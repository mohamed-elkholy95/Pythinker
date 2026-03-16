import threading
from functools import lru_cache

from app.infrastructure.external.cache.redis_cache import RedisCache

_get_cache_init_lock = threading.Lock()


@lru_cache
def get_cache():
    """Get cache implementation"""
    with _get_cache_init_lock:
        return RedisCache()


__all__ = ["RedisCache", "get_cache"]
