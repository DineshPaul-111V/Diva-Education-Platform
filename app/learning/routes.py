import json
import re
import logging
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.models.learning_path import LearningPath
from app.models.lesson_progress import LessonProgress
from app.models.student_progress import StudentProgress
from app.learning.services.skill_map import generate_skill_map
from app.learning.services.diagnostic import generate_diagnostic
from app.learning.services.level_detection import detect_student_level
from app.learning.services.roadmap import generate_roadmap
from app.learning.services.lesson_content import generate_full_lesson
from app.learning.services.remediation import generate_remediation, generate_retry_quiz
from app.learning.services.reteach import generate_reteach
from app.learning.services.mastery import evaluate_quiz_submission
from app.learning.services.telemetry import log_telemetry, record_student_activity, get_topics_needing_review
from app.learning.services.rag import store_student_embedding

logger = logging.getLogger(__name__)

# Input constraints
MAX_DOMAIN_LENGTH = 200
MAX_MESSAGE_LENGTH = 2000

def sanitize_text_input(text: str, max_length: int = MAX_DOMAIN_LENGTH) -> str:
    """Strip control characters and cap length for user-supplied text inputs."""
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return cleaned.strip()[:max_length]

learning_bp = Blueprint("learning", __name__, url_prefix="/learning")

@learning_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    paths = LearningPath.query.filter_by(user_id=current_user.id).order_by(LearningPath.created_at.desc()).all()
    # Get active path
    active_path = LearningPath.query.filter_by(user_id=current_user.id).order_by(LearningPath.created_at.desc()).first()
    
    topics_need_review = []
    progress_pct = 0
    completed_count = 0
    total_lessons = 0
    lessons = []
    
    if active_path:
        topics_need_review = get_topics_needing_review(active_path.id)
        lessons = LessonProgress.query.filter_by(learning_path_id=active_path.id).all()
        total_lessons = len(lessons)
        completed_count = sum(1 for l in lessons if l.status == "COMPLETED")
        if total_lessons > 0:
            progress_pct = int((completed_count / total_lessons) * 100)
            
    student_progress = StudentProgress.query.filter_by(user_id=current_user.id).first()
    
    return render_template(
        "dashboard/dashboard.html",
        paths=paths,
        active_path=active_path,
        topics_need_review=topics_need_review,
        progress_pct=progress_pct,
        completed_count=completed_count,
        total_lessons=total_lessons,
        student_progress=student_progress,
        lessons=lessons
    )

@learning_bp.route("/new", methods=["GET"])
@login_required
def new_path():
    # Call LLM to suggest trending topics
    from app.learning.services.llm import call_llm
    from app.learning.services.prompts import TRENDING_TOPICS_PROMPT
    from app.learning.services.schemas import TrendingTopicsResponse
    try:
        data = call_llm(TRENDING_TOPICS_PROMPT(), TrendingTopicsResponse)
        trending = data.topics
    except Exception:
        trending = ["Rust systems programming", "Kubernetes for backend", "React performance tuning", "Python Data Analytics", "Machine Learning", "Cloud Security"]
    return render_template("learning/new_path.html", trending=trending)

@learning_bp.route("/assessment", methods=["GET"])
@login_required
def assessment():
    return render_template("assessment/assessment.html")

