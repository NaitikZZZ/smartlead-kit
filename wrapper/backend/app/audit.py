"""Append-only record of who did what, in an Upstash Redis list (newest
first, capped). Read via GET /api/admin/audit. log() never raises - a Redis
hiccup must not fail the action being recorded."""
from __future__ import annotations

import json
import logging
import time

from . import redis_cache

logger = logging.getLogger(__name__)

_KEY = "audit_log"
_MAX_ENTRIES = 5000


def log(name: str, action: str, ip: str = "", **details) -> None:
    entry = {"ts": time.time(), "name": name, "ip": ip, "action": action, **details}
    logger.info(f"audit {entry}")
    if not redis_cache.is_configured():
        return
    try:
        redis_cache._pipeline([
            ["LPUSH", _KEY, json.dumps(entry, default=str)],
            ["LTRIM", _KEY, "0", str(_MAX_ENTRIES - 1)],
        ])
    except Exception as e:
        logger.warning(f"audit log write failed: {e}")


def recent(limit: int = 200) -> list[dict]:
    if not redis_cache.is_configured():
        return []
    rows = redis_cache._pipeline([["LRANGE", _KEY, "0", str(max(1, limit) - 1)]])[0] or []
    return [json.loads(r) for r in rows]
