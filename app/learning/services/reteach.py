from app.learning.services.llm import call_llm
from app.learning.services.prompts import RETEACH_PROMPT
from app.learning.services.schemas import ReteachResponse

def generate_reteach(skill_name: str, subtopic_title: str, original_explanation: str, student_struggle: str) -> ReteachResponse:
    prompt = RETEACH_PROMPT(skill_name, subtopic_title, original_explanation, student_struggle)
    return call_llm(prompt, ReteachResponse, model_type="fast")
