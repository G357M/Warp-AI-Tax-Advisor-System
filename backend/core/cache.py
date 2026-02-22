"""
Redis cache connection and utilities.
"""
import json
from typing import Any, Optional
import redis
from redis import Redis

from core.config import settings


# Redis client
redis_client: Optional[Redis] = None


def get_redis() -> Redis:
    """Get Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8"
        )
    return redis_client


def cache_get(key: str) -> Optional[Any]:
    """
    Get value from cache.
    
    Args:
        key: Cache key
        
    Returns:
        Cached value or None if not found
    """
    if not settings.CACHE_ENABLED:
        return None
        
    try:
        client = get_redis()
        value = client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        print(f"Cache get error: {e}")
    return None


def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """
    Set value in cache.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds (optional)
        
    Returns:
        True if successful, False otherwise
    """
    if not settings.CACHE_ENABLED:
        return False
        
    try:
        client = get_redis()
        serialized = json.dumps(value)
        if ttl:
            client.setex(key, ttl, serialized)
        else:
            client.set(key, serialized)
        return True
    except Exception as e:
        print(f"Cache set error: {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete value from cache.
    
    Args:
        key: Cache key
        
    Returns:
        True if successful, False otherwise
    """
    if not settings.CACHE_ENABLED:
        return False
        
    try:
        client = get_redis()
        client.delete(key)
        return True
    except Exception as e:
        print(f"Cache delete error: {e}")
        return False


def cache_clear_pattern(pattern: str) -> int:
    """
    Clear all keys matching pattern.
    
    Args:
        pattern: Redis key pattern (e.g., "user:*")
        
    Returns:
        Number of keys deleted
    """
    if not settings.CACHE_ENABLED:
        return 0
        
    try:
        client = get_redis()
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
        return 0
    except Exception as e:
        print(f"Cache clear pattern error: {e}")
        return 0


class Cache:
    """Cache wrapper with async methods for health checks."""
    
    async def ping(self) -> bool:
        """Ping Redis to check if it's alive."""
        try:
            client = get_redis()
            return client.ping()
        except Exception:
            return False


# Global cache instance
cache = Cache()
