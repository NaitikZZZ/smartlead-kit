#!/usr/bin/env python3
"""
Sweep every non-DRAFTED Smartlead campaign and pull bounced leads.

Bounce signal: lead_category_id == 9 ("Sender Originated Bounce") which matches
the bounce_count returned by /campaigns/{id}/analytics.

Usage:
    python find_bounced_leads.py

Outputs:
    outputs/bounced_leads.csv     one row per (campaign, bounced lead)
    outputs/bounced_summary.csv   one row per campaign with bounces
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

KIT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(KIT_ROOT / ".env")

API_BASE = "https://server.smartlead.ai/api/v1"
API_KEY = os.environ.get("SMARTLEAD_API_KEY") or sys.exit("Set SMARTLEAD_API_KEY in .env")

OUT_DIR = KIT_ROOT / "outputs"
OUT_DIR.mkdir(exist_ok=True)

BOUNCE_CATEGORY_ID = 9
PAGE_SIZE = 100  # API hard-caps limit at 100
MAX_WORKERS = 3  # account is throttled at 200 req/min
RETRY_MAX = 6


def request(method, path, **kwargs):
    params = kwargs.pop("params", {}) or {}
    params["api_key"] = API_KEY
    url = f"{API_BASE}{path}"
    for attempt in range(RETRY_MAX):
        r = requests.request(method, url, params=params, timeout=60, **kwargs)
        if r.status_code == 429 or "rate limit exceeded" in r.text.lower():
            time.sleep(min(60, 5 * (attempt + 1)))
            continue
        if r.status_code >= 500:
            time.sleep(1 + attempt)
            continue
        try:
            return r.json()
        except Exception:
            return {"_raw": r.text, "_status": r.status_code}
    return {"_error": f"max retries on {path}"}


def list_all_campaigns():
    """GET /campaigns/ returns full list (no pagination params accepted)."""
    data = request("GET", "/campaigns/")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return []


def get_analytics(cid):
    return request("GET", f"/campaigns/{cid}/analytics")


def is_bounce_row(r):
    """A row counts as 'bounced' if Smartlead has it as BLOCKED (recipient
    bounce / suppression) or AI-categorized as Sender Originated Bounce (id 9).
    """
    return r.get("status") == "BLOCKED" or r.get("lead_category_id") == BOUNCE_CATEGORY_ID


def get_bounced_leads(cid):
    found = []
    offset = 0
    while True:
        data = request("GET", f"/campaigns/{cid}/leads", params={"offset": offset, "limit": PAGE_SIZE})
        if not isinstance(data, dict):
            break
        rows = data.get("data") or []
        if not rows:
            break
        for r in rows:
            if is_bounce_row(r):
                found.append(r)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return found


def process_campaign(c):
    cid = c["id"]
    name = c.get("name", "")
    status = c.get("status", "")
    analytics = get_analytics(cid) or {}
    try:
        bounce_n = int(analytics.get("bounce_count") or 0)
    except (TypeError, ValueError):
        bounce_n = 0
    blocked_n = 0
    try:
        blocked_n = int((analytics.get("campaign_lead_stats") or {}).get("blocked") or 0)
    except (TypeError, ValueError):
        blocked_n = 0
    # Skip campaign only if BOTH event-level bounce_count AND lead-level blocked are zero
    if bounce_n == 0 and blocked_n == 0:
        return {"id": cid, "name": name, "status": status,
                "bounce_count": 0, "blocked_count": 0, "leads": []}
    leads = get_bounced_leads(cid)
    return {"id": cid, "name": name, "status": status,
            "bounce_count": bounce_n, "blocked_count": blocked_n, "leads": leads}


def main():
    print("Loading campaigns...", flush=True)
    campaigns = list_all_campaigns()
    print(f"  total campaigns: {len(campaigns)}", flush=True)
    targets = [c for c in campaigns if c.get("status") != "DRAFTED"]
    print(f"  non-DRAFTED to sweep: {len(targets)}", flush=True)

    summary_rows = []
    detail_rows = []
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_campaign, c): c for c in targets}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"id": c["id"], "name": c.get("name"), "status": c.get("status"),
                       "bounce_count": 0, "leads": [], "_err": str(e)}
            done += 1
            if done % 50 == 0 or res["leads"]:
                print(f"  [{done}/{len(targets)}] {res['id']} {res['status']:10} bounces={res['bounce_count']:4} blocked={res['blocked_count']:4} leads_found={len(res['leads']):4}  {res['name'][:55]}", flush=True)
            if res["bounce_count"] > 0 or res["blocked_count"] > 0 or res["leads"]:
                summary_rows.append({
                    "campaign_id": res["id"],
                    "campaign_name": res["name"],
                    "campaign_status": res["status"],
                    "analytics_bounce_count": res["bounce_count"],
                    "analytics_blocked_count": res["blocked_count"],
                    "leads_pulled_count": len(res["leads"]),
                })
            for r in res["leads"]:
                lead = r.get("lead") or {}
                detail_rows.append({
                    "campaign_id": res["id"],
                    "campaign_name": res["name"],
                    "campaign_status": res["status"],
                    "campaign_lead_map_id": r.get("campaign_lead_map_id"),
                    "lead_id": lead.get("id"),
                    "email": lead.get("email"),
                    "first_name": lead.get("first_name"),
                    "last_name": lead.get("last_name"),
                    "company_name": lead.get("company_name"),
                    "phone_number": lead.get("phone_number"),
                    "website": lead.get("website"),
                    "lead_status": r.get("status"),
                    "lead_category_id": r.get("lead_category_id"),
                    "created_at": r.get("created_at"),
                })

    detail_path = OUT_DIR / "bounced_leads.csv"
    summary_path = OUT_DIR / "bounced_summary.csv"

    with detail_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "campaign_id", "campaign_name", "campaign_status",
            "campaign_lead_map_id", "lead_id", "email", "first_name", "last_name",
            "company_name", "phone_number", "website",
            "lead_status", "lead_category_id", "created_at",
        ])
        w.writeheader()
        w.writerows(detail_rows)

    with summary_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "campaign_id", "campaign_name", "campaign_status",
            "analytics_bounce_count", "analytics_blocked_count", "leads_pulled_count",
        ])
        w.writeheader()
        w.writerows(sorted(summary_rows, key=lambda r: -(r["analytics_blocked_count"] + r["analytics_bounce_count"])))

    total_bounce_count = sum(r["analytics_bounce_count"] for r in summary_rows)
    total_blocked = sum(r["analytics_blocked_count"] for r in summary_rows)
    total_pulled = len(detail_rows)
    print()
    print(f"DONE. campaigns_with_bounces={len(summary_rows)} bounce_events={total_bounce_count} blocked_leads={total_blocked} leads_pulled={total_pulled}")
    print(f"  detail: {detail_path}")
    print(f"  summary: {summary_path}")


if __name__ == "__main__":
    main()
