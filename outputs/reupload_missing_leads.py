"""Re-upload leads that Smartlead silently dropped because they exist in other campaigns.

Root cause: the original upload used `ignore_duplicate_leads_in_other_campaign: false`,
which means Smartlead BLOCKS duplicates from other campaigns. Setting it to TRUE allows
the same email to live in this campaign even if it exists in a Plum/945 campaign.

This script reads each campaign's prospects.csv, queries Smartlead for the leads currently
attached, computes the diff, and re-uploads only the missing emails with the flag flipped.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://server.smartlead.ai/api/v1"
API_KEY = os.environ.get("SMARTLEAD_API_KEY") or sys.exit("Set SMARTLEAD_API_KEY")

KIT = Path("/Users/naitikchavda/Event Auto push/smartlead-kit")

CAMPAIGNS = {
    "compass": {
        "id": 3238358,
        "csv": KIT / "outputs/smb_techsaas_compass/prospects.csv",
    },
    "empuls": {
        "id": 3238359,
        "csv": KIT / "outputs/smb_techsaas_empuls/prospects.csv",
    },
}


def _req(method, path, body=None, params=None):
    p = {"api_key": API_KEY, **(params or {})}
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(p)}"
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
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"_error": True, "_status": e.code, "_body": e.read().decode()[:400]}


def fetch_emails_in_campaign(cid: int) -> set[str]:
    out, offset = set(), 0
    while True:
        r = _req("GET", f"/campaigns/{cid}/leads", params={"limit": 100, "offset": offset})
        data = r.get("data") if isinstance(r, dict) else r
        if not data:
            break
        for L in data:
            email = (L.get("lead") or {}).get("email") or L.get("email") or ""
            if email:
                out.add(email.strip().lower())
        if len(data) < 100:
            break
        offset += 100
    return out


def load_csv_leads(path: Path) -> list[dict]:
    leads = []
    seen = set()  # in-file dedup (Compass has Rakesh Kumar + Banga sharing rakesh@atlys.com)
    with path.open() as f:
        for row in csv.DictReader(f):
            email = (row.get("email") or "").strip()
            if not email or "@" not in email:
                continue
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            leads.append({
                "first_name": row.get("first_name", "").strip(),
                "last_name": row.get("last_name", "").strip(),
                "email": email,
                "company_name": row.get("company_name", "").strip(),
                "phone_number": (row.get("phone_number") or "").strip(),
                "website": (row.get("website") or "").strip(),
                "location": (row.get("location") or "").strip(),
                "linkedin_profile": (row.get("linkedin_profile") or "").strip(),
                "custom_fields": {
                    "job_title": row.get("job_title", "").strip(),
                    "tier": row.get("tier", "").strip(),
                    "segment": row.get("segment", "").strip(),
                    "personalized_line": row.get("personalized_line", "").strip(),
                },
            })
    return leads


def upload(cid: int, leads: list[dict]) -> dict:
    return _req("POST", f"/campaigns/{cid}/leads", {
        "lead_list": leads,
        # Force-add even if these emails exist in other campaigns
        "settings": {"ignore_duplicate_leads_in_other_campaign": True},
    })


def main() -> int:
    for label, cfg in CAMPAIGNS.items():
        cid = cfg["id"]
        print(f"\n=== {label.upper()} ({cid}) ===")

        already = fetch_emails_in_campaign(cid)
        all_csv = load_csv_leads(cfg["csv"])
        missing = [L for L in all_csv if L["email"].lower() not in already]

        print(f"  csv_unique={len(all_csv)}  in_campaign={len(already)}  missing={len(missing)}")
        if not missing:
            print("  nothing to upload, skipping")
            continue

        r = upload(cid, missing)
        if r.get("_error"):
            print(f"  upload FAILED: status={r.get('_status')} body={r.get('_body')}")
            continue
        print(f"  upload OK: uploaded={r.get('upload_count')} duplicate_in_campaign={r.get('already_added_to_campaign')} blocklisted={r.get('total_unsubscribed_lead_count') or r.get('unsubscribed_leads')} invalid={r.get('invalid_emails_count')}")

        after = fetch_emails_in_campaign(cid)
        print(f"  final lead count in campaign: {len(after)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