@learning_bp.route("/skill-map", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def skill_map_api():
    domain = sanitize_text_input(request.json.get("domain", ""))
    if len(domain) < 2:
        return jsonify({"error": "Please specify a domain of at least 2 characters."}), 400
    if len(domain) > MAX_DOMAIN_LENGTH:
        return jsonify({"error": f"Domain must be under {MAX_DOMAIN_LENGTH} characters."}), 400
    try:
        skill_map_data = generate_skill_map(domain)
        return jsonify(skill_map_data.model_dump())
    except Exception as e:
        logger.exception("Failed to generate skill map for domain '%s'", domain)
        return jsonify({"error": f"Failed to generate skill map: {str(e)}"}), 500

@learning_bp.route("/diagnostic/generate", methods=["POST"])
@login_required
@limiter.limit("3 per minute")
def diagnostic_generate():
    data = request.json or {}
    domain = sanitize_text_input(data.get("domain", ""))
    skill_map = data.get("skillMap", [])
    
    if len(domain) < 2:
        return jsonify({"error": "Invalid domain"}), 400
    if len(domain) > MAX_DOMAIN_LENGTH:
        return jsonify({"error": f"Domain must be under {MAX_DOMAIN_LENGTH} characters."}), 400
        
    try:
        if not skill_map:
            skill_map_res = generate_skill_map(domain)
            skill_map = skill_map_res.model_dump()["skillMap"]
            
        diag = generate_diagnostic(domain, {"domain": domain, "skillMap": skill_map})
        return jsonify({
            "domain": domain,
            "skillMap": skill_map,
            "questions": diag.model_dump()["questions"]
        })
    except Exception as e:
        logger.exception("Failed to generate diagnostic for domain '%s'", domain)
        return jsonify({"error": f"Failed to generate placement test: {str(e)}"}), 500

@learning_bp.route("/diagnostic/submit", methods=["POST"])
@login_required
@limiter.limit("3 per minute")
def diagnostic_submit():
    data = request.json or {}
    domain = data.get("domain")
    skill_map = data.get("skillMap")
    questions = data.get("questions")
    answers = data.get("answers") # list of {id, selectedIndex}
    
    if not domain or not skill_map or not questions or not answers:
        return jsonify({"error": "Invalid payload"}), 400
        
    try:
        # Evaluate diagnostic quiz
        quiz_key = [{"id": q["id"], "correctIndex": q["correctAnswer"], "testedSkill": q["skillId"]} for q in questions]
        eval_result = evaluate_quiz_submission(quiz_key, answers)
        
        # Grade questions for level detection
        graded_for_level = []
        for q in questions:
            user_ans = next((a for a in answers if a["id"] == q["id"]), None)
            is_correct = user_ans is not None and user_ans["selectedIndex"] == q["correctAnswer"]
            graded_for_level.append({"tier": q["tier"], "correct": is_correct})
            
        detected_level = detect_student_level(graded_for_level)
        
        # Extract misconceptions
        detected_misconceptions = []
        for q in questions:
            user_ans = next((a for a in answers if a["id"] == q["id"]), None)
            if user_ans and user_ans["selectedIndex"] != q["correctAnswer"]:
                key = str(user_ans["selectedIndex"])
                misc_explanation = q.get("misconceptionMapping", {}).get(key, f"Selected incorrect alternative for skill: {q['skillId']}")
                detected_misconceptions.append({
                    "skillId": q["skillId"],
                    "misconceptionText": misc_explanation
                })
                
        # Generate personalized roadmap
        roadmap_data = generate_roadmap(
            domain,
            {"domain": domain, "skillMap": skill_map},
            detected_level,
            detected_misconceptions
        )
        roadmap_dict = roadmap_data.model_dump()
        
        # Save LearningPath to db
        learning_path = LearningPath(
            user_id=current_user.id,
            domain=roadmap_dict["domain"],
            initial_level=detected_level,
            detected_level=detected_level,
            skill_map=skill_map,
            knowledge_graph=roadmap_dict["knowledgeGraph"],
            roadmap=roadmap_dict["modules"]
        )
        db.session.add(learning_path)
        db.session.commit()
        
        # Seed LessonProgress
        is_first = True
        for module_item in roadmap_dict["modules"]:
            for lesson in module_item["lessons"]:
                linked_node = next((n for n in roadmap_dict["knowledgeGraph"] if n["skillId"] == lesson["targetSkillId"] or n["nodeId"] == lesson["id"]), None)
                node_misconceptions = linked_node["linkedMisconceptions"] if linked_node else []
                
                lesson_progress = LessonProgress(
                    learning_path_id=learning_path.id,
                    lesson_id=lesson["id"],
                    title=lesson["title"],
                    tier=module_item["tier"],
                    is_revision_module=module_item["isRevision"],
                    target_skill_id=lesson["targetSkillId"],
                    status="IN_PROGRESS" if is_first else "LOCKED",
                    mastery_score=(linked_node["initialMastery"] * 100) if linked_node else 0.0,
                    attempts_count=0,
                    misconceptions=[{
                        "conceptId": lesson["targetSkillId"],
                        "misconceptionText": m
                    } for m in node_misconceptions]
                )
                db.session.add(lesson_progress)
                is_first = False
                
        db.session.commit()
        
        # Store diagnostic misconceptions in student RAG
        for misc in detected_misconceptions:
            store_student_embedding(
                learning_path.id,
                "MISCONCEPTION",
                misc["skillId"],
                f"Placement Misconception in {misc['skillId']}: {misc['misconceptionText']}"
            )
            
        # Log telemetry
        log_telemetry(learning_path.id, "QUIZ_SUBMITTED", {
            "type": "DIAGNOSTIC_PLACEMENT",
            "score": eval_result["score"],
            "detectedLevel": detected_level,
            "totalQuestions": len(questions),
            "misconceptionsCount": len(detected_misconceptions)
        })
        
        # Award XP
        record_student_activity(current_user.id, 30)
        
        return jsonify({
            "success": True,
            "learningPathId": learning_path.id,
            "score": eval_result["score"],
            "detectedLevel": detected_level,
            "skillMap": skill_map,
            "knowledgeGraph": roadmap_dict["knowledgeGraph"],
            "roadmap": roadmap_dict["modules"]
        })
    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to submit diagnostic for user %s", current_user.id)
        return jsonify({"error": f"Failed to submit placement assessment: {str(e)}"}), 500

@learning_bp.route("/roadmap/<path_id>", methods=["GET"])
@login_required
def roadmap_view(path_id):
    path = LearningPath.query.get_or_404(path_id)
    if path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    lessons = LessonProgress.query.filter_by(learning_path_id=path.id).all()
    # Group lessons by status or just expose status
    lesson_statuses = {l.lesson_id: l.status for l in lessons}
    lesson_db_ids = {l.lesson_id: l.id for l in lessons}
    
    return render_template(
        "roadmap/roadmap.html",
        path=path,
        lesson_statuses=lesson_statuses,
        lesson_db_ids=lesson_db_ids
    )

@learning_bp.route("/lesson/<progress_id>", methods=["GET"])
@login_required
def lesson_view(progress_id):
    lesson = LessonProgress.query.get_or_404(progress_id)
    if not lesson.learning_path or lesson.learning_path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    force_regen = request.args.get("regenerate") == "true"
    
    # Auto-detect legacy thin content to upgrade to comprehensive 50-min textbook standard
    is_thin_content = False
    if lesson.content_sections and isinstance(lesson.content_sections, list) and not force_regen:
        section_word_counts = []
        for s in lesson.content_sections:
            if isinstance(s, dict):
                c = s.get("content") or ""
                section_word_counts.append(len(c.split()))
        if section_word_counts and (any(cnt < 220 for cnt in section_word_counts) or sum(section_word_counts) < 900):
            is_thin_content = True
            logger.info("Upgrading legacy thin lesson content (%s words) for '%s'", sum(section_word_counts), lesson.title)
    
    if not lesson.content_sections or force_regen or is_thin_content:
        # Generate new multi-section lesson
        skill_name = lesson.title
        skill_desc = f"Skill: {lesson.title} ({lesson.target_skill_id or lesson.lesson_id})"
        tier = lesson.tier
        is_revision = lesson.is_revision_module
        domain = lesson.learning_path.domain if lesson.learning_path else "General"
        
        try:
            generated = generate_full_lesson(
                lesson.learning_path_id,
                lesson.lesson_id,
                skill_name,
                skill_desc,
                tier,
                is_revision,
                domain
            )
            
            lesson.content_sections = generated["sections"]
            lesson.quiz_json = generated["quiz"]
            if lesson.status == "LOCKED":
                lesson.status = "IN_PROGRESS"
            if force_regen:
                lesson.attempts_count = 0
                lesson.last_remediation = None
            db.session.commit()
            
            log_telemetry(lesson.learning_path_id, "LESSON_VIEWED", {
                "lessonId": lesson.lesson_id,
                "title": lesson.title,
                "isFirstView": True,
                "isRevision": lesson.is_revision_module
            })
            
            if force_regen:
                return redirect(url_for("learning.lesson_view", progress_id=progress_id))
        except Exception as e:
            db.session.rollback()
            logger.exception("Failed to generate lesson content for '%s'", lesson.title)
            # Don't save partial content — leave content_sections as None so it retries on next visit
            flash("Failed to generate lesson content. Please try again.", "error")
            return redirect(url_for("learning.roadmap_view", path_id=lesson.learning_path_id))
    else:
        log_telemetry(lesson.learning_path_id, "LESSON_VIEWED", {
            "lessonId": lesson.lesson_id,
            "title": lesson.title,
            "isFirstView": False
        })
        
    # Sanitize quiz to hide correct index from client
    client_quiz = []
    if lesson.quiz_json:
        raw_quiz = lesson.quiz_json
        if isinstance(raw_quiz, str):
            try:
                raw_quiz = json.loads(raw_quiz)
            except Exception:
                raw_quiz = []
        if isinstance(raw_quiz, list):
            for q in raw_quiz:
                if isinstance(q, dict):
                    client_quiz.append({
                        "id": q.get("id", ""),
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "subtopicId": q.get("subtopicId", "")
                    })
            
    from app.learning.services.lesson_content import ensure_section_mcqs
    domain = lesson.learning_path.domain if lesson.learning_path else "General"
    sections_with_mcqs = ensure_section_mcqs(lesson.content_sections or [], lesson.title, domain)

    try:
        return render_template(
            "lesson/lesson.html",
            lesson=lesson,
            quiz=client_quiz,
            sections=sections_with_mcqs
        )
    except Exception as e:
        logger.exception("Failed to render lesson view for progress_id '%s'", progress_id)
        flash("An error occurred while loading this lesson. Please try again.", "error")
        return redirect(url_for("learning.roadmap_view", path_id=lesson.learning_path_id))

@learning_bp.route("/lesson/<progress_id>/download-pdf", methods=["GET"])
@login_required
def lesson_download_pdf(progress_id):
    from flask import Response
    from app.learning.services.pdf_export import generate_lesson_pdf
    
    lesson = LessonProgress.query.get_or_404(progress_id)
    if lesson.learning_path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    try:
        pdf_bytes = generate_lesson_pdf(
            title=lesson.title,
            domain=lesson.learning_path.domain,
            tier=lesson.tier,
            sections=lesson.content_sections or []
        )
        safe_filename = re.sub(r'[^a-zA-Z0-9_-]+', '_', lesson.title).strip('_')
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{safe_filename}_Study_Guide.pdf"'}
        )
    except Exception as e:
        logger.exception("Failed to generate binary PDF for lesson %s", lesson.title)
        flash("Failed to generate PDF. Falling back to print view.", "error")
        return redirect(url_for("learning.lesson_syllabus", progress_id=progress_id))

