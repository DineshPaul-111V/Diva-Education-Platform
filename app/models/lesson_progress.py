from datetime import datetime, timezone
from app.extensions import db
from app.models.learning_path import gen_uuid

def _utcnow():
    return datetime.now(timezone.utc)

class LessonProgress(db.Model):
    __tablename__ = "lesson_progress"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    learning_path_id = db.Column(db.String, db.ForeignKey("learning_paths.id"), nullable=False)
    lesson_id = db.Column(db.String, nullable=False, index=True)
    title = db.Column(db.String, nullable=False)
    tier = db.Column(db.String, nullable=False, default="Beginner")
    is_revision_module = db.Column(db.Boolean, default=False)
    target_skill_id = db.Column(db.String, nullable=False, default="")
    status = db.Column(db.String, nullable=False, default="LOCKED") # LOCKED|IN_PROGRESS|REVISION_REQUIRED|COMPLETED
    mastery_score = db.Column(db.Float, default=0.0)
    attempts_count = db.Column(db.Integer, default=0)
    misconceptions = db.Column(db.JSON, default=list) # JSON array of {conceptId, misconceptionText}
    content_sections = db.Column(db.JSON) # JSON array of subtopics with contents, examples, miniChecks
    quiz_json = db.Column(db.JSON) # 5 MCQs
    last_remediation = db.Column(db.JSON) # target revision text & retry quiz
    reteach_history = db.Column(db.JSON, default=list) # JSON array of {subtopicId, explanation, checkInQuestion}
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.Index('idx_lp_lesson', 'learning_path_id', 'lesson_id'),
    )
