from datetime import datetime, timezone
from app.extensions import db
from app.models.learning_path import gen_uuid

def _utcnow():
    return datetime.now(timezone.utc)

class TelemetryEvent(db.Model):
    __tablename__ = "telemetry_events"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    learning_path_id = db.Column(db.String, db.ForeignKey("learning_paths.id"), nullable=False)
    event_type = db.Column(db.String, nullable=False) # LESSON_VIEWED | QUIZ_SUBMITTED | REMEDIATION_TRIGGERED | LESSON_COMPLETED
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    __table_args__ = (
        db.Index('idx_lp_telemetry_created', 'learning_path_id', 'created_at'),
    )