@learning_bp.route("/roadmap/<path_id>/download-pdf", methods=["GET"])
@login_required
def roadmap_download_pdf(path_id):
    from flask import Response
    from app.learning.services.pdf_export import generate_roadmap_pdf
    
    path = LearningPath.query.get_or_404(path_id)
    if path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    try:
        pdf_bytes = generate_roadmap_pdf(
            domain=path.domain,
            detected_level=path.detected_level or "All Levels",
            roadmap=path.roadmap or []
        )
        safe_filename = re.sub(r'[^a-zA-Z0-9_-]+', '_', path.domain).strip('_')
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{safe_filename}_Course_Syllabus.pdf"'}
        )
    except Exception as e:
        logger.exception("Failed to generate binary PDF for roadmap %s", path.domain)
        flash("Failed to generate PDF. Falling back to print view.", "error")
        return redirect(url_for("learning.roadmap_syllabus", path_id=path_id))

@learning_bp.route("/lesson/<progress_id>/syllabus", methods=["GET"])
@login_required
def lesson_syllabus(progress_id):
    lesson = LessonProgress.query.get_or_404(progress_id)
    if lesson.learning_path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    return render_template(
        "lesson/syllabus_print.html",
        title=lesson.title,
        domain=lesson.learning_path.domain,
        tier=lesson.tier,
        type_badge="Lesson Masterclass Syllabus",
        download_url=url_for("learning.lesson_download_pdf", progress_id=lesson.id),
        sections=lesson.content_sections or []
    )

