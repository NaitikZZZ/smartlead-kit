"""Vercel Blob REST client - thin wrapper so per-run output files can move
off local disk (config.RUNS_DIR) without a JS dependency. Vercel doesn't
publish a plain REST reference for this (the @vercel/blob SDK is the
documented path), so this mirrors the SDK's actual HTTP calls: PUT to
https://vercel.com/api/blob/?pathname=... with the store id (embedded in the
token itself) and API version as headers, GET straight from the blob's own
returned URL with the same bearer token for private access.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import quote

import requests

from . import config

_API_URL = "https://vercel.com/api/blob/"
_API_VERSION = "12"  # BLOB_API_VERSION as of the vercel/storage SDK, July 2026


API_VERSION = _API_VERSION  # exposed so the browser can send the matching x-api-version


def is_configured() -> bool:
    return bool(config.BLOB_READ_WRITE_TOKEN)


def store_id() -> str:
    """Public accessor - the browser needs this for the x-vercel-blob-store-id
    header on a direct-to-Blob upload."""
    return _store_id()


def upload_url_for(pathname: str) -> str:
    """The URL a client-token holder PUTs to (note: distinct from url_for(),
    which is where the blob is READ back from once written)."""
    return f"{_API_URL}?pathname={quote(pathname)}"


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


def create_client_token(pathname: str, *, max_bytes: int, valid_seconds: int = 3600,
                        allowed_content_types: list[str] | None = None) -> str:
    """Mints a short-lived, single-pathname-scoped token so a BROWSER can PUT
    straight to Vercel Blob, skipping our own backend entirely. That matters
    because Vercel caps a serverless function's request body at 4.5MB (hard,
    not configurable) - routing a real Apollo export through /api/runs 413s
    before FastAPI even sees it.

    Generated purely locally - no network call, no Node runtime. The exact
    construction is ported from @vercel/blob's
    generateClientTokenFromReadWriteToken (verified identical in SDK v1.0.0
    and v2.6.1, whose BLOB_API_VERSION 12 matches _API_VERSION above):
        payload = base64(json({pathname, validUntil, ...constraints}))
        secured = hmac_sha256(key=read_write_token, msg=payload).hexdigest()
        token   = "vercel_blob_client_{storeId}_" + base64(f"{secured}.{payload}")
    Note the HMAC order: the read-write token is the KEY, the payload is the
    MESSAGE (easy to invert - the SDK reads createHmac(sha256, token).update(payload)).

    The constraint fields are what the Blob API enforces server-side, so a
    leaked token can only overwrite this one pathname, only up to max_bytes,
    and only until it expires. The SDK's own 30s default validUntil is far too
    short for a multi-MB upload on a slow connection, hence 1 hour here.
    Both constraints were confirmed enforced by live testing: a token scoped
    to one pathname 403s on any other ('"pathname" X does not match the token
    payload'), and exceeding max_bytes 403s too.

    The caller (browser) must PUT to _API_URL?pathname=<pathname> with exactly
    these headers - established empirically, since Vercel documents only the
    JS SDK path:
        authorization:           Bearer <this token>
        x-api-version:           12
        x-vercel-blob-store-id:  <store id>
        x-vercel-blob-access:    private   (required - the store is private,
                                            omitting it fails with "Cannot use
                                            public access on a private store")
        x-content-type:          <mime>
    """
    rw_token = config.require("BLOB_READ_WRITE_TOKEN", config.BLOB_READ_WRITE_TOKEN)
    # Must match JSON.stringify byte-for-byte: compact separators, and OMIT
    # optional keys entirely rather than sending null (JSON.stringify drops
    # undefined values, and sending "onUploadCompleted": null gets the whole
    # token rejected as a "Token mismatch" - confirmed by testing against a
    # reference token generated by the real SDK).
    payload_obj: dict = {
        "pathname": pathname,
        "validUntil": int((time.time() + valid_seconds) * 1000),  # epoch MILLIseconds
        "addRandomSuffix": False,
        "allowOverwrite": True,
        "maximumSizeInBytes": max_bytes,
    }
    if allowed_content_types:
        payload_obj["allowedContentTypes"] = allowed_content_types
    payload = base64.b64encode(json.dumps(payload_obj, separators=(",", ":")).encode()).decode()
    secured = hmac.new(rw_token.encode(), payload.encode(), hashlib.sha256).hexdigest()
    body = base64.b64encode(f"{secured}.{payload}".encode()).decode()
    return f"vercel_blob_client_{_store_id()}_{body}"
