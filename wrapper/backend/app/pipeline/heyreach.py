"""HeyReach push for the LinkedIn output file.

Creates a HeyReach lead list named after the campaign and adds the LinkedIn
contacts to it (V2 add-leads, batched at 100). Endpoints and payloads mirror
the HeyReach public API (X-API-KEY auth): POST /list/CreateEmptyList and
POST /list/AddLeadsToListV2.

Mirrors the email side: just as the email file becomes a HubSpot list, the
LinkedIn file becomes a HeyReach list, ready to attach to a campaign in HeyReach.
"""
from __future__ import annotations

import requests

from .. import config

BASE = "https://api.heyreach.io/api/public"
_ADD_BATCH = 100


def is_configured() -> bool:
    return bool(config.HEYREACH_API_KEY)


def _headers():
    return {"X-API-KEY": config.require("HEYREACH_API_KEY", config.HEYREACH_API_KEY),
            "Content-Type": "application/json"}


def _lead(row: dict) -> dict | None:
    url = (row.get("linkedin_url") or "").strip()
    if not url:
        return None
    lead = {
        "firstName": (row.get("first_name") or "").strip() or None,
        "lastName": (row.get("last_name") or "").strip() or None,
        "profileUrl": url,
    }
    company = (row.get("company_name") or "").strip()
    if company:
        lead["companyName"] = company
    position = (row.get("job_title") or "").strip()
    if position:
        lead["position"] = position
    return lead


def create_list(name: str) -> int:
    r = requests.post(f"{BASE}/list/CreateEmptyList", headers=_headers(),
                      json={"name": name, "type": "USER_LIST"}, timeout=30)
    r.raise_for_status()
    body = r.json() if r.content else {}
    # Response shape varies; the list id is the useful bit.
    return body.get("id") or body.get("listId") or body


def add_leads(list_id: int, leads: list[dict]) -> dict:
    added = updated = failed = 0
    for i in range(0, len(leads), _ADD_BATCH):
        chunk = leads[i:i + _ADD_BATCH]
        r = requests.post(f"{BASE}/list/AddLeadsToListV2", headers=_headers(),
                          json={"listId": list_id, "leads": chunk}, timeout=60)
        r.raise_for_status()
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
        list_id = create_list(list_name)
        counts = add_leads(list_id, leads)
        return {"status": "pushed", "list_id": list_id, "list_name": list_name,
                "eligible": len(linkedin_rows), "pushed": counts["added"] + counts["updated"], **counts}
    except Exception as e:
        return {"status": "error", "pushed": 0, "eligible": len(linkedin_rows),
                "message": f"HeyReach push failed: {e}. LinkedIn CSV is still downloadable."}
