from datetime import datetime, timezone
from app.extensions import db
from app.models.learning_path import gen_uuid

def _utcnow():
    return datetime.now(timezone.utc)

class DailyPuzzle(db.Model):
    __tablename__ = "daily_puzzles"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    puzzle_date = db.Column(db.String, nullable=False, unique=True, index=True) # YYYY-MM-DD
    category = db.Column(db.String, nullable=False, default="Output Predictor") # Output Predictor | Spot the Bug | Logic Riddle | Time Complexity
    title = db.Column(db.String, nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    code_snippet = db.Column(db.Text, nullable=True)
    options = db.Column(db.JSON, nullable=False) # List of 4 string options
    correct_option_index = db.Column(db.Integer, nullable=False) # 0-indexed
    explanation = db.Column(db.Text, nullable=False)
    hint = db.Column(db.Text, nullable=False)
    xp_reward = db.Column(db.Integer, nullable=False, default=50)
    created_at = db.Column(db.DateTime, default=_utcnow)
