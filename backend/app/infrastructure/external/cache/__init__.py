from functools import lru_cache

from app.infrastructure.external.cache.redis_cache import RedisCache


@lru_cache
def get_cache():
    """Get cache implementation"""
    return RedisCache()

__all__ = ['RedisCache', 'get_cache']
