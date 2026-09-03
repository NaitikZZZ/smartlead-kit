"""HeyReach push for the LinkedIn output file.

Creates a HeyReach lead list named after the campaign and adds the LinkedIn
contacts to it (V2 add-leads, batched at 100). Endpoints and payloads mirror
the HeyReach public API (X-API-KEY auth): POST /list/CreateEmptyList and
POST /list/AddLeadsToListV2.

Mirrors the email side: just as the email file becomes a HubSpot list, the
LinkedIn file becomes a HeyReach list, ready to attach to a campaign in HeyReach.
"""
from __future__ import annotations

from .._lazy import pd
import requests

from .. import config

BASE = "https://api.heyreach.io/api/public"
_ADD_BATCH = 100
# HeyReach's list name field has a hard 50-char server-side limit (confirmed
# live: CreateEmptyList 400s with "Name must be ... a maximum length of '50'"
# on anything longer) - our campaign titles routinely run longer than that.
_LIST_NAME_MAX = 50


def _raise_with_body(r: requests.Response):
    """requests' default HTTPError swallows the response body, which is
    exactly where HeyReach puts the actual validation message (e.g. the list
    name length limit) - surface it so failures are diagnosable instead of a
    bare '400 Client Error: Bad Request for url: ...'."""
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason} for {r.url}: {r.text[:500]}", response=r)


def is_configured() -> bool:
    return bool(config.HEYREACH_API_KEY)


def _headers():
    return {"X-API-KEY": config.require("HEYREACH_API_KEY", config.HEYREACH_API_KEY),
            "Content-Type": "application/json"}


def _s(v) -> str:
    """Coerce a row field to a stripped string. A source CSV column that's
    blank for every row in a batch gets inferred by pandas as float64, so its
    "empty" cells come back as NaN (a float), not None - and NaN is truthy in
    Python, so the previous `(v or "").strip()` pattern raised AttributeError
    on it. Treat NaN the same as None/blank."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _lead(row: dict) -> dict | None:
    """profileUrl is the only hard requirement (HeyReach identifies a lead by
    LinkedIn profile). email is pushed as emailAddress whenever we have one -
    the user's HeyReach workspace is synced to email, so a lead without it
    won't line up with that integration. Anything else this pipeline has
    per-prospect but that isn't one of HeyReach's standard lead fields
    (confirmed via the real payload shape used in this account's prior
    HeyReach pushes: firstName/lastName/profileUrl/emailAddress/companyName/
    position - no other standard fields exist) goes into customUserFields,
    HeyReach's supported arbitrary-custom-field mechanism."""
    url = _s(row.get("linkedin_url"))
    if not url:
        return None
    lead = {
        "firstName": _s(row.get("first_name")) or None,
        "lastName": _s(row.get("last_name")) or None,
        "profileUrl": url,
    }
    company = _s(row.get("company_name"))
    if company:
        lead["companyName"] = company
    position = _s(row.get("job_title"))
    if position:
        lead["position"] = position
    email = _s(row.get("email"))
    if email:
        lead["emailAddress"] = email

    custom_fields = []
    domain = _s(row.get("company_domain"))
    if domain:
        custom_fields.append({"name": "company_domain", "value": domain})
    campaign = _s(row.get("campaign_title"))
    if campaign:
        custom_fields.append({"name": "campaign_title", "value": campaign})
    if custom_fields:
        lead["customUserFields"] = custom_fields
    return lead


def create_list(name: str) -> int:
    name = name[:_LIST_NAME_MAX] if len(name) > _LIST_NAME_MAX else name
    r = requests.post(f"{BASE}/list/CreateEmptyList", headers=_headers(),
                      json={"name": name, "type": "USER_LIST"}, timeout=30)
    _raise_with_body(r)
    body = r.json() if r.content else {}
    # Response shape varies; the list id is the useful bit.
    return body.get("id") or body.get("listId") or body


def add_leads(list_id: int, leads: list[dict]) -> dict:
    added = updated = failed = 0
    for i in range(0, len(leads), _ADD_BATCH):
        chunk = leads[i:i + _ADD_BATCH]
        r = requests.post(f"{BASE}/list/AddLeadsToListV2", headers=_headers(),
                          json={"listId": list_id, "leads": chunk}, timeout=60)
        _raise_with_body(r)
        body = r.json() if r.content else {}
        added += body.get("addedLeadsCount", 0)
        updated += body.get("updatedLeadsCount", 0)
        failed += body.get("failedLeadsCount", 0)
    return {"added": added, "updated": updated, "failed": failed}


def push_leads(linkedin_rows: list[dict], list_name: str) -> dict:
    """Create a HeyReach list and add the LinkedIn contacts. Returns a status
    dict. Never raises into the caller - a HeyReach failure shouldn't sink the
    HubSpot import that already succeeded."""
    if not is_configured():
        return {"status": "not_configured", "pushed": 0, "eligible": len(linkedin_rows),
                "message": "HEYREACH_API_KEY not set - LinkedIn CSV is downloadable for manual import."}

    leads = [ld for ld in (_lead(r) for r in linkedin_rows) if ld]
    if not leads:
        return {"status": "no_leads", "pushed": 0, "eligible": len(linkedin_rows),
                "message": "No LinkedIn URLs to push."}

    try:
        actual_name = list_name[:_LIST_NAME_MAX] if len(list_name) > _LIST_NAME_MAX else list_name
        list_id = create_list(actual_name)
        counts = add_leads(list_id, leads)
        return {"status": "pushed", "list_id": list_id, "list_name": actual_name,
                "eligible": len(linkedin_rows), "pushed": counts["added"] + counts["updated"], **counts}
    except Exception as e:
        return {"status": "error", "pushed": 0, "eligible": len(linkedin_rows),
                "message": f"HeyReach push failed: {e}. LinkedIn CSV is still downloadable."}
