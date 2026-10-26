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


_REQUIRED_COPY_KEYS = {"dm1_connected", "dm1_not_connected", "dm2", "dm3", "dm4"}


def list_senders() -> list[dict]:
    """Available LinkedIn sender accounts in this HeyReach workspace - needed
    to pick sender_ids for push_campaign_copy(). GetAll paginates (response
    has "totalCount"/"items") and defaults to a 10-item page when no
    limit/offset is sent - confirmed live 2026-10-12: a bare {} body silently
    returned 10 of 44 real accounts. 100 is the documented per-page max, so
    this loops rather than assuming one page covers every workspace."""
    accounts, offset = [], 0
    while True:
        r = requests.post(f"{BASE}/li_account/GetAll", headers=_headers(),
                          json={"offset": offset, "limit": 100}, timeout=30)
        _raise_with_body(r)
        body = r.json() if r.content else {}
        page = body.get("items", []) if isinstance(body, dict) else (body or [])
        accounts.extend(page)
        total = body.get("totalCount") if isinstance(body, dict) else None
        offset += len(page)
        if not page or (total is not None and offset >= total):
            break
    return accounts


def create_campaign(name: str, list_id: int, sender_ids: list[int]) -> int:
    """Confirmed against HeyReach's own published docs (heyreach.io/blog/campaign-api,
    checked 2026-10-12) - scripts/17_heyreach_push_campaign.py's guess that
    {"name": ...} alone was enough was wrong: linkedInUserListId and
    linkedInAccountIds (1-100 items) are both REQUIRED on Create, not
    attachable afterward. Response is {"campaignId": ...}. Creates in DRAFT
    status; StartCampaign (not called here) is a separate, explicit step."""
    r = requests.post(f"{BASE}/campaign/Create", headers=_headers(), json={
        "name": name, "linkedInUserListId": list_id, "linkedInAccountIds": sender_ids,
    }, timeout=30)
    _raise_with_body(r)
    body = r.json() if r.content else {}
    cid = body.get("campaignId") or body.get("id")
    if not cid:
        raise ValueError(f"HeyReach campaign create: no campaignId in response - {str(body)[:500]}")
    return cid


def update_schedule(campaign_id: int, timezone="Asia/Kolkata", start_hour="09:00:00", end_hour="17:00:00",
                     days=("mon", "tue", "wed", "thu", "fri")) -> None:
    """Confirmed shape (heyreach.io/blog/campaign-api, checked 2026-10-12):
    UpdateCampaignScheduleApiDto nests the actual schedule fields under a
    "schedule" object - they are NOT flat alongside campaignId, which is what
    scripts/17_heyreach_push_campaign.py's unverified guess had sent."""
    day_fields = {
        "mon": "enabledMonday", "tue": "enabledTuesday", "wed": "enabledWednesday",
        "thu": "enabledThursday", "fri": "enabledFriday", "sat": "enabledSaturday", "sun": "enabledSunday",
    }
    enabled = {field: False for field in day_fields.values()}
    for d in days:
        enabled[day_fields[d]] = True
    r = requests.post(f"{BASE}/campaign/UpdateSchedule", headers=_headers(), json={
        "campaignId": campaign_id,
        "schedule": {"dailyStartTime": start_hour, "dailyEndTime": end_hour, "timeZoneId": timezone, **enabled},
    }, timeout=15)
    _raise_with_body(r)


def update_accounts(campaign_id: int, sender_ids: list[int]) -> None:
    """Not called automatically by push_campaign_copy() - sender_ids are
    required directly on create_campaign() now (confirmed required field),
    so this is only for changing senders on an existing campaign later."""
    r = requests.post(f"{BASE}/campaign/UpdateAccounts", headers=_headers(),
                      json={"campaignId": campaign_id, "linkedInAccountIds": sender_ids}, timeout=30)
    _raise_with_body(r)


def _dm(copy: dict, key: str, delay: int, unit: str, external_ref: str, conditional: dict, unconditional: dict) -> dict:
    return {
        "nodeType": "MESSAGE", "actionDelay": delay, "actionDelayUnit": unit,
        "payload": {"messages": [copy[key]["message"]], "fallbackMessage": copy[key]["fallback"]},
        "externalReference": external_ref, "conditionalNode": conditional, "unconditionalNode": unconditional,
    }


def _end(delay: int, unit: str = "DAY") -> dict:
    return {"nodeType": "END", "actionDelay": delay, "actionDelayUnit": unit}


