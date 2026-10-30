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

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .._lazy import pd
import requests

from .. import config
from .hubspot_retry import request_with_retry
from .hubspot_import import logger

BASE = "https://api.interakt.ai/v1/public"
# Growth plan = 300 req/min; stay well under it. Track User has no batch
# endpoint, so requests go out concurrently but are paced by ONE shared clock:
# a request starts at most every _REQUEST_INTERVAL_SECONDS (~272/min) no matter
# how many workers are in flight. The workers only hide per-request latency.
_REQUEST_INTERVAL_SECONDS = 0.22
_WORKERS = 8
_MAX_ERRORS_KEPT = 5
PUSH_CHUNK_SIZE = 600  # contacts per Inngest step: ~135s at the paced rate, under the 300s limit


class _Pacer:
    def __init__(self, interval: float):
        self._interval = interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            time.sleep(slot - now)


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


def check_template(name: str) -> dict:
    """Look up an existing Interakt template by name and report its approval
    status. Interakt's public API has no endpoint to submit a NEW template for
    WABA approval (confirmed against scripts/interakt_send_template.py, the
    only other caller of this read-only endpoint) - that has to happen by hand
    in the Interakt dashboard. So Copy Push's Interakt leg can only ever
    check readiness, never "push" a template into existence. Never raises."""
    if not is_configured():
        return {"status": "not_configured", "message": "INTERAKT_API_KEY not set"}
    try:
        r = requests.get(f"{BASE}/track/organization/templates", headers=_headers(),
                         params={"offset": 0, "template_name": name}, timeout=15)
        if not r.ok:
            return {"status": "error", "message": f"{r.status_code} {r.text[:300]}"}
        templates = (r.json().get("results") or {}).get("templates", [])
        match = next((t for t in templates if t.get("name") == name), None)
        if not match:
            return {
                "status": "not_found", "template_name": name,
                "message": f"No template named '{name}' found in Interakt. It needs to be created and "
                           "submitted for WABA approval in the Interakt dashboard first - this can't be "
                           "done via API. Re-check once it's been submitted.",
            }
        approved = str(match.get("approval_status", "")).lower() in ("approved", "active")
        return {
            "status": "approved" if approved else "pending_approval",
            "template_name": name, "approval_status": match.get("approval_status"),
            "category": match.get("category"),
            "message": ("Template is approved and ready - sending it is a separate, explicit action "
                        "(never automatic).") if approved else
                       f"Template exists but isn't approved yet (status: {match.get('approval_status')}). "
                       "Wait for WABA approval before sending.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Interakt template check failed: {e}"}


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

    pacer = _Pacer(_REQUEST_INTERVAL_SECONDS)
    headers = _headers()

    def _push_one(payload: dict) -> str | None:
        """None on success, else the error text."""
        pacer.wait()
        try:
            r = request_with_retry("POST", f"{BASE}/track/users/", headers=headers, json=payload, timeout=15)
            return None if r.ok else f"{payload['fullPhoneNumber']}: {r.status_code} {r.text[:200]}"
        except requests.RequestException as e:
            return f"{payload['fullPhoneNumber']}: {e}"

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        outcomes = list(pool.map(_push_one, payloads))
    errors_all = [o for o in outcomes if o]
    pushed, failed = len(outcomes) - len(errors_all), len(errors_all)
    errors = errors_all[:_MAX_ERRORS_KEPT]
    logger.info("interakt push: %d contacts, %d failed, %.1fs", len(payloads), failed, time.monotonic() - t0)

    result = {"status": "pushed" if pushed else "error", "pushed": pushed, "failed": failed,
               "eligible": len(whatsapp_rows)}
    if errors:
        result["errors"] = errors
    return result


def merge_results(parts: list[dict]) -> dict:
    """Combines the per-chunk push_users results of one import into one."""
    if len(parts) == 1:
        return parts[0]
    pushed = sum(p.get("pushed", 0) for p in parts)
    merged = {"status": "pushed" if pushed else parts[0]["status"], "pushed": pushed,
              "failed": sum(p.get("failed", 0) for p in parts),
              "eligible": sum(p.get("eligible", 0) for p in parts)}
    errors = [e for p in parts for e in p.get("errors", [])][:_MAX_ERRORS_KEPT]
    if errors:
        merged["errors"] = errors
    return merged