@learning_bp.route("/roadmap/<path_id>/syllabus", methods=["GET"])
@login_required
def roadmap_syllabus(path_id):
    path = LearningPath.query.get_or_404(path_id)
    if path.user_id != current_user.id:
        return redirect(url_for("learning.dashboard"))
        
    return render_template(
        "lesson/syllabus_print.html",
        title=f"{path.domain} Complete Curriculum",
        domain=path.domain,
        tier=path.detected_level or "Beginner to Advanced",
        type_badge="Complete Course Syllabus",
        download_url=url_for("learning.roadmap_download_pdf", path_id=path.id),
        roadmap=path.roadmap or []
    )

@learning_bp.route("/lesson/<progress_id>/submit", methods=["POST"])
@login_required
def lesson_submit(progress_id):
    lesson = LessonProgress.query.get_or_404(progress_id)
    if lesson.learning_path.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json or {}
    answers = data.get("answers", []) # list of {id, selectedIndex}
    
    if not lesson.quiz_json:
        return jsonify({"error": "No quiz registered for this lesson"}), 400
        
    eval_result = evaluate_quiz_submission(lesson.quiz_json, answers)
    new_attempt = lesson.attempts_count + 1
    
    if eval_result["passed"]:
        lesson.status = "COMPLETED"
        lesson.mastery_score = eval_result["score"]
        lesson.attempts_count = new_attempt
        db.session.commit()
        
        # Unlock next lesson
        next_progress = None
        roadmap = lesson.learning_path.roadmap
        found_curr = False
        next_les_id = None
        if roadmap:
            for mod in roadmap:
                for les in mod.get("lessons", []):
                    if found_curr and not next_les_id:
                        next_les_id = les.get("id")
                        break
                    if les.get("id") == lesson.lesson_id:
                        found_curr = True
                if next_les_id:
                    break
                
        if next_les_id:
            next_progress = LessonProgress.query.filter_by(
                learning_path_id=lesson.learning_path_id,
                lesson_id=next_les_id
            ).first()
            if next_progress and next_progress.status == "LOCKED":
                next_progress.status = "IN_PROGRESS"
                db.session.commit()
        else:
            # Fallback: if roadmap traversal didn't find a next lesson,
            # unlock the first LOCKED lesson by database order to prevent student getting stuck
            fallback_next = LessonProgress.query.filter_by(
                learning_path_id=lesson.learning_path_id,
                status="LOCKED"
            ).first()
            if fallback_next:
                fallback_next.status = "IN_PROGRESS"
                db.session.commit()
                next_progress = fallback_next
                logger.warning("Used fallback unlock for lesson %s (roadmap traversal failed)", fallback_next.lesson_id)
                
        log_telemetry(lesson.learning_path_id, "LESSON_COMPLETED", {
            "lessonId": lesson.lesson_id,
            "score": eval_result["score"],
            "attemptsCount": new_attempt
        })
        
        record_student_activity(current_user.id, 50)
        
        return jsonify({
            "passed": True,
            "score": eval_result["score"],
            "correctCount": eval_result["correctCount"],
            "totalQuestions": eval_result["totalQuestions"],
            "xpAwarded": 50,
            "nextLessonProgressId": next_progress.id if next_progress else None
        })
    else:
        # Quiz failed, provide remediation and retry quiz
        wrong_summary = "\n".join(
            f"- Question: \"{w['question'].get('question', 'N/A') if isinstance(w['question'], dict) else 'N/A'}\"\n  Student Choice: {w['given']}\n  Explanation: {w['question'].get('explanation', '') if isinstance(w['question'], dict) else ''}"
            for w in eval_result["wrongAnswers"]
        )
        
        remediation = generate_remediation(lesson.title, wrong_summary)
        remediation_dict = remediation.model_dump()
        
        retry_quiz_data = generate_retry_quiz(
            lesson.title,
            lesson.learning_path.detected_level or "Beginner",
            # Assembled content markdown
            "\n\n".join(s["content"] for s in lesson.content_sections),
            remediation_dict["remediationText"]
        )
        retry_quiz_dict = retry_quiz_data.model_dump()
        
        # Store remediation text in RAG
        store_student_embedding(
            lesson.learning_path_id,
            "REMEDIATION",
            f"{lesson.lesson_id}_att_{new_attempt}",
            f"Remediation for {lesson.title} (Attempt {new_attempt}):\n{remediation_dict['remediationText']}"
        )
        
        lesson.status = "REVISION_REQUIRED"
        lesson.mastery_score = eval_result["score"]
        lesson.attempts_count = new_attempt
        lesson.quiz_json = retry_quiz_dict["quiz"]
        lesson.last_remediation = remediation_dict
        db.session.commit()
        
        log_telemetry(lesson.learning_path_id, "REMEDIATION_TRIGGERED", {
            "lessonId": lesson.lesson_id,
            "score": eval_result["score"],
            "attemptsCount": new_attempt
        })
        
        # Sanitize quiz for client response
        client_retry_quiz = [{
            "id": q["id"],
            "question": q["question"],
            "options": q["options"]
        } for q in retry_quiz_dict["quiz"]]
        
        return jsonify({
            "passed": False,
            "score": eval_result["score"],
            "correctCount": eval_result["correctCount"],
            "totalQuestions": eval_result["totalQuestions"],
            "remediation": remediation_dict,
            "retryQuiz": client_retry_quiz,
            "attemptsCount": new_attempt,
            "escalateToTutor": new_attempt >= 3
        })