def _dm2_onward(copy: dict, dm2_delay_days: int) -> dict:
    dm4 = _dm(copy, "dm4", 3, "DAY", "dm4", _end(1), _end(15))
    view_profile_2 = {"nodeType": "VIEW_PROFILE", "actionDelay": 1, "actionDelayUnit": "DAY",
                       "externalReference": "view-profile-2", "unconditionalNode": dm4}
    dm3 = _dm(copy, "dm3", 7, "DAY", "dm3", _end(1), view_profile_2)
    return _dm(copy, "dm2", dm2_delay_days, "DAY", "dm2", _end(1), dm3)


def build_sequence(copy: dict) -> dict:
    """The validated default from docs/heyreach-default-workflow.md:
    CHECK_IS_CONNECTION entry, no open-profile/InMail branch (that extension
    is documented there as an unvalidated draft - not built here)."""
    connected_branch = _dm(copy, "dm1_connected", 3, "HOUR", "dm1-connected", _end(1), _dm2_onward(copy, 5))
    connection_request = {
        "nodeType": "CONNECTION_REQUEST", "actionDelay": 1, "actionDelayUnit": "DAY",
        "externalReference": "connect", "payload": {"messages": [], "toBeWithdrawnAfterDays": 30},
        "conditionalNode": _dm(copy, "dm1_not_connected", 1, "DAY", "dm1-not-connected", _end(1), _dm2_onward(copy, 6)),
        "unconditionalNode": _end(50),
    }
    like_post = {
        "nodeType": "LIKE_POST", "actionDelay": 3, "actionDelayUnit": "HOUR",
        "externalReference": "like-post",
        "payload": {"reactionType": "LIKE", "randomReaction": True, "reactBefore": "MONTH1", "skipDelayIfCannotLike": True},
        "unconditionalNode": connection_request,
    }
    not_connected_branch = {"nodeType": "VIEW_PROFILE", "actionDelay": 3, "actionDelayUnit": "HOUR",
                            "externalReference": "view-profile-1", "unconditionalNode": like_post}
    return {"nodeType": "CHECK_IS_CONNECTION", "actionDelay": 0, "externalReference": "entry",
            "conditionalNode": connected_branch, "unconditionalNode": not_connected_branch}


def update_sequence(campaign_id: int, copy: dict) -> None:
    r = requests.post(f"{BASE}/campaign/UpdateSequence", headers=_headers(),
                      json={"campaignId": campaign_id, "sequence": build_sequence(copy)}, timeout=30)
    _raise_with_body(r)


def push_campaign_copy(campaign_name: str, list_id: int, copy: dict, sender_ids: list[int] | None = None) -> dict:
    """Create a DRAFT HeyReach campaign with the real DM cadence (the
    validated two-branch structure, not the unvalidated open-profile draft -
    see build_sequence's docstring) and attach it to list_id. Never raises.

    sender_ids is REQUIRED by HeyReach's own API (linkedInAccountIds, 1-100
    items, confirmed via heyreach.io/blog/campaign-api) - there's no way to
    create a campaign without at least one sender account, so this returns
    "needs_sender_accounts" rather than attempting a call that's guaranteed
    to fail, until region-matched sender selection is defined."""
    if not is_configured():
        return {"status": "not_configured", "message": "HEYREACH_API_KEY not set"}
    if not sender_ids:
        return {"status": "needs_sender_accounts",
                "message": "HeyReach requires at least one sender LinkedIn account to create a campaign - "
                           "none selected yet. Use heyreach.list_senders() (GetAll) to see available accounts."}
    missing = _REQUIRED_COPY_KEYS - copy.keys()
    if missing:
        return {"status": "error", "message": f"copy is missing required slot(s): {', '.join(sorted(missing))}"}
    try:
        cid = create_campaign(campaign_name, list_id, sender_ids)
        update_schedule(cid)
        update_sequence(cid, copy)
        return {
            "status": "pushed", "campaign_id": cid, "campaign_name": campaign_name, "list_id": list_id,
            "note": "Campaign created DRAFT with cadence, list, and senders attached. Review in the HeyReach UI, then start manually.",
        }
    except requests.HTTPError as e:
        return {"status": "error", "message": str(e), "raw_response": e.response.text[:1000] if e.response is not None else None}
    except Exception as e:
        return {"status": "error", "message": f"HeyReach campaign push failed: {e}"}


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
