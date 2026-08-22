import logging
import re
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import limiter
from app.models.learning_path import LearningPath
from app.learning.services.llm import call_llm_text, LLMGenerationError
from app.learning.services.prompts import TUTOR_RAG_PROMPT
from app.learning.services.rag import retrieve_student_context

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 2000

tutor_bp = Blueprint("tutor", __name__, url_prefix="/tutor")

def detect_requested_language(message: str, fallback_lang: str = None) -> str:
    msg_lower = (message or "").lower()
    # Check explicit patterns and inflectional forms (e.g., "explain in tamil", "tamil", "banglay", "marathit", "telungu")
    if re.search(r'(tamil|தமிழ்|thamil|tamizh)', msg_lower):
        return "Tamil"
    if re.search(r'(telugu|తెలుగు|telungu)', msg_lower):
        return "Telugu"
    if re.search(r'(bengali|bangla|বাংলা|banglay)', msg_lower):
        return "Bengali"
    if re.search(r'(hindi|हिंदी|hinglish)', msg_lower):
        return "Hindi"
    if re.search(r'(marathi|मराठी|maratti|marathit)', msg_lower):
        return "Marathi"
    if re.search(r'\b(english|angrezi)\b', msg_lower):
        return "English"
    return fallback_lang or "English"

@tutor_bp.route("/chat", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def chat():
    data = request.json or {}
    learning_path_id = data.get("learningPathId")
    message = data.get("message", "").strip()[:MAX_MESSAGE_LENGTH]
    quick_action = data.get("quickAction") # simplify | enterprise_example | debug_thought
    
    if len(message) < 1:
        return jsonify({"error": "Message cannot be empty"}), 400
        
    retrieved_chunks = []
    if learning_path_id:
        path = LearningPath.query.get(learning_path_id)
        if path and path.user_id == current_user.id:
            raw_chunks = retrieve_student_context(learning_path_id, message, top_k=4)
            retrieved_chunks = [c[:750] for c in raw_chunks]
    else:
        # Fallback to the user's latest active learning path if available
        latest_path = LearningPath.query.filter_by(user_id=current_user.id).order_by(LearningPath.created_at.desc()).first()
        if latest_path:
            raw_chunks = retrieve_student_context(latest_path.id, message, top_k=4)
            retrieved_chunks = [c[:750] for c in raw_chunks]

    # Detect requested language from message, payload or cookie
    preferred_lang = data.get("language") or request.cookies.get("preferred_language", "English")
    target_language = detect_requested_language(message, fallback_lang=preferred_lang)

    try:
        # Call LLM to respond in target language
        prompt = TUTOR_RAG_PROMPT(message, retrieved_chunks, quick_action, language=target_language)
        reply = call_llm_text(prompt)
        
        return jsonify({
            "reply": reply,
            "language": target_language,
            "retrievedChunksCount": len(retrieved_chunks)
        })
    except LLMGenerationError:
        logger.exception("AI Tutor LLM call failed")
        return jsonify({"error": "The AI Tutor is temporarily unavailable due to high demand. Please try again in a moment."}), 503
    except Exception as e:
        logger.exception("AI Tutor unexpected error")
        return jsonify({"error": f"AI Tutor is currently unavailable: {str(e)}"}), 500
