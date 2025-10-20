"""
Redis cache utilities for performance optimization
"""

import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import redis
from redis.exceptions import RedisError
from restaurant_inventory.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Redis client
try:
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    # Test connection
    redis_client.ping()
    logger.info(f"✓ Redis connected: {settings.REDIS_URL}")
except RedisError as e:
    logger.warning(f"⚠ Redis connection failed: {e}. Caching disabled.")
    redis_client = None


class CacheManager:
    """Manage Redis caching operations"""

    def __init__(self, client: Optional[redis.Redis] = None):
        self.client = client or redis_client
        self.enabled = self.client is not None

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled:
            return None

        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache HIT: {key}")
                return json.loads(value)
            logger.debug(f"Cache MISS: {key}")
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Cache get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL (time-to-live)

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (default: 300 = 5 minutes)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled:
            return False

        try:
            result = self.client.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return bool(result)
        except RedisError as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern

        Args:
            pattern: Redis key pattern (e.g., "dashboard:*")

        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0

        try:
            keys = self.client.keys(pattern)
            if keys:
                deleted = self.client.delete(*keys)
                logger.info(f"Cache DELETE pattern '{pattern}': {deleted} keys")
                return deleted
            return 0
        except RedisError as e:
            logger.error(f"Cache delete pattern error: {e}")
            return 0

    def clear_all(self) -> bool:
        """Clear entire cache (use with caution!)"""
        if not self.enabled:
            return False

        try:
            self.client.flushdb()
            logger.warning("Cache CLEARED: All keys deleted")
            return True
        except RedisError as e:
            logger.error(f"Cache clear error: {e}")
            return False

    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False}

        try:
            info = self.client.info("stats")
            return {
                "enabled": True,
                "keys": self.client.dbsize(),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except RedisError as e:
            logger.error(f"Cache stats error: {e}")
            return {"enabled": True, "error": str(e)}

    @staticmethod
    def _calculate_hit_rate(hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


def make_cache_key(*args, **kwargs) -> str:
    """
    Generate a cache key from arguments

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        SHA256 hash of arguments as cache key
    """
    # Create a string representation of all arguments
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    key_string = ":".join(key_parts)

    # Hash it for consistent key length
    return hashlib.sha256(key_string.encode()).hexdigest()


def cached(prefix: str, ttl: int = 300):
    """
    Decorator to cache function results

    Args:
        prefix: Cache key prefix (e.g., "dashboard", "reports")
        ttl: Time to live in seconds (default: 300 = 5 minutes)

    Usage:
        @cached(prefix="dashboard", ttl=300)
        async def get_dashboard_data(location_id: int):
            return expensive_computation()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache = CacheManager()

            # Generate cache key
            cache_key = f"{prefix}:{make_cache_key(*args, **kwargs)}"

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            cache.set(cache_key, result, ttl)

            return result
        return wrapper
    return decorator


# Global cache manager instance
cache = CacheManager()


# Cache key patterns for different features
class CacheKeys:
    """Standard cache key patterns"""

    # Dashboard analytics cache
    DASHBOARD_ANALYTICS = "dashboard:analytics:{location_id}:{date}"

    # Reports cache
    REPORTS = "reports:{report_type}:{location_id}:{date_range}"

    # Inventory cache
    INVENTORY = "inventory:{location_id}"

    # POS sales cache
    POS_SALES = "pos:sales:{location_id}:{date}"

    @staticmethod
    def dashboard_analytics(location_id: Optional[int] = None, date: str = None) -> str:
        """Generate dashboard analytics cache key"""
        loc = location_id or "all"
        dt = date or "today"
        return f"dashboard:analytics:{loc}:{dt}"

    @staticmethod
    def clear_dashboard_cache():
        """Clear all dashboard-related cache keys"""
        return cache.delete_pattern("dashboard:*")

    @staticmethod
    def clear_inventory_cache(location_id: Optional[int] = None):
        """Clear inventory cache for location or all locations"""
        pattern = f"inventory:{location_id or '*'}"
        return cache.delete_pattern(pattern)
