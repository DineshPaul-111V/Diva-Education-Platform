import os
import secrets
import logging
from datetime import timedelta
from dotenv import load_dotenv

# Ensure .env is loaded whenever Config is imported
load_dotenv()

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class Config:
    raw_secret = os.environ.get("SECRET_KEY", "").strip("\"' \t\n\r")
    if raw_secret:
        SECRET_KEY = raw_secret
    else:
        SECRET_KEY = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY is not set in environment — using a random per-process key. "
            "Sessions will NOT persist across restarts. Set SECRET_KEY in .env for production."
        )
    
    # Database configuration
    raw_db_url = os.environ.get("DATABASE_URL", "").strip("\"' \t\n\r")
    if not raw_db_url:
        default_db = os.path.join(BASE_DIR, "dev.db")
        DATABASE_URL = f"sqlite:///{default_db.replace(chr(92), '/')}"
    elif raw_db_url.startswith("file:"):
        db_path = raw_db_url.replace("file:", "", 1).strip()
        if db_path.startswith("./") or db_path.startswith(".\\"):
            abs_db = os.path.abspath(os.path.join(BASE_DIR, db_path[2:]))
        else:
            abs_db = os.path.abspath(db_path)
        DATABASE_URL = f"sqlite:///{abs_db.replace(chr(92), '/')}"
    elif raw_db_url.startswith("postgres://"):
        DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = raw_db_url
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configurations
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get("PERMANENT_SESSION_LIFETIME_DAYS", 7)))
    
    # Groq & Gemini API configs
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip("\"' \t\n\r")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip("\"' \t\n\r")
    LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile").strip("\"' \t\n\r")
    
    # Mastery Threshold
    MASTERY_THRESHOLD = float(os.environ.get("MASTERY_THRESHOLD", 70.0))

