import uuid
from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db

def _utcnow():
    return datetime.now(timezone.utc)

def gen_uuid():
    return str(uuid.uuid4())

class User(db.Model, UserMixin):
    __tablename__ = "users"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    email = db.Column(db.String, unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String, nullable=False)
    name = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    
    learning_paths = db.relationship("LearningPath", backref="user", lazy=True, cascade="all, delete-orphan")
    login_attempts = db.relationship("LoginAttempt", backref="user", lazy=True, cascade="all, delete-orphan")
    progress = db.relationship("StudentProgress", backref="user", uselist=False, lazy=True, cascade="all, delete-orphan")


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)
    email = db.Column(db.String, nullable=False, index=True)
    success = db.Column(db.Boolean, nullable=False)
    ip = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
