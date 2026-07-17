"""Exclusion against the HubSpot "ABM EXCLSIONS - DNU" contacts list (28280).

This is now the mandatory exclusion source (replaces the Account Mapping
Sheet). The list is a dynamic HubSpot contacts list with ~120k members, so we
can't pull it per run. Instead we page every member's `hs_email_domain` once,
dedupe into a normalized domain set, and cache it on disk. Runs read the cache
(instant); a scheduled/manual `refresh_cache()` keeps it fresh.

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


def build_domain_set(progress=None) -> set[str]:
    """Pages every member of the exclusion list and collects normalized email
    domains. Slow (~10-15 min for 120k) - meant to be cached, not run per job."""
    headers = _headers()
    lid = _list_id()
    domains: set[str] = set()

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
                json={"properties": ["hs_email_domain"], "inputs": [{"id": cid} for cid in chunk]},
                timeout=60,
            )
            br.raise_for_status()
            for rec in br.json().get("results", []):
                d = normalize_domain(rec.get("properties", {}).get("hs_email_domain"))
                if d:
                    domains.add(d)
            time.sleep(0.05)

        fetched += len(record_ids)
        if progress:
            progress(fetched, len(domains))
        paging = body.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break

    return domains


def refresh_cache(progress=None) -> dict:
    domains = build_domain_set(progress=progress)
    meta = {"built_at": datetime.now(UTC).isoformat(), "list_id": _list_id(),
            "domain_count": len(domains), "domains": sorted(domains)}
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


def load_domain_set(progress=None) -> tuple[set[str], dict]:
    """Returns (domain_set, meta). Uses a fresh cache if present; rebuilds only
    when the cache is missing or older than the TTL. `meta` carries staleness so
    callers can surface it."""
    age = _cache_age_hours()
    if age is not None and age <= config.EXCLUSION_CACHE_TTL_HOURS:
        data = json.loads(_CACHE_FILE.read_text())
        return set(data["domains"]), {"source": "cache", "age_hours": round(age, 1),
                                      "domain_count": data.get("domain_count", len(data["domains"])),
                                      "built_at": data.get("built_at")}
    # Missing or stale -> rebuild (this is the slow path).
    meta = refresh_cache(progress=progress)
    return set(meta["domains"]), {"source": "rebuilt", "age_hours": 0.0,
                                  "domain_count": meta["domain_count"], "built_at": meta["built_at"]}


def run_exclusion_check(df: pd.DataFrame, domain_col: str | None, progress=None):
    """Marks each row Excluded if its (email/company) domain is in the DNU set.
    Keeps the same output contract as the old sheet-based check:
    'Exclusion Status' in {'Excluded','OK to reach out'} + 'Exclusion Reason'."""
    dnu, meta = load_domain_set(progress=progress)

    dcol = domain_col if (domain_col and domain_col in df.columns) else ("Domain" if "Domain" in df.columns else None)
    statuses, reasons = [], []
    no_domain = 0
    excluded = 0
    for _, row in df.iterrows():
        d = normalize_domain(row.get(dcol)) if dcol else ""
        if not d:
            no_domain += 1
            statuses.append("OK to reach out")
            reasons.append("No domain to match against DNU list")
            continue
        # Match exact domain or a sub/parent-domain relationship (in.acme.com <-> acme.com).
        hit = d in dnu or any(d == x or d.endswith("." + x) or x.endswith("." + d) for x in dnu)
        if hit:
            excluded += 1
            statuses.append("Excluded")
            reasons.append(f"Domain {d} is in HubSpot DNU list {_list_id()}")
        else:
            statuses.append("OK to reach out")
            reasons.append("Not in DNU list")

    out = df.copy()
    out["Exclusion Status"] = statuses
    out["Exclusion Reason"] = reasons
    stats = {
        "total": len(out), "excluded": excluded,
        "ok_to_reach_out": int((out["Exclusion Status"] == "OK to reach out").sum()),
        "no_domain": no_domain,
        "dnu_domains": meta["domain_count"],
        "dnu_list_id": _list_id(),
        "cache": meta,
    }
    return out, stats


if __name__ == "__main__":  # warm-up / scheduled refresh entrypoint
    def _p(fetched, uniq):
        print(f"  fetched {fetched} members, {uniq} unique domains", flush=True)
    print(f"Refreshing exclusion cache for list {_list_id()} ...")
    m = refresh_cache(progress=_p)
    print(f"Done: {m['domain_count']} unique DNU domains cached at {_CACHE_FILE}")
