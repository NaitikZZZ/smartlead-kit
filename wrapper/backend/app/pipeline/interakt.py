"""Interakt push for the WhatsApp output file.

Registers/updates each WhatsApp-eligible contact as a tracked Interakt user
via the Track User API (POST /v1/public/track/users/), so they land in
Interakt ready for a template send or automation. Mirrors the email/LinkedIn
side: just as the email file becomes a HubSpot import and the LinkedIn file
becomes a HeyReach list, the WhatsApp file becomes tracked Interakt users.

Same endpoint/auth/payload shape as scripts/interakt_push_leads.py (kept as
a separate manual/dry-run tool); this module is the always-live path wired
into the Confirm & Upload flow alongside HubSpot + HeyReach.
"""
from __future__ import annotations

import time

from .._lazy import pd
import requests

from .. import config

BASE = "https://api.interakt.ai/v1/public"
# Growth plan = 300 req/min; stay well under it. Track User has no batch
# endpoint, so this paces one request at a time (matches interakt_push_leads.py).
_REQUEST_DELAY_SECONDS = 0.25
_MAX_ERRORS_KEPT = 5


def is_configured() -> bool:
    return bool(config.INTERAKT_API_KEY)


def _headers():
    return {"Authorization": f"Basic {config.require('INTERAKT_API_KEY', config.INTERAKT_API_KEY)}",
            "Content-Type": "application/json"}


def _s(v) -> str:
    """Coerce a row field to a stripped string - a source CSV column that's
    blank for every row in a batch gets inferred by pandas as float64, so its
    "empty" cells come back as NaN (a float), not None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _user_payload(row: dict, campaign_title: str) -> dict | None:
    """fullPhoneNumber is the only hard requirement (Interakt identifies a
    tracked user by phone number) - rebuilt from whatsapp_upload.csv's split
    country_code + phone_number columns, since Track User wants one combined
    digits-only number, not the split shape the CSV carries for Interakt's
    own bulk-import template."""
    country_code = _s(row.get("country_code"))
    phone_number = _s(row.get("phone_number"))
    if not phone_number:
        return None
    full_phone = f"{country_code}{phone_number}" if country_code else phone_number

    traits = {}
    name = " ".join(p for p in (_s(row.get("first_name")), _s(row.get("last_name"))) if p)
    if name:
        traits["name"] = name
    if _s(row.get("email")):
        traits["email"] = _s(row.get("email"))
    if _s(row.get("company_name")):
        traits["company"] = _s(row.get("company_name"))
    if _s(row.get("job_title")):
        traits["job_title"] = _s(row.get("job_title"))

    payload = {"fullPhoneNumber": full_phone, "traits": traits}
    if campaign_title:
        payload["tags"] = [campaign_title]
    return payload


def push_users(whatsapp_rows: list[dict], campaign_title: str) -> dict:
    """Tracks each WhatsApp-eligible contact as an Interakt user. Returns a
    status dict. Never raises into the caller - an Interakt failure shouldn't
    sink the HubSpot import that already succeeded."""
    if not is_configured():
        return {"status": "not_configured", "pushed": 0, "eligible": len(whatsapp_rows),
                "message": "INTERAKT_API_KEY not set - WhatsApp CSV is downloadable for manual import."}

    payloads = [p for p in (_user_payload(r, campaign_title) for r in whatsapp_rows) if p]
    if not payloads:
        return {"status": "no_leads", "pushed": 0, "eligible": len(whatsapp_rows),
                "message": "No phone numbers to push."}

    pushed = failed = 0
    errors = []
    for i, payload in enumerate(payloads):
        try:
            r = requests.post(f"{BASE}/track/users/", headers=_headers(), json=payload, timeout=15)
            if r.ok:
                pushed += 1
            else:
                failed += 1
                if len(errors) < _MAX_ERRORS_KEPT:
                    errors.append(f"{payload['fullPhoneNumber']}: {r.status_code} {r.text[:200]}")
        except requests.RequestException as e:
            failed += 1
            if len(errors) < _MAX_ERRORS_KEPT:
                errors.append(f"{payload['fullPhoneNumber']}: {e}")
        if i < len(payloads) - 1:
            time.sleep(_REQUEST_DELAY_SECONDS)

    result = {"status": "pushed" if pushed else "error", "pushed": pushed, "failed": failed,
               "eligible": len(whatsapp_rows)}
    if errors:
        result["errors"] = errors
    return result
