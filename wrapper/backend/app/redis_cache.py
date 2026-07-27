"""Upstash Redis REST client - thin key/value + chunked-blob helpers so the
local file-based caches (domain lookups, email/phone/person reveal results,
HubSpot exclusion-list snapshot, association dropdown lists) can move off
disk without changing their calling code's shape. Uses Upstash's REST API
(plain HTTPS, not a TCP redis client) since that's what a Vercel serverless
function can reliably use.

Chunking exists because 2 of these caches (the ~120k-record HubSpot
exclusion-list snapshot and the Apollo person-enrichment cache) run into the
tens of MB as one JSON blob - comfortably past Upstash's per-request payload
limit. Splitting the serialized JSON string across multiple keys keeps every
request small while the CALLING code still gets back the exact same Python
dict/list it always did - no changes needed to any cache-matching logic.
"""
from __future__ import annotations

import json

import requests

from . import config

_CHUNK_SIZE = 900_000  # bytes - safely under Upstash's ~1MB REST payload limit


def is_configured() -> bool:
    return bool(config.UPSTASH_REDIS_REST_URL and config.UPSTASH_REDIS_REST_TOKEN)


def _headers():
    token = config.require("UPSTASH_REDIS_REST_TOKEN", config.UPSTASH_REDIS_REST_TOKEN)
    return {"Authorization": f"Bearer {token}"}


def _base_url():
    return config.require("UPSTASH_REDIS_REST_URL", config.UPSTASH_REDIS_REST_URL)


def get_raw(key: str) -> str | None:
    r = requests.get(f"{_base_url()}/get/{key}", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json().get("result")


def set_raw(key: str, value: str) -> None:
    r = requests.post(f"{_base_url()}/set/{key}", headers=_headers(), data=value.encode("utf-8"), timeout=15)
    r.raise_for_status()


def get_json(key: str):
    raw = get_raw(key)
    return json.loads(raw) if raw is not None else None


def set_json(key: str, value) -> None:
    set_raw(key, json.dumps(value))


def _pipeline(commands: list[list[str]]) -> list:
    """Batches multiple Redis commands into a single HTTP round-trip via
    Upstash's /pipeline endpoint - one request/response regardless of how
    many chunks, instead of one request per chunk. Confirmed by hand: 26
    sequential chunk GETs (the real exclusion-cache chunk count) took ~84s;
    switching to this cut it to about the same time as a single GET."""
    if not commands:
        return []
    r = requests.post(f"{_base_url()}/pipeline", headers=_headers(), json=commands, timeout=30)
    r.raise_for_status()
    return [item.get("result") for item in r.json()]


def get_json_chunked(base_key: str):
    """For values that may exceed Upstash's single-request payload limit."""
    meta = get_json(f"{base_key}:meta")
    if meta is None:
        return None
    results = _pipeline([["GET", f"{base_key}:{i}"] for i in range(meta["chunks"])])
    return json.loads("".join(r or "" for r in results))


def set_json_chunked(base_key: str, value) -> None:
    s = json.dumps(value)
    chunks = [s[i:i + _CHUNK_SIZE] for i in range(0, len(s), _CHUNK_SIZE)] or [""]
    _pipeline([["SET", f"{base_key}:{i}", chunk] for i, chunk in enumerate(chunks)])
    set_json(f"{base_key}:meta", {"chunks": len(chunks)})
