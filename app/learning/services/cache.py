import hashlib
import json
import logging
from cachetools import TTLCache
from app.config import Config

logger = logging.getLogger(__name__)

# Cache size: 1000 items, TTL from config
llm_cache = TTLCache(maxsize=1000, ttl=Config.LLM_CACHE_TTL)

def _generate_cache_key(prompt: str, schema_name: str, model_type: str) -> str:
    """Generate a consistent hash for a cache key based on prompt and schema."""
    key_string = f"{prompt}:{schema_name}:{model_type}"
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()

def get_cached_response(prompt: str, schema_name: str, model_type: str):
    cache_key = _generate_cache_key(prompt, schema_name, model_type)
    if cache_key in llm_cache:
        logger.info(f"LLM Cache hit for {model_type} / {schema_name}")
        return llm_cache[cache_key]
    return None

def set_cached_response(prompt: str, schema_name: str, model_type: str, response):
    cache_key = _generate_cache_key(prompt, schema_name, model_type)
    llm_cache[cache_key] = response
