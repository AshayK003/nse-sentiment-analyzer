"""
Disk cache layer — TTL-based caching with diskcache backend.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional

try:
    import diskcache
    _DISKCACHE_AVAILABLE = True
except ImportError:
    diskcache = None
    _DISKCACHE_AVAILABLE = False

log = logging.getLogger(__name__)

# Global cache instance
_cache: Any = None


def get_cache() -> Any:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None and _DISKCACHE_AVAILABLE:
        try:
            _cache = diskcache.Cache(".price_cache")
        except Exception as e:
            log.warning("Failed to initialize diskcache: %s", e)
            _cache = None
    return _cache


def _make_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """Create a deterministic cache key from function + arguments."""
    # Create a hashable representation
    key_data = {
        "func": f"{func.__module__}.{func.__qualname__}",
        "args": args,
        "kwargs": {k: v for k, v in kwargs.items() if k != "_force_refresh"},
    }
    serialized = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]


def cached(
    ttl_seconds: int = 300,
    key_prefix: str = "",
    backend: str = "disk",
) -> Callable:
    """
    TTL-based cache decorator.

    Args:
        ttl_seconds: Time-to-live in seconds
        key_prefix: Prefix for cache keys (helps with invalidation)
        backend: "disk" or "memory" (memory is process-local)

    Usage:
        @cached(ttl_seconds=300, key_prefix="ohlcv:")
        def fetch_ohlcv(ticker: str, period: str = "1y") -> list[OHLCV]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            force_refresh = kwargs.pop("_force_refresh", False)

            if force_refresh:
                return func(*args, **kwargs)

            # Try cache
            cache = get_cache()
            if cache:
                key = f"{key_prefix}{_make_key(func, args, kwargs)}"
                try:
                    entry_data = cache.get(key)
                    if entry_data:
                        # Check if entry has timestamp and is still valid
                        if isinstance(entry_data, dict) and "timestamp" in entry_data:
                            ts = datetime.fromisoformat(entry_data["timestamp"])
                            ttl = entry_data.get("ttl_seconds", ttl_seconds)
                            if (datetime.now() - ts).total_seconds() < ttl:
                                log.debug("Cache HIT: %s", key)
                                return entry_data["value"]
                        # Expired
                        log.debug("Cache EXPIRED: %s", key)
                        cache.delete(key)
                except Exception as e:
                    log.debug("Cache read error: %s", e)

            # Cache miss or error - call function
            result = func(*args, **kwargs)

            # Store in cache
            if cache and result is not None:
                try:
                    key = f"{key_prefix}{_make_key(func, args, kwargs)}"
                    entry = {
                        "value": result,
                        "timestamp": datetime.now().isoformat(),
                        "ttl_seconds": ttl_seconds,
                    }
                    cache.set(key, entry)
                    log.debug("Cache SET: %s (TTL=%ds)", key, ttl_seconds)
                except Exception as e:
                    log.debug("Cache write error: %s", e)

            return result
        return wrapper
    return decorator


def invalidate(pattern: str = "") -> int:
    """
    Invalidate cache entries matching pattern.

    Args:
        pattern: Key prefix to match (e.g., "ohlcv:" or "news_ticker:RELIANCE")

    Returns:
        Number of entries deleted
    """
    cache = get_cache()
    if not cache:
        return 0

    count = 0
    try:
        if pattern:
            # Iterate and delete matching keys
            for key in list(cache.iterkeys()):
                if isinstance(key, str) and key.startswith(pattern):
                    cache.delete(key)
                    count += 1
        else:
            # Clear all
            cache.clear()
            count = -1  # Unknown
    except Exception as e:
        log.error("Cache invalidation error: %s", e)

    log.info("Cache invalidated: %d entries (pattern=%s)", count, pattern)
    return count


def get_cache_stats() -> dict:
    """Get cache statistics."""
    cache = get_cache()
    if not cache:
        return {"available": False, "entries": 0, "size_mb": 0}

    try:
        stats = cache.stats()
        return {
            "available": True,
            "entries": cache.volume(),
            "size_mb": round(stats.get("size", 0) / (1024 * 1024), 2),
            "hits": stats.get("hits", 0),
            "misses": stats.get("misses", 0),
        }
    except Exception:
        return {"available": True, "entries": 0, "size_mb": 0}


def invalidate_ticker_cache(ticker: str) -> int:
    """Invalidate all cached data for a ticker."""
    ticker = ticker.upper().replace(".NS", "").replace(".BO", "")
    return invalidate(pattern=ticker)


# Simple in-memory TTL cache fallback
class TimedCache:
    """Simple in-memory TTL cache for cases where diskcache isn't available."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str, ttl_seconds: int) -> Any:
        if key in self._store:
            value, timestamp = self._store[key]
            if time.time() - timestamp < ttl_seconds:
                return value
            else:
                del self._store[key]
        return None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.time())

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        self._store.clear()


# Fallback in-memory cache
_memory_cache = TimedCache()


def get_memory_cache() -> TimedCache:
    return _memory_cache