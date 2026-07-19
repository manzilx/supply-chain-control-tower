"""Tiny in-process TTL cache.

Single-worker (UVICORN_WORKERS=1) means a plain dict + monotonic clock is
enough — no Redis, no thread locks. Use sparingly: only for read paths that
fan out across the planning/sourcing stores and recompute the same answer
hundreds of times per session (portfolio summary, progress lists, etc.).

Usage:
    @ttl_cache(ttl_seconds=15)
    def expensive(tenant_id: str) -> Thing:
        ...

Invalidation is time-based only. Hand-written writes (create_pr, etc.) accept
the brief staleness — the cache is small (seconds) and the demo data is
generally read-heavy.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Dict, List, Tuple

# Every ttl_cache wrapper registers its invalidate() here so write paths can
# bust the whole derived-analytics layer in one call (see invalidate_all).
_REGISTRY: List[Callable[[], None]] = []


def ttl_cache(ttl_seconds: float = 10.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        store: Dict[Tuple, Tuple[float, Any]] = {}

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            hit = store.get(key)
            if hit is not None and (now - hit[0]) < ttl_seconds:
                return hit[1]
            value = fn(*args, **kwargs)
            store[key] = (now, value)
            return value

        def invalidate() -> None:
            store.clear()

        wrapper.invalidate = invalidate  # type: ignore[attr-defined]
        _REGISTRY.append(invalidate)
        return wrapper

    return decorator


def invalidate_all() -> None:
    """Bust every ttl_cache in the process.

    Called by write paths (PR/RFQ/quote/award, BOM upload, vendor add,
    approval decision, shipment event, ingest commit) so cached analytics
    never serve stale data after a mutation. Cheap: just clears dicts.
    """
    for inv in _REGISTRY:
        inv()


def invalidates_cache(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate a mutator so the analytics caches are busted AFTER it runs.

    Firing in a `finally` (post-write) instead of inline at function start
    closes the stale-read window: previously a read landing between the
    start-of-function invalidate and the actual store write could re-populate
    the cache with pre-mutation data, which then served until TTL expiry.
    Running invalidation after the body guarantees the next read recomputes
    against the committed state. Also covers early-return paths (harmless
    extra clear) and exceptions (cache cleared even on partial writes).
    """
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        finally:
            invalidate_all()

    return wrapper
