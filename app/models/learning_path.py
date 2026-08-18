import uuid
from datetime import datetime, timezone
from app.extensions import db

def gen_uuid():
    return str(uuid.uuid4())

def _utcnow():
    return datetime.now(timezone.utc)

class LearningPath(db.Model):
    __tablename__ = "learning_paths"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    domain = db.Column(db.String, nullable=False)
    initial_level = db.Column(db.String)
    detected_level = db.Column(db.String)
    skill_map = db.Column(db.JSON, nullable=False, default=list)
    knowledge_graph = db.Column(db.JSON, nullable=False, default=dict)
    roadmap = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=_utcnow)
    
    lessons = db.relationship("LessonProgress", backref="learning_path", lazy=True, cascade="all, delete-orphan")
    telemetry = db.relationship("TelemetryEvent", backref="learning_path", lazy=True, cascade="all, delete-orphan")
    embeddings = db.relationship("ContentEmbedding", backref="learning_path", lazy=True, cascade="all, delete-orphan")
