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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from datetime import datetime, UTC
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc

import pandas as pd
import requests

from .. import config, redis_cache

_CACHE_FILE = config.CACHE_DIR / f"exclusion_domains_{config.HUBSPOT_EXCLUSION_LIST_ID}.json"
# Redis (Upstash) is used when configured - required on Vercel, where
# _CACHE_FILE isn't writable/persistent across invocations. Chunked because
# the ~120k-record snapshot runs into the tens of MB (confirmed ~23MB).
_REDIS_KEY = f"cache:exclusion:{config.HUBSPOT_EXCLUSION_LIST_ID}"
_MEMBERSHIP_PAGE = 250
_READ_BATCH = 100
# The LinkedIn URL property that actually holds data in this portal. The code
# previously asked for "linkedinurl", which is not a property here at all (of
# 1,086 contact properties, no such name) - HubSpot silently ignores unknown
# property names, so the LinkedIn match rule was comparing against empty
# strings and could never fire. Measured on 500 DNU contacts:
# hs_linkedin_url 72.2% populated, linkedin_url 71.4%, every other candidate
# 0%. Their union is also 72.2% (only 4 contacts have hs_linkedin_url alone,
# 0 the reverse), so the second field adds no coverage and would only
# introduce conflicts (7 of 357 disagree). This also matches the property the
# write side already uses in outputs.build_hubspot_import_file.
_LINKEDIN_PROP = "hs_linkedin_url"


def _cache_read() -> dict | None:
    if redis_cache.is_configured():
        return redis_cache.get_json_chunked(_REDIS_KEY)
    if not _CACHE_FILE.exists():
        return None
    return json.loads(_CACHE_FILE.read_text())


def _cache_write(meta: dict) -> None:
    if redis_cache.is_configured():
        redis_cache.set_json_chunked(_REDIS_KEY, meta)
        return
    _CACHE_FILE.write_text(json.dumps(meta))


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
                        _LINKEDIN_PROP,
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
                    "linkedin_url": (props.get(_LINKEDIN_PROP, "") or "").strip().lower(),
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
    _cache_write(meta)
    return meta


# ---------------------------------------------------------------------------
# Resumable refresh (for duration-capped serverless, e.g. Vercel's 300s)
# ---------------------------------------------------------------------------
_BUILD_STATE_KEY = f"cache:exclusion:{config.HUBSPOT_EXCLUSION_LIST_ID}:build"
_READ_WORKERS = 12


def cache_is_fresh() -> bool:
    """True iff the cache is within TTL AND no rebuild is mid-flight - i.e. a
    scheduled refresh can safely no-op. Lets the cron be scheduled frequently
    (needed, since a rebuild takes several slices) without re-fetching 121k
    contacts every time."""
    if redis_cache.is_configured():
        if (redis_cache.get_json_chunked(_BUILD_STATE_KEY) or {}).get("after"):
            return False  # a partial build is in progress - keep going
    meta = _cache_read()
    if not meta or not meta.get("built_at"):
        return False
    try:
        built = datetime.fromisoformat(str(meta["built_at"]).replace("Z", "+00:00"))
    except ValueError:
        return False
    age_h = (datetime.now(UTC) - built).total_seconds() / 3600
    return age_h <= config.EXCLUSION_CACHE_TTL_HOURS


def _fetch_membership_page(headers: dict, lid: str, after: str | None) -> tuple[list[str], str | None]:
    params = {"limit": _MEMBERSHIP_PAGE}
    if after:
        params["after"] = after
    r = requests.get(f"https://api.hubapi.com/crm/v3/lists/{lid}/memberships",
                     headers=headers, params=params, timeout=60)
    r.raise_for_status()
    body = r.json()
    ids = [str(x["recordId"]) for x in body.get("results", [])]
    return ids, body.get("paging", {}).get("next", {}).get("after")


