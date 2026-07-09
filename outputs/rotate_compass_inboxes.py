"""Rotate Compass campaign inboxes.

Rule (locked): Ashwin Ganesh's mailboxes (xoxodayenterprise.com, partnerwithxoxoday.com,
alliancewithxoxoday.com) are reserved exclusively for reseller-partnership campaigns.
They must NOT be used on Compass (general SMB Tech SaaS) or Empuls (HR) campaigns.

This script:
1. Removes the 3 Ashwin Ganesh inboxes from the Compass campaign (3238358)
2. Attaches 3 different India-coded sales-flavored senders
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://server.smartlead.ai/api/v1"
API_KEY = os.environ.get("SMARTLEAD_API_KEY") or sys.exit("Set SMARTLEAD_API_KEY")

CAMPAIGN_ID = 3238358  # Compass

ASHWIN_INBOXES_TO_REMOVE = [
    18054404,  # ashwin.ganesh@xoxodayenterprise.com
    18054403,  # ashwin.ganesh@partnerwithxoxoday.com
    18054402,  # ashwin.ganesh@alliancewithxoxoday.com
]

NEW_COMPASS_INBOXES = [
    16832054,  # avni.sharma@insightswithxoxoday.com
    16831996,  # vanya.shah@xoxodaycorporatehub.com
    16831934,  # aarohi.desai@xoxoday-global.com
]


def _req(method: str, path: str, body: dict | None = None) -> dict:
    qs = urllib.parse.urlencode({"api_key": API_KEY})
    url = f"{API_BASE}{path}?{qs}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()
        return {"_error": True, "_status": e.code, "_body": body_txt}


def fmt(r: dict) -> str:
    if not r.get("_error"):
        return "OK"
    body = (r.get("_body") or "")[:240]
    return f"FAIL {r.get('_status')} {body}"


def main() -> int:
    print(f"Compass campaign {CAMPAIGN_ID}: rotating inboxes")

    # Remove Ashwin Ganesh's 3 inboxes
    r = _req(
        "DELETE",
        f"/campaigns/{CAMPAIGN_ID}/email-accounts",
        {"email_account_ids": ASHWIN_INBOXES_TO_REMOVE},
    )
    print(f"  remove Ashwin x3 -> {fmt(r)}")

    # Attach 3 new India-coded inboxes
    r = _req(
        "POST",
        f"/campaigns/{CAMPAIGN_ID}/email-accounts",
        {"email_account_ids": NEW_COMPASS_INBOXES},
    )
    print(f"  add 3 new India inboxes -> {fmt(r)}")

    # Verify by listing current inboxes on the campaign
    r = _req("GET", f"/campaigns/{CAMPAIGN_ID}/email-accounts")
    if not r.get("_error"):
        attached = r if isinstance(r, list) else r.get("data", [])
        print(f"\nCurrent inboxes on Compass ({len(attached)}):")
        for a in attached:
            print(f"  id={a.get('id') or a.get('email_account_id')} | {a.get('from_email','?')} | {a.get('from_name','?')}")
    else:
        print(f"  list current -> {fmt(r)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
