import json
import os
import time
import threading
import logging
from app.config import BASE_DIR

logger = logging.getLogger(__name__)

class FallbackStateManager:
    _lock = threading.Lock()
    _file_path = os.path.join(BASE_DIR, "fallback_state.json")

    @classmethod
    def log_fallback_event(cls, provider: str, model: str, error: str, prompt_summary: str):
        """
        Thread-safely logs a fallback event to a JSON file.
        """
        event = {
            "timestamp": time.time(),
            "time_str": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            "provider": provider,
            "model": model,
            "error": error,
            "prompt_summary": prompt_summary
        }
        
        with cls._lock:
            try:
                data = []
                if os.path.exists(cls._file_path):
                    try:
                        with open(cls._file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        data = []

                data.append(event)
                
                with open(cls._file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                    
            except Exception as e:
                logger.error(f"Failed to log fallback event: {str(e)}")