def _read_contact_batch(headers: dict, chunk: list[str]) -> list[dict]:
    """Batch-reads one chunk of contacts and maps them to DNU records. Only
    requests properties that are actually read below - the original also asked
    for email/hs_lead_status/linkedinprofileid and never used them."""
    br = requests.post(
        "https://api.hubapi.com/crm/v3/objects/contacts/batch/read",
        headers=headers,
        json={"properties": ["hs_email_domain", "work_email", "firstname", "lastname",
                             "company", "website", _LINKEDIN_PROP],
              "inputs": [{"id": cid} for cid in chunk]},
        timeout=60,
    )
    br.raise_for_status()
    out = []
    for rec in br.json().get("results", []):
        props = rec.get("properties", {})
        email_domains = set()
        if props.get("hs_email_domain"):
            email_domains.add(normalize_domain(props.get("hs_email_domain", "")))
        if props.get("work_email"):
            wd = normalize_domain(props.get("work_email", ""))
            if wd:
                email_domains.add(wd)
        first_name = (props.get("firstname", "") or "").strip().lower()
        last_name = (props.get("lastname", "") or "").strip().lower()
        record = {
            "email_domains": sorted(email_domains),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}".strip() if first_name or last_name else "",
            "company_name": (props.get("company", "") or "").strip().lower(),
            "company_domain": normalize_domain(props.get("website", "")),
            "linkedin_url": (props.get(_LINKEDIN_PROP, "") or "").strip().lower(),
        }
        if any([record["email_domains"], record["first_name"], record["last_name"],
                record["company_name"], record["company_domain"], record["linkedin_url"]]):
            out.append(record)
    return out


def refresh_cache_resumable(budget_seconds: int = 240, progress=None) -> dict:
    """Rebuilds the DNU cache in bounded slices so it can run under a hard
    function-duration cap, persisting progress between invocations.

    Why this exists: a full rebuild can't fit in Vercel's 300s cap and can't
    be made to. Measured against the live list - membership pagination alone
    is ~486 pages x ~0.8s = ~391s, and it's cursor-based so it CANNOT be
    parallelized; batch reads add ~96s even across 12 workers. The old
    refresh_cache() only wrote the cache after finishing everything, so every
    capped invocation was killed having persisted nothing - the nightly Vercel
    cron had never once completed and the served snapshot was days stale.

    Each call resumes from the saved cursor, works until budget_seconds, then
    saves partial progress. Returns {"done": bool, ...}; when done it writes
    the real cache key and clears the build state. Requires Redis (there is no
    meaningful resume story on an ephemeral serverless filesystem).

    build_exclusion_set()/refresh_cache() are left intact for the uncapped
    runners (module __main__, the Render cron), which are simpler when there's
    no duration limit to work around."""
    if not redis_cache.is_configured():
        raise RuntimeError("Resumable refresh needs Redis (UPSTASH_REDIS_REST_URL/TOKEN) to persist progress")

    started = time.time()
    state = redis_cache.get_json_chunked(_BUILD_STATE_KEY) or {}
    records: list[dict] = state.get("records", [])
    after: str | None = state.get("after")
    pages = state.get("pages", 0)
    resumed = bool(state)

    headers = _headers()
    lid = _list_id()
    exhausted = False

    while time.time() - started < budget_seconds:
        ids, next_after = _fetch_membership_page(headers, lid, after)
        if not ids:
            exhausted = True
            break
        chunks = [ids[i:i + _READ_BATCH] for i in range(0, len(ids), _READ_BATCH)]
        with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
            for batch in pool.map(lambda c: _read_contact_batch(headers, c), chunks):
                records.extend(batch)
        pages += 1
        after = next_after
        if progress:
            progress(pages * _MEMBERSHIP_PAGE, len(records))
        if not after:
            exhausted = True
            break

    if exhausted:
        # Dedupe before publishing. Two builds appending to the same Redis state
        # concurrently would otherwise double-count (observed live: a racing
        # manual run plus the scheduled one produced 173,250 records against an
        # expected 121,263). Cheap insurance that the published snapshot is
        # correct regardless of how the accumulated state got there.
        seen = set()
        deduped = []
        for r in records:
            key = json.dumps(r, sort_keys=True)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        records = deduped
        meta = {
            "built_at": datetime.now(UTC).isoformat(),
            "list_id": lid,
            "record_count": len(records),
            "records": records,
        }
        _cache_write(meta)
        redis_cache.set_json_chunked(_BUILD_STATE_KEY, {})  # clear resume state
        return {"done": True, "record_count": len(records), "pages": pages,
                "built_at": meta["built_at"], "resumed": resumed,
                "elapsed_s": round(time.time() - started, 1)}

    redis_cache.set_json_chunked(_BUILD_STATE_KEY,
                                 {"records": records, "after": after, "pages": pages})
    return {"done": False, "record_count_so_far": len(records), "pages": pages,
            "resumed": resumed, "elapsed_s": round(time.time() - started, 1)}


