from datetime import datetime, timezone
from app.extensions import db
from app.models.learning_path import gen_uuid

def _utcnow():
    return datetime.now(timezone.utc)

class StudentProgress(db.Model):
    __tablename__ = "student_progress"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, unique=True)
    total_xp = db.Column(db.Integer, nullable=False, default=0)
    streak_days = db.Column(db.Integer, nullable=False, default=0)
    streak_freeze_count = db.Column(db.Integer, nullable=False, default=1)
    last_puzzle_date = db.Column(db.String, nullable=True) # YYYY-MM-DD
    streak_history = db.Column(db.JSON, nullable=False, default=list) # List of completed YYYY-MM-DD date strings
    puzzles_solved_count = db.Column(db.Integer, nullable=False, default=0)
    badges = db.Column(db.JSON, nullable=False, default=list) # JSON array of earned badge names
    last_active = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