@learning_bp.route("/lesson/<progress_id>/reteach", methods=["POST"])
@login_required
def lesson_reteach(progress_id):
    lesson = LessonProgress.query.get_or_404(progress_id)
    if lesson.learning_path.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json or {}
    subtopic_id = data.get("subtopicId")
    student_struggle = sanitize_text_input(data.get("struggle", "I don't understand the main concept."), MAX_MESSAGE_LENGTH)
    
    if not lesson.content_sections:
        return jsonify({"error": "Lesson content not generated yet. Please open the lesson first."}), 400
    
    section = next((s for s in lesson.content_sections if s["subtopicId"] == subtopic_id), None)
    if not section:
        return jsonify({"error": "Subtopic not found in this lesson"}), 404
        
    try:
        reteach_data = generate_reteach(
            lesson.title,
            section["title"],
            section["content"],
            student_struggle
        )
        reteach_dict = reteach_data.model_dump()
        
        # Save to reteach history
        history = list(lesson.reteach_history or [])
        history.append({
            "subtopicId": subtopic_id,
            "struggle": student_struggle,
            "reteachContent": reteach_dict["reteachContent"],
            "checkInQuestion": reteach_dict["checkInQuestion"]
        })
        lesson.reteach_history = history
        db.session.commit()
        
        return jsonify(reteach_dict)
    except Exception as e:
        logger.exception("Failed to generate reteach for lesson %s subtopic %s", lesson.lesson_id, subtopic_id)
        return jsonify({"error": f"Failed to generate alternative explanation: {str(e)}"}), 500


