"""Maximize India-coded inbox attachment + bump schedule for speed.

Rule: Ashwin Ganesh inboxes are reserved for reseller partnership campaigns only.
This script does NOT attach them to Compass or Empuls.

Steps:
1. Compass (3238358): detach Ashwin x3 (idempotent if already removed), attach 7 more India senders
2. Empuls (3238359): attach 9 more India female senders
3. Bump both schedules: max_new_leads_per_day = full lead count, min_time = 10 min
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

COMPASS_ID = 3238358
EMPULS_ID = 3238359

ASHWIN_INBOXES = [18054404, 18054403, 18054402]  # reserved for reseller partnership

COMPASS_DESIRED = [
    16832001,  # pavitra.mishra@planwithxoxoday.com (already attached)
    16832054,  # avni.sharma@insightswithxoxoday.com (already attached after rotation)
    16831996,  # vanya.shah@xoxodaycorporatehub.com (already attached)
    16831934,  # aarohi.desai@xoxoday-global.com (already attached)
    16832055,  # eesha.mehta@progresswithxoxoday.com
    16831947,  # mahira.kapoor@progresswithxoxoday.com
    16831960,  # navisha.rathi@planwithxoxoday.com
    16832028,  # diya.nair@elevatewithxoxoday.com
]

EMPULS_DESIRED = [
    16833694,  # ritu.sharma (already)
    16833695,  # riya.mehta (already)
    16833699,  # sneha.nair (already)
    16833664,  # anika.sharma (already)
    16833671,  # divya.iyer
    16833663,  # aishwarya.mehta
    16833678,  # kavya.rao
    16833677,  # isha.kapoor
    16833682,  # meera.shah
    16833688,  # neha.verma
    16833700,  # tanya.gupta
    16832002,  # aisha.hassan
    16831984,  # arisha.mansoor
]


def _req(method: str, path: str, body: dict | None = None) -> dict | list:
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


def fmt(r) -> str:
    if isinstance(r, list):
        return f"OK (list len={len(r)})"
    if isinstance(r, dict) and not r.get("_error"):
        return "OK"
    body = (r.get("_body") or "")[:240] if isinstance(r, dict) else str(r)[:240]
    return f"FAIL {r.get('_status') if isinstance(r, dict) else '?'} {body}"


def list_attached(campaign_id: int) -> list[int]:
    r = _req("GET", f"/campaigns/{campaign_id}/email-accounts")
    if isinstance(r, list):
        return [a.get("id") or a.get("email_account_id") for a in r]
    if isinstance(r, dict) and not r.get("_error"):
        return [a.get("id") or a.get("email_account_id") for a in r.get("data", [])]
    return []


def detach(campaign_id: int, ids: list[int]) -> None:
    if not ids:
        return
    r = _req("DELETE", f"/campaigns/{campaign_id}/email-accounts", {"email_account_ids": ids})
    print(f"  detach {ids} -> {fmt(r)}")


def attach(campaign_id: int, ids: list[int]) -> None:
    if not ids:
        return
    r = _req("POST", f"/campaigns/{campaign_id}/email-accounts", {"email_account_ids": ids})
    print(f"  attach {ids} -> {fmt(r)}")


def reconcile(name: str, campaign_id: int, desired: list[int]) -> None:
    print(f"\n=== {name} ({campaign_id}) ===")
    current = set(list_attached(campaign_id))
    print(f"  currently attached: {sorted(current)}")

    # Always strip Ashwin if present, even if not in desired
    to_strip = [i for i in current if i in ASHWIN_INBOXES]
    if to_strip:
        detach(campaign_id, to_strip)
        current -= set(to_strip)

    to_add = [i for i in desired if i not in current]
    to_remove = [i for i in current if i not in desired and i not in ASHWIN_INBOXES]

    if to_remove:
        detach(campaign_id, to_remove)
    if to_add:
        attach(campaign_id, to_add)

    after = list_attached(campaign_id)
    print(f"  final count: {len(after)} inboxes")


def set_schedule(campaign_id: int, max_per_day: int) -> None:
    r = _req("POST", f"/campaigns/{campaign_id}/schedule", {
        "timezone": "Asia/Kolkata",
        "days_of_the_week": [1, 2, 3, 4, 5],
        "start_hour": "09:00",
        "end_hour": "18:00",
        "min_time_btw_emails": 10,
        "max_new_leads_per_day": max_per_day,
    })
    print(f"  set_schedule (max_per_day={max_per_day}, min_time=10) -> {fmt(r)}")


def main() -> int:
    reconcile("COMPASS", COMPASS_ID, COMPASS_DESIRED)
    set_schedule(COMPASS_ID, max_per_day=26)

    reconcile("EMPULS", EMPULS_ID, EMPULS_DESIRED)
    set_schedule(EMPULS_ID, max_per_day=45)

    print("\nDone. Both campaigns maxed out on India inboxes + day-1 onboarding throughput.")
    print("Ashwin Ganesh inboxes (18054404/18054403/18054402) remain reserved for reseller partnership campaigns only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
