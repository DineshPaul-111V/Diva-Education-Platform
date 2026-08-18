import json
import math
import re
import logging
from app.extensions import db
from app.models.content_embedding import ContentEmbedding

logger = logging.getLogger(__name__)

def generate_local_embedding(text: str, dimension: int = 128) -> list:
    """
    Computes a lightweight deterministic text embedding vector (dimension 128)
    for fast, accurate per-student RAG retrieval across all languages.
    """
    vector = [0.0] * dimension
    tokens = [t.strip() for t in text.lower().split() if len(t.strip()) > 1]
    
    if not tokens:
        return vector
        
    for token in tokens:
        hash_val = 0
        for char in token:
            hash_val = (hash_val << 5) - hash_val + ord(char)
            # Simulate 32-bit integer overflow in JS `hash |= 0`
            hash_val = hash_val & 0xffffffff
            if hash_val & 0x80000000:
                hash_val = -((hash_val ^ 0xffffffff) + 1)
        
        idx = abs(hash_val) % dimension
        vector[idx] += 1.0 / math.sqrt(len(tokens))
        
    # Normalize vector to unit length
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        return [v / norm for v in vector]
    return vector

def cosine_similarity(a: list, b: list) -> float:
    """
    Calculates cosine similarity between two float vectors.
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a)
    norm_b = sum(y * y for y in b)
    denominator = math.sqrt(norm_a) * math.sqrt(norm_b)
    return dot_product / denominator if denominator != 0 else 0.0

def store_student_embedding(learning_path_id: str, source_type: str, source_ref_id: str, chunk_text: str):
    """
    Stores a chunk into the student's personal RAG corpus.
    """
    try:
        embedding = generate_local_embedding(chunk_text)
        embedding_record = ContentEmbedding(
            learning_path_id=learning_path_id,
            source_type=source_type,
            source_ref_id=source_ref_id,
            chunk_text=chunk_text,
            embedding_json=json.dumps(embedding)
        )
        db.session.add(embedding_record)
        db.session.commit()
    except Exception as err:
        db.session.rollback()
        logger.warning("Failed to store student embedding chunk for %s: %s", source_ref_id, err)

def retrieve_student_context(learning_path_id: str, query_text: str, top_k: int = 5) -> list:
    """
    Retrieves the top-k most relevant chunks for this student's specific learning path.
    Strictly scoped to WHERE learningPathId = current.
    """
    try:
        query_vector = generate_local_embedding(query_text)
        stored = ContentEmbedding.query.filter_by(learning_path_id=learning_path_id).all()
        
        if not stored:
            return []
            
        scored = []
        for item in stored:
            try:
                item_vec = json.loads(item.embedding_json)
                score = cosine_similarity(query_vector, item_vec)
            except Exception:
                score = 0.0
            scored.append({
                "chunk": f"[{item.source_type}] {item.chunk_text}",
                "score": score
            })
            
        scored.sort(key=lambda x: x["score"], reverse=True)
        return [s["chunk"] for s in scored[:top_k]]
    except Exception as err:
        logger.warning("Failed to retrieve student context for path %s: %s", learning_path_id, err)
        return []

import io
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

def process_uploaded_pdf(learning_path_id: str, file_stream: bytes, filename: str):
    """Parses a PDF, chunks it, and stores embeddings for the student's learning path."""
    if not PyPDF2:
        logger.error("PyPDF2 is not installed")
        return
        
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_stream))
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
                
        # Simple chunking by words
        words = text.split()
        chunk_size = 200
        overlap = 50
        chunks = []
        
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i+chunk_size])
            if chunk.strip():
                chunks.append(chunk)
            i += (chunk_size - overlap)
            
        for idx, chunk in enumerate(chunks):
            store_student_embedding(
                learning_path_id,
                "DOCUMENT",
                f"{filename}_chunk_{idx}",
                chunk
            )
        logger.info(f"Processed PDF {filename} into {len(chunks)} chunks.")
    except Exception as err:
        logger.error(f"Failed to process PDF {filename}: {err}")
