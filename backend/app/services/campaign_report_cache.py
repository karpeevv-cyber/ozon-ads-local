from __future__ import annotations

import time
from threading import RLock
from typing import Any

CACHE_TTL_SECONDS = 60 * 60

_lock = RLock()
_cache: dict[tuple[str, str, str, float], tuple[float, dict[str, Any]]] = {}


def get_campaign_report_cache(key: tuple[str, str, str, float]) -> dict[str, Any] | None:
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at >= CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        return dict(payload)


def set_campaign_report_cache(key: tuple[str, str, str, float], payload: dict[str, Any]) -> None:
    with _lock:
        _cache[key] = (time.monotonic(), dict(payload))


def invalidate_campaign_report_cache(company: str | None = None) -> None:
    with _lock:
        if not company:
            _cache.clear()
            return
        normalized = str(company)
        for key in list(_cache.keys()):
            if key[0] == normalized:
                _cache.pop(key, None)
