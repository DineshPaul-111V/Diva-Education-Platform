from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app.models.learning_path import LearningPath
from app.models.lesson_progress import LessonProgress
from app.models.student_progress import StudentProgress
from app.learning.services.telemetry import get_topics_needing_review

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")

@analytics_bp.route("/dashboard-data", methods=["GET"])
@login_required
def dashboard_data():
    try:
        active_path = LearningPath.query.filter_by(user_id=current_user.id).order_by(LearningPath.created_at.desc()).first()
        student_progress = StudentProgress.query.filter_by(user_id=current_user.id).first()
        
        badges = list(student_progress.badges or []) if student_progress else []
        
        radar_data = []
        skills_breakdown = []
        topics_needing_review = []
        tier_stats = {
            "Beginner": {"total": 0, "completed": 0, "avgMastery": 0.0},
            "Intermediate": {"total": 0, "completed": 0, "avgMastery": 0.0},
            "Advanced": {"total": 0, "completed": 0, "avgMastery": 0.0},
            "Pro": {"total": 0, "completed": 0, "avgMastery": 0.0}
        }
        
        completed_count = 0
        total_count = 0
        lessons_list = []
        overall_mastery = 0.0
        
        mastered_count = 0
        proficient_count = 0
        developing_count = 0
        needs_review_count = 0
        
        top_strength = None
        top_growth = None
        
        if active_path:
            kg_raw = active_path.knowledge_graph or []
            kg_nodes = kg_raw if isinstance(kg_raw, list) else kg_raw.get("nodes", []) or kg_raw.get("knowledgeGraph", [])
            lessons = LessonProgress.query.filter_by(learning_path_id=active_path.id).all()
            
            total_count = len(lessons)
            completed_count = sum(1 for l in lessons if l.status == "COMPLETED")
            
            # Map of lessons by target_skill_id, lesson_id, and normalized title
            lesson_by_skill_id = {}
            lesson_by_lesson_id = {}
            for l in lessons:
                if l.target_skill_id:
                    lesson_by_skill_id[l.target_skill_id] = l
                lesson_by_lesson_id[l.lesson_id] = l
                
            lessons_list = [{
                "id": l.id,
                "lessonId": l.lesson_id,
                "title": l.title,
                "tier": l.tier,
                "status": l.status,
                "masteryScore": round(l.mastery_score or 0.0, 1)
            } for l in lessons]
            
            # Compute mastery for each skill
            total_score_sum = 0
            tier_scores = {"Beginner": [], "Intermediate": [], "Advanced": [], "Pro": []}
            
            for node in kg_nodes:
                node_label = node.get("label") or node.get("name") or "Concept"
                node_id = node.get("nodeId") or node.get("skillId") or ""
                skill_id = node.get("skillId") or node_id
                tier = node.get("tier") or "Beginner"
                if tier not in tier_scores:
                    tier = "Beginner"
                initial_mastery = float(node.get("initialMastery", 0.0))
                
                # Match lesson
                l = lesson_by_skill_id.get(skill_id) or lesson_by_lesson_id.get(node_id)
                if not l:
                    # Fallback title match
                    for candidate in lessons:
                        if candidate.title.strip().lower() == node_label.strip().lower() or candidate.title.strip().lower() in node_label.strip().lower():
                            l = candidate
                            break
                            
                lesson_status = l.status if l else "LOCKED"
                lesson_id_ref = l.id if l else None
                
                if l and l.status == "COMPLETED":
                    score = l.mastery_score if l.mastery_score > 0 else 100.0
                elif l and l.status == "IN_PROGRESS":
                    score = max(l.mastery_score or 0.0, 45.0)
                elif l and l.status == "REVISION_REQUIRED":
                    score = min(l.mastery_score or 0.0, 50.0) if l.mastery_score > 0 else 35.0
                else:
                    score = initial_mastery * 100.0 if initial_mastery > 0 else 0.0
                    
                score = min(100.0, max(0.0, round(score, 1)))
                total_score_sum += score
                tier_scores[tier].append(score)
                
                if score >= 80:
                    status_label = "Mastered"
                    mastered_count += 1
                elif score >= 60:
                    status_label = "Proficient"
                    proficient_count += 1
                elif score >= 30:
                    status_label = "Developing"
                    developing_count += 1
                else:
                    status_label = "Needs Focus"
                    needs_review_count += 1
                    
                skills_breakdown.append({
                    "skillId": skill_id,
                    "name": node_label,
                    "tier": tier,
                    "mastery": score,
                    "status": lesson_status,
                    "statusLabel": status_label,
                    "lessonDbId": lesson_id_ref
                })
                
            # If no KG nodes, compute directly from lessons
            if not skills_breakdown and lessons:
                for l in lessons:
                    score = (l.mastery_score or 100.0) if l.status == "COMPLETED" else (45.0 if l.status == "IN_PROGRESS" else 0.0)
                    tier = l.tier or "Beginner"
                    if tier not in tier_scores:
                        tier = "Beginner"
                    tier_scores[tier].append(score)
                    total_score_sum += score
                    
                    status_label = "Mastered" if score >= 80 else ("Proficient" if score >= 60 else ("Developing" if score >= 30 else "Needs Focus"))
                    if score >= 80: mastered_count += 1
                    elif score >= 60: proficient_count += 1
                    elif score >= 30: developing_count += 1
                    else: needs_review_count += 1
                    
                    skills_breakdown.append({
                        "skillId": l.target_skill_id or l.lesson_id,
                        "name": l.title,
                        "tier": tier,
                        "mastery": round(score, 1),
                        "status": l.status,
                        "statusLabel": status_label,
                        "lessonDbId": l.id
                    })
                    
            num_skills = len(skills_breakdown)
            overall_mastery = round(total_score_sum / num_skills, 1) if num_skills > 0 else 0.0
            
            # Compute tier distribution
            for t_name, scores in tier_scores.items():
                t_total = len(scores)
                t_avg = round(sum(scores) / t_total, 1) if t_total > 0 else 0.0
                tier_stats[t_name] = {
                    "total": t_total,
                    "completed": sum(1 for s in scores if s >= 80),
                    "avgMastery": t_avg
                }
                
            # Prepare clean Radar Chart dataset (deduplicated top 6-8 core capabilities)
            seen_concepts = set()
            radar_data = []
            for s in sorted(skills_breakdown, key=lambda x: (x["tier"], -x["mastery"])):
                clean_name = s["name"]
                if len(clean_name) > 20:
                    clean_name = clean_name[:17] + "..."
                if clean_name not in seen_concepts and len(radar_data) < 7:
                    seen_concepts.add(clean_name)
                    radar_data.append({
                        "concept": clean_name,
                        "mastery": s["mastery"],
                        "tier": s["tier"],
                        "fullMark": 100
                    })
                    
            # Fallback to tier stats if fewer than 3 nodes
            if len(radar_data) < 3:
                radar_data = []
                for t_name, stats in tier_stats.items():
                    if stats["total"] > 0:
                        radar_data.append({
                            "concept": f"{t_name} Skills",
                            "mastery": stats["avgMastery"],
                            "tier": t_name,
                            "fullMark": 100
                        })
                        
            # Identify Top Strength and Growth Focus
            sorted_by_score = sorted(skills_breakdown, key=lambda x: x["mastery"], reverse=True)
            top_strength = sorted_by_score[0]["name"] if sorted_by_score and sorted_by_score[0]["mastery"] > 0 else "Beginning Journey"
            
            weakest_candidates = [s for s in sorted_by_score if s["status"] in ("IN_PROGRESS", "REVISION_REQUIRED") or (s["status"] == "LOCKED" and s["mastery"] < 60)]
            top_growth = weakest_candidates[0]["name"] if weakest_candidates else (sorted_by_score[-1]["name"] if sorted_by_score else "Core Concepts")
            
            topics_needing_review = get_topics_needing_review(active_path.id)
            
        # Determine Mastery Level Grade
        if overall_mastery >= 90:
            mastery_grade = "Master Expert"
            grade_badge = "🏆"
        elif overall_mastery >= 75:
            mastery_grade = "Proficient Practitioner"
            grade_badge = "⭐"
        elif overall_mastery >= 50:
            mastery_grade = "Growing Developer"
            grade_badge = "🚀"
        elif overall_mastery >= 25:
            mastery_grade = "Developing Learner"
            grade_badge = "🌱"
        else:
            mastery_grade = "Novice Explorer"
            grade_badge = "🎯"
            
        return jsonify({
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "totalXP": student_progress.total_xp if student_progress else 0,
                "streakDays": student_progress.streak_days if student_progress else 0,
                "badges": badges
            },
            "activePath": {
                "id": active_path.id,
                "domain": active_path.domain,
                "initialLevel": active_path.initial_level,
                "createdAt": active_path.created_at.isoformat(),
                "totalLessonsCount": total_count,
                "completedLessonsCount": completed_count,
                "progressPercentage": round((completed_count / total_count) * 100) if total_count > 0 else 0,
                "lessons": lessons_list
            } if active_path else None,
            "masteryProfile": {
                "overallScore": overall_mastery,
                "grade": mastery_grade,
                "badge": grade_badge,
                "masteredCount": mastered_count,
                "proficientCount": proficient_count,
                "developingCount": developing_count,
                "needsReviewCount": needs_review_count,
                "topStrength": top_strength,
                "topGrowth": top_growth,
                "tierStats": tier_stats,
                "skills": skills_breakdown
            },
            "radarData": radar_data,
            "topicsNeedingReview": topics_needing_review
        })
    except Exception as e:
        print("Failed to compile dashboard data:", e)
        return jsonify({"error": "Failed to compile dashboard data"}), 500