def load_exclusion_records(progress=None) -> tuple[list[dict], dict]:
    """Returns (records_list, meta). Serves whatever is cached - a Vercel Cron
    Job (see app/routes/cron.py, daily) is the ONLY thing that rebuilds this;
    a real user request never rebuilds inline anymore (that used to be a
    ~25-30 min blocking fallback on cache miss, which cannot run inside a
    Vercel function's duration limit - or, frankly, inside a request a human
    is waiting on at all). If the cache is past its TTL, it's still used (a
    slightly-stale DNU list beats none), just flagged as stale. Only raises
    if there's no cache at all yet (first-ever deploy, before the cron has
    run once) - the caller already treats that as "mark everyone OK, DNU
    list unavailable" rather than blocking."""
    data = _cache_read()  # single fetch - reused below for both age and records, not re-fetched via _cache_age_hours()
    if data is None:
        raise RuntimeError(
            "Exclusion cache has never been built - the daily cron (app/routes/cron.py) "
            "populates it; wait for the next run or trigger it manually."
        )
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(data["built_at"])).total_seconds() / 3600
    except Exception:
        age = None
    records = data.get("records", [])
    stale = age is None or age > config.EXCLUSION_CACHE_TTL_HOURS
    return records, {
        "source": "stale_cache" if stale else "cache",
        "age_hours": round(age, 1) if age is not None else None,
        "record_count": data.get("record_count", len(records)),
        "built_at": data.get("built_at"),
    }


def _parent_suffixes(domain: str) -> list[str]:
    """Proper parent suffixes of a domain: a.b.com -> ['b.com', 'com']."""
    parts = domain.split(".")
    return [".".join(parts[i:]) for i in range(1, len(parts))]


def _build_dnu_index(dnu_records: list[dict]) -> dict:
    """Prebuilds hash lookups for the DNU list so matching is O(1) per row
    instead of a full linear rescan.

    Why: run_exclusion_check used to scan all ~121k records SEVEN times per
    input row (~849k dict lookups/row, measured 0.307s/row). A 4,643-row run
    therefore needed ~48min on Vercel, blew the 300s function cap, got killed,
    and Inngest retried it 5 times - the run sat at "running" for 105min and
    never completed. Indexed, the same work is ~0.6s of setup plus ~5us/row.

    Matching semantics are preserved EXACTLY, including the bidirectional
    subdomain rule (input.endswith('.'+dnu) OR dnu.endswith('.'+input)). That
    reverse direction is what `*_parents` covers: a DNU domain x is a
    subdomain of input d exactly when d is one of x's parent suffixes."""
    idx = {
        "email_exact": set(), "email_parents": set(),
        "first_exact": {}, "first_parents": {},
        "last_exact": {}, "last_parents": {},
        "full_names": set(), "full_name_ctx": {},
        "company_domain_exact": set(), "company_domain_parents": set(),
        "company_names": set(), "linkedin_urls": set(),
    }
    for rec in dnu_records:
        domains = [d for d in (rec.get("email_domains") or []) if d]
        for d in domains:
            idx["email_exact"].add(d)
            idx["email_parents"].update(_parent_suffixes(d))

        if domains:
            for key, ex, par in (("first_name", "first_exact", "first_parents"),
                                 ("last_name", "last_exact", "last_parents")):
                name = rec.get(key)
                if name:
                    e = idx[ex].setdefault(name, set())
                    p = idx[par].setdefault(name, set())
                    for d in domains:
                        e.add(d)
                        p.update(_parent_suffixes(d))

        if rec.get("full_name"):
            fname = rec["full_name"]
            idx["full_names"].add(fname)
            # Context behind each name, so a name match can require corroboration
            # (see the Match 4 comment in run_exclusion_check).
            ctx = idx["full_name_ctx"].setdefault(fname, {"companies": set(), "domains": set()})
            if rec.get("company_name"):
                ctx["companies"].add(rec["company_name"])
            if rec.get("company_domain"):
                ctx["domains"].add(rec["company_domain"])
            for d in domains:
                ctx["domains"].add(d)
        cd = rec.get("company_domain")
        if cd:
            idx["company_domain_exact"].add(cd)
            idx["company_domain_parents"].update(_parent_suffixes(cd))
        if rec.get("company_name"):
            idx["company_names"].add(rec["company_name"])
        if rec.get("linkedin_url"):
            idx["linkedin_urls"].add(rec["linkedin_url"])
    return idx


