"""
Redis Cache Utility Module

Provides caching functionality for frequently accessed data.
Supports automatic JSON serialization and TTL-based expiration.

Usage:
    from src.cache import cache_get, cache_set, cache_delete

    # Store value with 5-minute TTL
    cache_set("odds:2025012506010911", odds_data, ttl=300)

    # Retrieve value
    odds = cache_get("odds:2025012506010911")

    # Delete value
    cache_delete("odds:2025012506010911")

Cache Key Conventions:
    - odds:{race_id} - Race odds (TTL: 60s)
    - bias:{date} - Daily track bias (TTL: 3600s)
    - code:{table} - Code master data (TTL: 86400s)
    - race:{race_id} - Race metadata (TTL: 300s)
"""

import json
import logging
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Redis client singleton
_redis_client = None
_redis_available = False


def _get_redis_client():
    """Get or create Redis client singleton."""
    global _redis_client, _redis_available

    if _redis_client is not None:
        return _redis_client if _redis_available else None

    try:
        from src.settings import settings

        if not settings.redis_enabled:
            logger.debug("Redis caching is disabled")
            _redis_available = False
            return None

        import redis

        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Test connection
        _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis connected: {settings.redis_url}")
        return _redis_client

    except ImportError:
        logger.debug("redis package not installed, caching disabled")
        _redis_available = False
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        _redis_available = False
        return None


def cache_get(key: str) -> Any | None:
    """
    Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value (JSON deserialized) or None if not found
    """
    client = _get_redis_client()
    if not client:
        return None

    try:
        data = client.get(key)
        if data is not None:
            logger.debug(f"Cache hit: {key}")
            return json.loads(data)
        logger.debug(f"Cache miss: {key}")
        return None
    except Exception as e:
        logger.warning(f"Cache get error: {key}, {e}")
        return None


def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set value in cache with TTL.

    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time-to-live in seconds (default: 300s = 5 minutes)

    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        data = json.dumps(value, ensure_ascii=False, default=str)
        client.setex(key, ttl, data)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Cache set error: {key}, {e}")
        return False


def cache_delete(key: str) -> bool:
    """
    Delete value from cache.

    Args:
        key: Cache key

    Returns:
        True if deleted, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        result = client.delete(key)
        logger.debug(f"Cache delete: {key} (deleted: {result})")
        return result > 0
    except Exception as e:
        logger.warning(f"Cache delete error: {key}, {e}")
        return False


def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching pattern.

    Args:
        pattern: Redis pattern (e.g., "odds:*")

    Returns:
        Number of deleted keys
    """
    client = _get_redis_client()
    if not client:
        return 0

    try:
        keys = list(client.scan_iter(match=pattern))
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"Cache pattern delete: {pattern} (deleted: {deleted})")
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"Cache pattern delete error: {pattern}, {e}")
        return 0


def cached(key_prefix: str, ttl: int = 300):
    """
    Decorator for caching function results.

    Args:
        key_prefix: Cache key prefix (e.g., "odds")
        ttl: Time-to-live in seconds

    Usage:
        @cached("race", ttl=300)
        def get_race_data(race_id: str):
            # Expensive operation
            return data

    The cache key will be: "{key_prefix}:{first_arg}"
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from first positional argument
            if args:
                cache_key = f"{key_prefix}:{args[0]}"
            else:
                # Fallback to function name if no args
                cache_key = f"{key_prefix}:{func.__name__}"

            # Try cache first
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function
            result = func(*args, **kwargs)

            # Cache result
            if result is not None:
                cache_set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def async_cached(key_prefix: str, ttl: int = 300):
    """
    Decorator for caching async function results.

    Same as @cached but for async functions.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if args:
                cache_key = f"{key_prefix}:{args[0]}"
            else:
                cache_key = f"{key_prefix}:{func.__name__}"

            cached_value = cache_get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            if result is not None:
                cache_set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


# =============================================================================
# Predefined TTL Constants
# =============================================================================

TTL_ODDS = 60  # Odds: 1 minute (changes frequently)
TTL_RACE = 300  # Race metadata: 5 minutes
TTL_BIAS = 3600  # Daily bias: 1 hour
TTL_CODE_MASTER = 86400  # Code master: 24 hours
TTL_PREDICTION = 1800  # Predictions: 30 minutes


if __name__ == "__main__":
    # Test cache functionality
    import os

    os.environ["REDIS_ENABLED"] = "true"

    print("Testing cache operations...")

    # Test set/get
    test_data = {"horse": "テスト馬", "odds": 3.5}
    if cache_set("test:key", test_data, ttl=60):
        print("Set: OK")
        result = cache_get("test:key")
        print(f"Get: {result}")
        cache_delete("test:key")
        print("Delete: OK")
    else:
        print("Redis not available, caching disabled")