@analytics_bp.route("/sudoku", methods=["GET"])
@login_required
def get_daily_sudoku():
    try:
        from flask import request
        from app.learning.services.sudoku_service import (
            generate_sudoku_board,
            get_grid_dimensions
        )
        from app.learning.services.daily_puzzle_service import (
            get_user_streak_info,
            get_today_date_str
        )
        
        size = int(request.args.get("size", 4))
        if size not in (4, 6, 9):
            size = 4
            
        today_str = get_today_date_str()
        grid, solution = generate_sudoku_board(size=size, date_seed=today_str)
        streak_info = get_user_streak_info(current_user.id)
        size, block_r, block_c = get_grid_dimensions(size)
        
        return jsonify({
            "success": True,
            "size": size,
            "blockRows": block_r,
            "blockCols": block_c,
            "initialGrid": grid,
            "solution": solution,
            "streakInfo": streak_info,
            "date": today_str
        })
    except Exception as e:
        print("Failed to load Sudoku:", e)
        return jsonify({"error": "Failed to load Sudoku"}), 500

@analytics_bp.route("/sudoku/submit", methods=["POST"])
@login_required
def submit_sudoku():
    try:
        from flask import request
        from app.learning.services.sudoku_service import verify_sudoku_board
        
        data = request.get_json() or {}
        submitted_board = data.get("board")
        solution = data.get("solution")
        size = int(data.get("size", 4))
        
        if not submitted_board or not solution:
            return jsonify({"error": "Missing board data"}), 400
            
        result = verify_sudoku_board(current_user.id, submitted_board, solution, size=size)
        return jsonify(result)
    except Exception as e:
        print("Failed to verify Sudoku:", e)
        return jsonify({"error": "Failed to verify Sudoku"}), 500

@analytics_bp.route("/sudoku/hint", methods=["POST"])
@login_required
def get_sudoku_hint():
    try:
        from flask import request
        from app.learning.services.sudoku_service import get_socratic_sudoku_hint
        
        data = request.get_json() or {}
        current_board = data.get("board")
        solution = data.get("solution")
        size = int(data.get("size", 4))
        
        if not current_board or not solution:
            return jsonify({"error": "Missing board data"}), 400
            
        hint_data = get_socratic_sudoku_hint(current_board, solution, size=size)
        return jsonify({
            "success": True,
            **hint_data
        })
    except Exception as e:
        print("Failed to calculate Sudoku hint:", e)
        return jsonify({"error": "Failed to calculate hint"}), 500

