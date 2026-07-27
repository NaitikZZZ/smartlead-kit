"""Vercel Blob REST client - thin wrapper so per-run output files can move
off local disk (config.RUNS_DIR) without a JS dependency. Vercel doesn't
publish a plain REST reference for this (the @vercel/blob SDK is the
documented path), so this mirrors the SDK's actual HTTP calls: PUT to
https://vercel.com/api/blob/?pathname=... with the store id (embedded in the
token itself) and API version as headers, GET straight from the blob's own
returned URL with the same bearer token for private access.
"""
from __future__ import annotations

import requests

from . import config

_API_URL = "https://vercel.com/api/blob/"
_API_VERSION = "12"  # BLOB_API_VERSION as of the vercel/storage SDK, July 2026


def is_configured() -> bool:
    return bool(config.BLOB_READ_WRITE_TOKEN)


def _store_id() -> str:
    token = config.require("BLOB_READ_WRITE_TOKEN", config.BLOB_READ_WRITE_TOKEN)
    parts = token.split("_")
    return parts[3] if len(parts) > 3 else ""


def _headers(extra: dict | None = None) -> dict:
    token = config.require("BLOB_READ_WRITE_TOKEN", config.BLOB_READ_WRITE_TOKEN)
    headers = {
        "authorization": f"Bearer {token}",
        "x-api-version": _API_VERSION,
        "x-vercel-blob-store-id": _store_id(),
    }
    if extra:
        headers.update(extra)
    return headers


def put(pathname: str, data: bytes | str, content_type: str | None = None) -> dict:
    """Uploads (or overwrites) a private blob at the given pathname. Returns
    the API response dict - notably `url`, which is what get()/downstream
    code should store to fetch it back later."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    headers = _headers({
        "x-vercel-blob-access": "private",
        "x-add-random-suffix": "0",
        "x-allow-overwrite": "1",
    })
    if content_type:
        headers["x-content-type"] = content_type
    r = requests.put(_API_URL, params={"pathname": pathname}, headers=headers, data=data, timeout=60)
    r.raise_for_status()
    return r.json()


def get(url: str) -> bytes:
    """Fetches a private blob's content given a blob URL (either returned by
    put(), or reconstructed via url_for() - both resolve to the same file,
    confirmed by testing: the URL is fully deterministic from store id +
    pathname, so callers never need to persist what put() returned)."""
    token = config.require("BLOB_READ_WRITE_TOKEN", config.BLOB_READ_WRITE_TOKEN)
    r = requests.get(url, headers={"authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    return r.content


def url_for(pathname: str) -> str:
    """Deterministically reconstructs a private blob's URL from its pathname -
    no need to persist what put() returned anywhere."""
    return f"https://{_store_id().lower()}.private.blob.vercel-storage.com/{pathname}"


def exists(pathname: str) -> bool:
    token = config.require("BLOB_READ_WRITE_TOKEN", config.BLOB_READ_WRITE_TOKEN)
    r = requests.head(url_for(pathname), headers={"authorization": f"Bearer {token}"}, timeout=15)
    return r.status_code == 200
