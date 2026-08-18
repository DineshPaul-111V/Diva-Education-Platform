from datetime import datetime, timezone
from app.extensions import db
from app.models.learning_path import gen_uuid

def _utcnow():
    return datetime.now(timezone.utc)

class ContentEmbedding(db.Model):
    __tablename__ = "content_embeddings"
    
    id = db.Column(db.String, primary_key=True, default=gen_uuid)
    learning_path_id = db.Column(db.String, db.ForeignKey("learning_paths.id"), nullable=False)
    source_type = db.Column(db.String, nullable=False) # LESSON | MISCONCEPTION | REMEDIATION
    source_ref_id = db.Column(db.String, nullable=False) # lessonId or conceptId
    chunk_text = db.Column(db.Text, nullable=False)
    embedding_json = db.Column(db.Text, nullable=False) # JSON serialized float array
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        db.Index('idx_lp_embedding', 'learning_path_id'),
    )
