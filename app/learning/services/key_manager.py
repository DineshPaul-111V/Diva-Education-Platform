import time
import logging

logger = logging.getLogger(__name__)

class KeyPool:
    def __init__(self, name: str, keys_str: str):
        self.name = name
        self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.index = 0
        self.cooldowns = {}  # {key: timestamp_when_available}

    def get_key(self) -> str | None:
        if not self.keys:
            return None
        now = time.time()
        available = [k for k in self.keys if self.cooldowns.get(k, 0) <= now]
        if not available:
            logger.warning(f"All keys in {self.name} pool are currently rate-limited!")
            return None
        key = available[self.index % len(available)]
        self.index += 1
        return key

    def mark_rate_limited(self, key: str, cooldown_seconds: int = 60):
        logger.warning(f"Marking {self.name} key as rate-limited for {cooldown_seconds}s")
        self.cooldowns[key] = time.time() + cooldown_seconds
        
    @property
    def has_keys(self) -> bool:
        return len(self.keys) > 0
