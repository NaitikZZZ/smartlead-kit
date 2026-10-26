"""Per-person password login. Each teammate has their own password; the name
it maps to is what gets stamped on audit-log entries and on the HubSpot note,
so there's a record of who ran what. Passwords arrive in the X-App-Password
header on every API call and are compared by SHA-256 against APP_USERS (see
config.py), so the plain passwords never live on the server.

Fails closed on Vercel (VERCEL=1) if APP_USERS is unset; outside Vercel it
lets requests through as "local-dev" so local development needs no setup."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

from . import config


@dataclass
class Actor:
    name: str
    ip: str


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _users() -> dict[str, str]:
    try:
        return json.loads(config.APP_USERS) if config.APP_USERS else {}
    except json.JSONDecodeError:
        return {}


def require_user(request: Request, x_app_password: Optional[str] = Header(None)) -> Actor:
    users = _users()
    if not users:
        if os.environ.get("VERCEL"):
            raise HTTPException(401, "Login is not configured on the server")
        return Actor("local-dev", _client_ip(request))
    if not x_app_password:
        raise HTTPException(401, "Password required")
    digest = hashlib.sha256(x_app_password.encode()).hexdigest()
    for known_digest, name in users.items():
        if hmac.compare_digest(digest, known_digest):
            return Actor(name, _client_ip(request))
    raise HTTPException(401, "Invalid password")


def require_admin(request: Request, x_app_password: Optional[str] = Header(None)) -> Actor:
    actor = require_user(request, x_app_password)
    if not config.ADMIN_NAME or actor.name != config.ADMIN_NAME:
        raise HTTPException(403, "Admin only")
    return actor