@learning_bp.route("/lesson/<progress_id>/check-mini", methods=["POST"])
@login_required
def lesson_check_mini(progress_id):
    """
    AI-powered mini check answer evaluation.
    Returns { correct: bool, feedback: str, correctAnswer: str }
    """
    lesson = LessonProgress.query.get_or_404(progress_id)
    if lesson.learning_path.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    subtopic_id = data.get("subtopicId", "")
    question = data.get("question", "")
    student_answer = data.get("studentAnswer", "").strip()

    if not student_answer:
        return jsonify({"error": "No answer provided"}), 400

    # Find the section context for richer evaluation
    section_context = ""
    if lesson.content_sections:
        sec = next((s for s in lesson.content_sections if s.get("subtopicId") == subtopic_id), None)
        if sec:
            section_context = sec.get("content", "")[:600]  # first 600 chars as context

    from app.learning.services.llm import call_llm_text
    eval_prompt = f"""You are an educational AI evaluating a student's answer to a mini-check question.

Lesson: "{lesson.title}"
Mini-Check Question: "{question}"
Student's Answer: "{student_answer}"
Section Context (excerpt): "{section_context}"

Evaluate strictly but fairly. Determine:
1. Is the student's answer correct or essentially correct? (Yes/No)
2. A brief 1-2 sentence feedback message for the student.
3. The ideal correct answer in 1-2 concise sentences.

Respond in this exact format (no extra text):
CORRECT: yes
FEEDBACK: <your feedback here>
CORRECT_ANSWER: <ideal answer here>

If the answer is wrong, FEEDBACK must start with "Not quite —" and explain the error clearly.
If correct, FEEDBACK must start with "Correct! " and reinforce the key point."""

    try:
        raw = call_llm_text(eval_prompt, model_type="fast")
        
        # Parse the structured response
        lines = raw.strip().splitlines()
        result = {"correct": False, "feedback": "Could not evaluate answer.", "correctAnswer": ""}
        for line in lines:
            if line.startswith("CORRECT:"):
                val = line.split(":", 1)[1].strip().lower()
                result["correct"] = val in ("yes", "true", "correct")
            elif line.startswith("FEEDBACK:"):
                result["feedback"] = line.split(":", 1)[1].strip()
            elif line.startswith("CORRECT_ANSWER:"):
                result["correctAnswer"] = line.split(":", 1)[1].strip()

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Failed to evaluate answer: {str(e)}"}), 500

