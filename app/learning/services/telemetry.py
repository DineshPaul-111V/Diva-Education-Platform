import logging
from datetime import datetime, timedelta
from app.extensions import db
from app.models.telemetry import TelemetryEvent
from app.models.student_progress import StudentProgress
from app.models.lesson_progress import LessonProgress

logger = logging.getLogger(__name__)

SPACED_REPETITION_DECAY_DAYS = 14
DECAY_MULTIPLIER = 0.8

def log_telemetry(learning_path_id: str, event_type: str, payload: dict):
    """
    Logs a telemetry event to feed the analytics and feedback loops.
    """
    try:
        event = TelemetryEvent(
            learning_path_id=learning_path_id,
            event_type=event_type,
            payload=payload
        )
        db.session.add(event)
        db.session.flush()  # Flush instead of commit to avoid nested commit issues
    except Exception as err:
        db.session.rollback()
        logger.warning("Failed to log telemetry event: %s", err)

def record_student_activity(user_id: str, xp_gained: int):
    """
    Awards XP, updates streaks, and checks badges on student progression.
    """
    try:
        existing = StudentProgress.query.filter_by(user_id=user_id).first()
        now = datetime.utcnow()
        
        if not existing:
            new_progress = StudentProgress(
                user_id=user_id,
                total_xp=xp_gained,
                streak_days=1,
                last_active=now,
                badges=["First Steps"]
            )
            db.session.add(new_progress)
            db.session.commit()
            return
            
        # Check streak
        diff = now - existing.last_active
        diff_hours = diff.total_seconds() / 3600.0
        
        streak = existing.streak_days
        if 24.0 <= diff_hours <= 48.0:
            streak += 1
        elif diff_hours > 48.0:
            streak = 1
            
        current_badges = list(existing.badges or [])
        new_xp = existing.total_xp + xp_gained
        
        if new_xp >= 100 and "Century Club" not in current_badges:
            current_badges.append("Century Club")
        if new_xp >= 500 and "Mastery Scholar" not in current_badges:
            current_badges.append("Mastery Scholar")
        if streak >= 3 and "Consistent Learner" not in current_badges:
            current_badges.append("Consistent Learner")
            
        existing.total_xp = new_xp
        existing.streak_days = streak
        existing.last_active = now
        existing.badges = current_badges
        db.session.commit()
    except Exception as err:
        db.session.rollback()
        logger.warning("Failed to record student activity: %s", err)

def get_topics_needing_review(learning_path_id: str) -> list:
    """
    Computes spaced repetition mastery decay for nodes not revisited in >14 days.
    """
    try:
        cutoff = datetime.utcnow() - timedelta(days=SPACED_REPETITION_DECAY_DAYS)
        stale_lessons = LessonProgress.query.filter(
            LessonProgress.learning_path_id == learning_path_id,
            LessonProgress.status == "COMPLETED",
            LessonProgress.updated_at < cutoff
        ).all()
        
        results = []
        for l in stale_lessons:
            days = (datetime.utcnow() - l.updated_at).days
            results.append({
                "lessonId": l.lesson_id,
                "title": l.title,
                "currentMastery": round(l.mastery_score * DECAY_MULTIPLIER),
                "originalMastery": l.mastery_score,
                "daysSinceReview": days
            })
        return results
    except Exception as err:
        logger.warning("Failed to compute spaced repetition decay: %s", err)
        return []
