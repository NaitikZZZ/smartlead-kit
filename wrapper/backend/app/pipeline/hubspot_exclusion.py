"""Exclusion against the HubSpot "ABM EXCLSIONS - DNU" contacts list (28280).

When the user chooses to run exclusion checks, they MUST use this list (mandatory).
The list is a dynamic HubSpot contacts list with ~120k members (~25-30 min to fetch).

Caching strategy:
- Daily cron at 2 AM (off-hours) refreshes the cache
- Daytime runs use the cached version if <24h old (instant lookup)
- If cache is missing/stale, a run rebuilds it fresh (~25-30 min, slow path)

Read-only against HubSpot - never writes anything (HubSpot is read-only here).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

try:
    from datetime import datetime, UTC
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc

import pandas as pd
import requests

from .. import config

_CACHE_FILE = config.CACHE_DIR / f"exclusion_domains_{config.HUBSPOT_EXCLUSION_LIST_ID}.json"
_MEMBERSHIP_PAGE = 250
_READ_BATCH = 100


def _headers():
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def normalize_domain(value) -> str:
    if value is None:
        return ""
    d = str(value).strip().lower()
    if not d or d == "nan":
        return ""
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0].strip()


def _list_id() -> str:
    return str(config.HUBSPOT_EXCLUSION_LIST_ID)


def build_exclusion_set(progress=None) -> dict:
    """Pages every member of the exclusion list and collects normalized identifiers:
    email domains, company names, company domains, LinkedIn URLs. Slow (~25-30 min
    for 120k) - meant to be cached, not run per job."""
    headers = _headers()
    lid = _list_id()
    records: list[dict] = []

    after = None
    fetched = 0
    while True:
        params = {"limit": _MEMBERSHIP_PAGE}
        if after:
            params["after"] = after
        r = requests.get(f"https://api.hubapi.com/crm/v3/lists/{lid}/memberships",
                         headers=headers, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        record_ids = [str(x["recordId"]) for x in body.get("results", [])]
        if not record_ids:
            break

        for i in range(0, len(record_ids), _READ_BATCH):
            chunk = record_ids[i:i + _READ_BATCH]
            br = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/batch/read",
                headers=headers,
                json={
                    "properties": [
                        "hs_email_domain",
                        "email",
                        "hs_lead_status",
                        "work_email",
                        "firstname",
                        "lastname",
                        "company",
                        "website",
                        "linkedinprofileid",
                        "linkedinurl"
                    ],
                    "inputs": [{"id": cid} for cid in chunk]
                },
                timeout=60,
            )
            br.raise_for_status()
            for rec in br.json().get("results", []):
                props = rec.get("properties", {})
                email_domains = set()
                # Collect email domains from both email and work_email fields
                if props.get("hs_email_domain"):
                    email_domains.add(normalize_domain(props.get("hs_email_domain", "")))
                if props.get("work_email"):
                    work_email_domain = normalize_domain(props.get("work_email", ""))
                    if work_email_domain:
                        email_domains.add(work_email_domain)

                first_name = (props.get("firstname", "") or "").strip().lower()
                last_name = (props.get("lastname", "") or "").strip().lower()
                full_name = f"{first_name} {last_name}".strip() if first_name or last_name else ""

                record = {
                    "email_domains": sorted(list(email_domains)),  # List of all email domains
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": full_name,
                    "company_name": (props.get("company", "") or "").strip().lower(),
                    "company_domain": normalize_domain(props.get("website", "")),
                    "linkedin_url": (props.get("linkedinurl", "") or "").strip().lower(),
                }
                if any([record["email_domains"], record["first_name"], record["last_name"],
                        record["company_name"], record["company_domain"], record["linkedin_url"]]):
                    records.append(record)
            time.sleep(0.05)

        fetched += len(record_ids)
        if progress:
            progress(fetched, len(records))
        paging = body.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break

    return {"records": records}


def refresh_cache(progress=None) -> dict:
    exclusion_data = build_exclusion_set(progress=progress)
    records = exclusion_data["records"]
    meta = {
        "built_at": datetime.now(UTC).isoformat(),
        "list_id": _list_id(),
        "record_count": len(records),
        "records": records
    }
    _CACHE_FILE.write_text(json.dumps(meta))
    return meta


def _cache_age_hours() -> float | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        built = datetime.fromisoformat(json.loads(_CACHE_FILE.read_text())["built_at"])
    except Exception:
        return None
    return (datetime.now(UTC) - built).total_seconds() / 3600


def load_exclusion_records(progress=None) -> tuple[list[dict], dict]:
    """Returns (records_list, meta). Uses cached version if fresh (<24h old).
    If cache is missing/stale, rebuilds from HubSpot.

    Daily cron at 2 AM refreshes the cache during off-hours, so daytime runs
    use the fresh cached copy (instant lookup). Records contain email_domain,
    company_name, company_domain, linkedin_url."""
    age = _cache_age_hours()
    if age is not None and age <= config.EXCLUSION_CACHE_TTL_HOURS:
        data = json.loads(_CACHE_FILE.read_text())
        records = data.get("records", [])
        return records, {
            "source": "cache",
            "age_hours": round(age, 1),
            "record_count": data.get("record_count", len(records)),
            "built_at": data.get("built_at")
        }
    # Missing or stale -> rebuild (slow path, ~25-30 min)
    meta = refresh_cache(progress=progress)
    return meta["records"], {
        "source": "rebuilt",
        "age_hours": 0.0,
        "record_count": meta["record_count"],
        "built_at": meta["built_at"]
    }


def run_exclusion_check(df: pd.DataFrame, domain_col: str | None, progress=None):
    """Marks each row Excluded if it matches any DNU record on:
    - Email domain (exact or subdomain)
    - Company domain (exact or subdomain)
    - Company name (exact, case-insensitive)
    - LinkedIn URL (exact match)
    - First/last name combos

    Output contract: 'Exclusion Status' in {'Excluded','OK to reach out'} + 'Exclusion Reason'.
    Robust: handles cache failures, missing columns, and row errors gracefully."""

    # Load cache with fallback
    try:
        dnu_records, meta = load_exclusion_records(progress=progress)
    except Exception as e:
        dnu_records = []
        meta = {"error": str(e), "record_count": 0, "source": "failed"}

    # If no records, mark all OK and return
    if not dnu_records:
        statuses = ["OK to reach out"] * len(df)
        reasons = ["DNU list unavailable"] * len(df)
        out = df.copy()
        out["Exclusion Status"] = statuses
        out["Exclusion Reason"] = reasons
        return out, {
            "total": len(out), "excluded": 0, "ok_to_reach_out": len(out),
            "dnu_record_count": 0, "dnu_list_id": _list_id(), "cache": meta,
        }

    # Find columns - be flexible with naming
    dcol = domain_col if (domain_col and domain_col in df.columns) else next(
        (c for c in df.columns if any(x in c.lower() for x in ["email", "person email"])), None
    )
    company_col = next((c for c in df.columns if "company" in c.lower()), None)
    linkedin_col = next((c for c in df.columns if any(x in c.lower() for x in ["linkedin", "social"])), None)
    first_name_col = next((c for c in df.columns if any(x in c.lower() for x in ["first", "fname"])), None)
    last_name_col = next((c for c in df.columns if any(x in c.lower() for x in ["last", "lname"])), None)
    domain_col_found = next((c for c in df.columns if any(x in c.lower() for x in ["domain", "website"])), None)

    statuses, reasons = [], []
    excluded = 0

    for _, row in df.iterrows():
        match_reason = None

        try:
            # Extract names safely
            row_first_name = (row.get(first_name_col) or "").strip().lower() if first_name_col else ""
            row_last_name = (row.get(last_name_col) or "").strip().lower() if last_name_col else ""
            row_full_name = f"{row_first_name} {row_last_name}".strip()
            email_domain = normalize_domain(row.get(dcol)) if dcol else ""
        except Exception:
            email_domain = ""
            row_first_name = ""
            row_last_name = ""
            row_full_name = ""

        # Match 1: Email domain
        if email_domain:
            for rec in dnu_records:
                dnu_domains = rec.get("email_domains", [])
                for dnu_domain in dnu_domains:
                    if dnu_domain and (email_domain == dnu_domain or
                                       email_domain.endswith("." + dnu_domain) or
                                       dnu_domain.endswith("." + email_domain)):
                        match_reason = f"Email domain matches DNU"
                        break
                if match_reason:
                    break

        # Match 2: First name + email domain
        if not match_reason and row_first_name and email_domain:
            for rec in dnu_records:
                if rec.get("first_name") == row_first_name:
                    dnu_domains = rec.get("email_domains", [])
                    for dnu_domain in dnu_domains:
                        if dnu_domain and (email_domain == dnu_domain or
                                           email_domain.endswith("." + dnu_domain) or
                                           dnu_domain.endswith("." + email_domain)):
                            match_reason = f"First name + email domain matches DNU"
                            break
                    if match_reason:
                        break

        # Match 3: Last name + email domain
        if not match_reason and row_last_name and email_domain:
            for rec in dnu_records:
                if rec.get("last_name") == row_last_name:
                    dnu_domains = rec.get("email_domains", [])
                    for dnu_domain in dnu_domains:
                        if dnu_domain and (email_domain == dnu_domain or
                                           email_domain.endswith("." + dnu_domain) or
                                           dnu_domain.endswith("." + email_domain)):
                            match_reason = f"Last name + email domain matches DNU"
                            break
                    if match_reason:
                        break

        # Match 4: Full name
        if not match_reason and row_full_name:
            for rec in dnu_records:
                if rec.get("full_name") == row_full_name:
                    match_reason = f"Full name matches DNU"
                    break

        # Match 5: Company domain
        if not match_reason and domain_col_found:
            try:
                company_domain = normalize_domain(row.get(domain_col_found))
                if company_domain:
                    for rec in dnu_records:
                        dnu_domain = rec.get("company_domain", "")
                        if dnu_domain and (company_domain == dnu_domain or
                                           company_domain.endswith("." + dnu_domain) or
                                           dnu_domain.endswith("." + company_domain)):
                            match_reason = f"Company domain matches DNU"
                            break
            except Exception:
                pass

        # Match 6: Company name
        if not match_reason and company_col:
            try:
                company_name = (row.get(company_col) or "").strip().lower()
                if company_name:
                    for rec in dnu_records:
                        if rec.get("company_name") and company_name == rec.get("company_name"):
                            match_reason = f"Company name matches DNU"
                            break
            except Exception:
                pass

        # Match 7: LinkedIn URL
        if not match_reason and linkedin_col:
            try:
                linkedin_url = (row.get(linkedin_col) or "").strip().lower()
                if linkedin_url:
                    for rec in dnu_records:
                        if rec.get("linkedin_url") and linkedin_url == rec.get("linkedin_url"):
                            match_reason = f"LinkedIn profile matches DNU"
                            break
            except Exception:
                pass

        if match_reason:
            excluded += 1
            statuses.append("Excluded")
            reasons.append(match_reason)
        else:
            statuses.append("OK to reach out")
            reasons.append("Not matched in DNU list")

    out = df.copy()
    out["Exclusion Status"] = statuses
    out["Exclusion Reason"] = reasons
    stats = {
        "total": len(out),
        "excluded": excluded,
        "ok_to_reach_out": int((out["Exclusion Status"] == "OK to reach out").sum()),
        "dnu_record_count": meta.get("record_count", 0),
        "dnu_list_id": _list_id(),
        "cache": meta,
    }
    return out, stats


if __name__ == "__main__":  # warm-up / scheduled refresh entrypoint
    def _p(fetched, rec_count):
        print(f"  fetched {fetched} members, {rec_count} unique records", flush=True)
    print(f"Refreshing exclusion cache for list {_list_id()} ...")
    m = refresh_cache(progress=_p)
    print(f"Done: {m['record_count']} DNU records (domains, companies, LinkedIn URLs) cached at {_CACHE_FILE}")