@learning_bp.route("/upload-notes", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def upload_notes():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    path_id = request.form.get("learning_path_id")
    if not path_id:
        return jsonify({"error": "Missing learning path"}), 400
        
    # Verify ownership
    path = LearningPath.query.get(path_id)
    if not path or path.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
        
    if file and file.filename.lower().endswith('.pdf'):
        from app.learning.services.rag import process_uploaded_pdf
        try:
            file_bytes = file.read()
            process_uploaded_pdf(path_id, file_bytes, file.filename)
            return jsonify({"success": True, "message": "Notes processed successfully!"})
        except Exception as e:
            logger.exception("Failed to process notes")
    return jsonify({"error": "Only PDFs are supported right now"}), 400

# ── Multi-Lingual Diva AI Voice Audio Stream Endpoint ──
TTS_LANG_MAP = {
    'tamil': 'ta',
    'ta': 'ta',
    'telugu': 'te',
    'te': 'te',
    'bengali': 'bn',
    'bn': 'bn',
    'bangla': 'bn',
    'hindi': 'hi',
    'hi': 'hi',
    'marathi': 'mr',
    'mr': 'mr',
    'english': 'en',
    'en': 'en'
}

@learning_bp.route("/voice/tts", methods=["GET"])
def voice_tts():
    import urllib.request
    import urllib.parse
    from flask import Response

    text = request.args.get("text", "").strip()
    lang = request.args.get("lang", "english").strip().lower()
    
    if not text:
        return Response(b"", mimetype="audio/mpeg")
    
    # Cap text length per chunk strictly under Google's 200-character limit
    text = text[:199]
    lang_code = TTS_LANG_MAP.get(lang, 'en')
    encoded_q = urllib.parse.quote(text, safe='')
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={lang_code}&client=tw-ob&q={encoded_q}"
    
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            audio_bytes = response.read()
            return Response(audio_bytes, mimetype="audio/mpeg", headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Type": "audio/mpeg"
            })
    except Exception as e:
        logger.warning(f"Voice TTS fetch error: {e}")
        return jsonify({"error": "Failed to stream audio"}), 502
