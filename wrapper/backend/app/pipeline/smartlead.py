"""Smartlead push for Copy Push - the Smartlead API client that scripts/06_
smartlead_create_campaign.py already has as a CLI tool, adapted here for the
wrapper's Copy Push flow.

Scoped deliberately narrow: create the campaign, push the sequence, set the
standard schedule/settings, and leave it PAUSED - same end state as the CLI
script. No lead upload (Copy Push has no contact data by design - see
CLAUDE.md's Flow 1/Flow 2 split) and no sender-account attachment (region-
matched sender selection is deliberately deferred; attach_accounts() exists
here ready to wire in once that's defined, but push_campaign_copy() doesn't
call it on its own).

New campaigns on Smartlead start unactivated by default - there's no explicit
"pause" call to make; simply never calling the start/launch endpoint is what
keeps it PAUSED, matching the CLI script's own behavior.
"""
from __future__ import annotations

import time

import requests

from .. import config

BASE = "https://server.smartlead.ai/api/v1"


def is_configured() -> bool:
    return bool(config.SMARTLEAD_API_KEY)


def _api_key() -> str:
    return config.require("SMARTLEAD_API_KEY", config.SMARTLEAD_API_KEY)


def _raise_with_body(r: requests.Response):
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason} for {r.url}: {r.text[:500]}", response=r)


def create_campaign(name: str) -> int:
    r = requests.post(f"{BASE}/campaigns/create", params={"api_key": _api_key()},
                      json={"name": name, "client_id": None}, timeout=30)
    _raise_with_body(r)
    cid = r.json().get("id")
    if not cid:
        raise ValueError(f"Smartlead campaign create: no id in response - {r.text[:300]}")
    return cid


def save_sequence(campaign_id: int, sequence: dict) -> None:
    r = requests.post(f"{BASE}/campaigns/{campaign_id}/sequences", params={"api_key": _api_key()},
                      json=sequence, timeout=30)
    _raise_with_body(r)


def set_schedule(campaign_id: int, timezone="Asia/Calcutta", start_hour=9, end_hour=18,
                  days=None, min_gap=20, max_daily=200) -> None:
    r = requests.post(f"{BASE}/campaigns/{campaign_id}/schedule", params={"api_key": _api_key()}, json={
        "timezone": timezone, "days_of_the_week": days or [1, 2, 3, 4, 5],
        "start_hour": f"{int(start_hour):02d}:00", "end_hour": f"{int(end_hour):02d}:00",
        "min_time_btw_emails": min_gap, "max_new_leads_per_day": max_daily,
    }, timeout=15)
    _raise_with_body(r)


def configure_settings(campaign_id: int) -> None:
    r = requests.post(f"{BASE}/campaigns/{campaign_id}/settings", params={"api_key": _api_key()}, json={
        "track_settings": ["DONT_EMAIL_OPEN", "DONT_LINK_CLICK"],
        "stop_lead_settings": "REPLY_TO_AN_EMAIL",
        "send_as_plain_text": False, "follow_up_percentage": 100, "add_unsubscribe_tag": True,
    }, timeout=15)
    _raise_with_body(r)


def attach_accounts(campaign_id: int, account_ids: list[int]) -> None:
    for i in range(0, len(account_ids), 50):
        batch = account_ids[i:i + 50]
        r = requests.post(f"{BASE}/campaigns/{campaign_id}/email-accounts", params={"api_key": _api_key()},
                          json={"email_account_ids": batch}, timeout=30)
        _raise_with_body(r)
        time.sleep(0.5)


def attach_accounts_by_tag(campaign_id: int, tag_id: int) -> None:
    """Attaches every mailbox carrying tag_id to the campaign in one call -
    confirmed live endpoint (docs/smartlead-api-docs.md), the "mailbox group"
    mechanism: Smartlead's own email-account tags are already region-named
    (India/SEA/GCC-KSA/Africa/Indonesia/US/...), so picking a tag is picking a
    region-matched sender group."""
    r = requests.post(f"{BASE}/campaigns/{campaign_id}/email-accounts/by-tag", params={"api_key": _api_key()},
                      json={"tag_id": tag_id}, timeout=30)
    _raise_with_body(r)


_DNU_MARKER = "dnu"  # tags whose name flags them do-not-use (e.g. "DNU (DoNotUse)", "CXO Email Account (DNU)")


def list_account_tags(include_dnu: bool = False) -> list[dict]:
    """The "mailbox group" list for the sender-selection UI. DNU-flagged tags
    are excluded by default - their name says not to use them."""
    r = requests.get(f"{BASE}/email-accounts/tags", params={"api_key": _api_key()}, timeout=15)
    _raise_with_body(r)
    tags = r.json() if r.content else []
    if include_dnu:
        return tags
    return [t for t in tags if _DNU_MARKER not in (t.get("name") or "").lower()]


def list_email_accounts(search: str | None = None) -> list[dict]:
    """All connected inboxes, paginated (Smartlead caps each page at 100 - see
    docs/smartlead-api-docs.md). search matches from_name or from_email,
    case-insensitively, for the individual-account search fallback."""
    accounts, offset = [], 0
    while True:
        r = requests.get(f"{BASE}/email-accounts/", params={"api_key": _api_key(), "offset": offset, "limit": 100}, timeout=30)
        _raise_with_body(r)
        page = r.json() if r.content else []
        if not page:
            break
        accounts.extend(page)
        if len(page) < 100:
            break
        offset += 100
    if search:
        q = search.lower()
        accounts = [a for a in accounts
                   if q in (a.get("from_name") or "").lower() or q in (a.get("from_email") or "").lower()]
    return [{"id": a["id"], "name": a.get("from_name"), "email": a.get("from_email")} for a in accounts]


def push_campaign_copy(name: str, sequence: dict, sender_account_ids: list[int] | None = None,
                       sender_tag_id: int | None = None) -> dict:
    """Create a Smartlead campaign and push its email sequence, optionally
    attaching senders by individual account id or by a mailbox-group tag (not
    both - tag takes precedence if both given). No leads either way - those
    are added separately later. Returns a status dict; never raises into the
    caller (same best-effort contract as heyreach.py / interakt.py)."""
    if not is_configured():
        return {"status": "not_configured", "message": "SMARTLEAD_API_KEY not set"}
    try:
        cid = create_campaign(name)
        save_sequence(cid, sequence)
        set_schedule(cid)
        configure_settings(cid)
        senders_note = "No sender accounts attached yet - add before starting."
        if sender_tag_id:
            attach_accounts_by_tag(cid, sender_tag_id)
            senders_note = f"Senders attached from mailbox group (tag_id {sender_tag_id})."
        elif sender_account_ids:
            attach_accounts(cid, sender_account_ids)
            senders_note = f"{len(sender_account_ids)} sender account(s) attached."
        return {
            "status": "pushed", "campaign_id": cid, "campaign_name": name,
            "note": f"Campaign created PAUSED with sequence + default schedule/settings. {senders_note} No leads attached yet.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Smartlead push failed: {e}"}