def _domain_hit(domain: str, exact: set, parents: set) -> bool:
    """True iff any indexed domain x satisfies the original triple condition:
    domain == x, domain.endswith('.'+x), or x.endswith('.'+domain)."""
    if domain in exact:
        return True
    for suffix in _parent_suffixes(domain):  # domain.endswith("." + x)
        if suffix in exact:
            return True
    return domain in parents  # x.endswith("." + domain)


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
    idx = _build_dnu_index(dnu_records)

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
        if email_domain and _domain_hit(email_domain, idx["email_exact"], idx["email_parents"]):
            match_reason = "Email domain matches DNU"

        # Match 2: First name + email domain
        if not match_reason and row_first_name and email_domain:
            if _domain_hit(email_domain, idx["first_exact"].get(row_first_name, frozenset()),
                           idx["first_parents"].get(row_first_name, frozenset())):
                match_reason = "First name + email domain matches DNU"

        # Match 3: Last name + email domain
        if not match_reason and row_last_name and email_domain:
            if _domain_hit(email_domain, idx["last_exact"].get(row_last_name, frozenset()),
                           idx["last_parents"].get(row_last_name, frozenset())):
                match_reason = "Last name + email domain matches DNU"

        # Row company/domain, needed by Match 4's corroboration check as well
        # as Matches 5 and 6.
        try:
            row_company_domain = normalize_domain(row.get(domain_col_found)) if domain_col_found else ""
        except Exception:
            row_company_domain = ""
        try:
            row_company_name = (row.get(company_col) or "").strip().lower() if company_col else ""
        except Exception:
            row_company_name = ""

        # Match 4: Full name - but ONLY when the company or domain corroborates it.
        # A bare name match excluded anyone sharing a name with any of 96,538 DNU
        # names: measured on 6,000 real prospects, 226 rows were excluded on name
        # alone and only 5 had any corroborating company/domain, i.e. ~221 false
        # positives (21.5% of all exclusions) - real people like "Imran Khan" at
        # kizad.ae dropped because an unrelated Imran Khan sits at another
        # account. Requiring corroboration keeps genuine same-person hits while
        # recovering those prospects; the strong signals (email/company domain,
        # company name, LinkedIn) are already covered by the other rules.
        if not match_reason and row_full_name and row_full_name in idx["full_names"]:
            ctx = idx["full_name_ctx"].get(row_full_name)
            if ctx and ((row_company_name and row_company_name in ctx["companies"])
                        or (row_company_domain and row_company_domain in ctx["domains"])
                        or (email_domain and email_domain in ctx["domains"])):
                match_reason = "Full name + company/domain matches DNU"

        # Match 5: Company domain
        if not match_reason and row_company_domain:
            if _domain_hit(row_company_domain, idx["company_domain_exact"],
                           idx["company_domain_parents"]):
                match_reason = "Company domain matches DNU"

        # Match 6: Company name
        if not match_reason and row_company_name:
            try:
                company_name = row_company_name
                if company_name and company_name in idx["company_names"]:
                    match_reason = "Company name matches DNU"
            except Exception:
                pass

        # Match 7: LinkedIn URL
        if not match_reason and linkedin_col:
            try:
                linkedin_url = (row.get(linkedin_col) or "").strip().lower()
                if linkedin_url and linkedin_url in idx["linkedin_urls"]:
                    match_reason = "LinkedIn profile matches DNU"
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
    _dest = _REDIS_KEY if redis_cache.is_configured() else _CACHE_FILE
    print(f"Done: {m['record_count']} DNU records (domains, companies, LinkedIn URLs) cached at {_dest}")
