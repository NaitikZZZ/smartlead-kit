"""Looks up whether each account's domain matches a HubSpot "dream account"
company, and who owns it. Read-only against HubSpot - never writes.

Two signals are checked (per user's own combined ask, 2026-09-15) since they
can drift independently - confirmed live on this portal: cam_account and
is_fy_24_cam are usually set together (same bulk update, 2026-09-04) but not
always (7,394 vs 7,204 matches out of 212,944 companies - a ~190 gap):
- cam_account (label "Dream Account Year"): FY24CAM/FY25CAM/FY26CAM picklist.
  Counts as a 2026 dream account when this is "FY26CAM".
- is_fy_24_cam (label "Is Dream Account ?"): legacy Yes/No flag, kept as an
  additional signal in case a company was only ever tagged here.

is_dream_account_2026 = cam_account == "FY26CAM" OR is_fy_24_cam == "true".

Matching is by company domain via the Search API with an IN filter - NOT
batch/read with idProperty="domain": confirmed live that idProperty=domain
404s the ENTIRE batch call on this portal even when every domain in it is a
real, existing company (domain isn't configured as a unique-id-eligible
property here), so batch/read is unusable regardless of unmatched domains.
"""
from __future__ import annotations

from .. import config
from .hubspot_retry import request_with_retry

_SEARCH_CHUNK = 100
_DREAM_YEAR_VALUE = "FY26CAM"


def _headers():
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _fetch_all_owners(headers: dict) -> dict[str, str]:
    """Real Owners API, not the hubspot_owner_id property's cached enum
    options - confirmed live that enum is stale/incomplete (missing at
    least one active, currently-assigned owner seen on real company
    records)."""
    names: dict[str, str] = {}
    after = None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        r = request_with_retry("GET", "https://api.hubapi.com/crm/v3/owners",
                               headers=headers, params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        for o in body.get("results", []):
            name = (f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
                    or o.get("email") or f"Owner {o['id']}")
            names[str(o["id"])] = name
        after = body.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return names


def lookup_dream_accounts(domains: list, progress=None) -> tuple[dict, dict]:
    """domain (lowercased/stripped) -> {"is_dream_account_2026": bool,
    "cam_account": str|None, "is_fy_24_cam": bool, "owner_id": str|None,
    "owner_name": str|None}. A domain absent from the returned dict was
    either blank or didn't match any HubSpot company - callers must treat
    that as "unknown", not "not a dream account"."""
    headers = _headers()
    clean = sorted({str(d).strip().lower() for d in domains if d and str(d).strip()})
    if not clean:
        return {}, {"total_domains": 0, "matched": 0}

    owner_names = _fetch_all_owners(headers)
    out: dict = {}

    for i in range(0, len(clean), _SEARCH_CHUNK):
        chunk = clean[i:i + _SEARCH_CHUNK]
        after = None
        while True:
            body_req = {
                "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "IN", "values": chunk}]}],
                "properties": ["domain", "cam_account", "is_fy_24_cam", "hubspot_owner_id"],
                "limit": 100,
            }
            if after:
                body_req["after"] = after
            r = request_with_retry("POST", "https://api.hubapi.com/crm/v3/objects/companies/search",
                                   headers=headers, json=body_req, timeout=60)
            r.raise_for_status()
            body = r.json()
            for rec in body.get("results", []):
                props = rec.get("properties", {}) or {}
                domain = (props.get("domain") or "").strip().lower()
                if not domain:
                    continue
                cam = props.get("cam_account")
                legacy = (props.get("is_fy_24_cam") or "").strip().lower() == "true"
                owner_id = props.get("hubspot_owner_id")
                out[domain] = {
                    "cam_account": cam,
                    "is_fy_24_cam": legacy,
                    "is_dream_account_2026": (cam == _DREAM_YEAR_VALUE) or legacy,
                    "owner_id": owner_id,
                    "owner_name": (owner_names.get(owner_id, f"Unknown owner ({owner_id})")
                                   if owner_id else "Unassigned"),
                }
            after = body.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        if progress:
            progress(min(i + _SEARCH_CHUNK, len(clean)), len(clean))

    return out, {"total_domains": len(clean), "matched": len(out)}
