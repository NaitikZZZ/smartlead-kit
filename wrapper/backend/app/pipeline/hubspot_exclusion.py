"""Exclusion against two HubSpot DNU contacts lists, checked with different
match rules (see config.py for the full reasoning):
- PROSPECT list (config.HUBSPOT_EXCLUSION_LIST_ID_PROSPECT): person-level
  signals (meeting completed, lifecycle/lead-status DNC). Matched narrowly -
  exact email address or exact LinkedIn URL - so one contact's status never
  excludes their colleagues at the same company.
- COMPANY list (config.HUBSPOT_EXCLUSION_LIST_ID_COMPANY): account-level
  signals (Parent Company Type, active deal stages - see
  _classify_company_reason). Matched broadly - company domain/name - to
  protect the whole account.

Both are dynamic HubSpot contacts lists, potentially tens of thousands of
members each, so each is cached independently (see refresh_cache_resumable).

Caching strategy (per list):
- Daily cron refreshes the cache
- Daytime runs use the cached version if <24h old (instant lookup)
- A real user request never rebuilds inline - only the cron does

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

from .._lazy import pd

from .. import config, redis_cache
from .hubspot_retry import request_with_retry

SOURCE_PROSPECT = "prospect"
SOURCE_COMPANY = "company"

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


def _cache_file(list_id: str) -> Path:
    return config.CACHE_DIR / f"exclusion_domains_{list_id}.json"


def _redis_key(list_id: str) -> str:
    return f"cache:exclusion:{list_id}"


def _build_state_key(list_id: str) -> str:
    return f"cache:exclusion:{list_id}:build"


def _cache_read(list_id: str) -> dict | None:
    if redis_cache.is_configured():
        return redis_cache.get_json_chunked(_redis_key(list_id))
    f = _cache_file(list_id)
    if not f.exists():
        return None
    return json.loads(f.read_text())


def _cache_write(list_id: str, meta: dict) -> None:
    if redis_cache.is_configured():
        redis_cache.set_json_chunked(_redis_key(list_id), meta)
        return
    _cache_file(list_id).write_text(json.dumps(meta))


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


def configured_lists(sources: set[str] | None = None) -> list[tuple[str, str]]:
    """(list_id, source) pairs to check. Company list is included only once
    HUBSPOT_EXCLUSION_LIST_ID_COMPANY is set.

    `sources`, when given, restricts to just those - this is what lets the
    two-stage pipeline (see runner.py) run the company list ALONE early
    (drop whole accounts before enrichment spend) and the prospect list
    ALONE late, right before the HubSpot/HeyReach/Interakt push (drop only
    the specific person, never their colleagues)."""
    lists = [(str(config.HUBSPOT_EXCLUSION_LIST_ID_PROSPECT), SOURCE_PROSPECT)]
    if config.HUBSPOT_EXCLUSION_LIST_ID_COMPANY:
        lists.append((str(config.HUBSPOT_EXCLUSION_LIST_ID_COMPANY), SOURCE_COMPANY))
    if sources is not None:
        lists = [(lid, s) for lid, s in lists if s in sources]
    return lists


def build_exclusion_set(list_id: str, source: str = SOURCE_PROSPECT, progress=None) -> dict:
    """Pages every member of the given list and collects normalized
    identifiers (exact emails, email domains, company name/domain, LinkedIn
    URL). Slow (~25-30 min for 120k) - meant to be cached, not run per job."""
    headers = _headers()
    records: list[dict] = []

    after = None
    fetched = 0
    while True:
        ids, next_after = _fetch_membership_page(headers, list_id, after)
        if not ids:
            break

        chunks = [ids[i:i + _READ_BATCH] for i in range(0, len(ids), _READ_BATCH)]
        for chunk in chunks:
            records.extend(_read_contact_batch(headers, chunk, source))
            time.sleep(0.05)

        fetched += len(ids)
        if progress:
            progress(fetched, len(records))
        after = next_after
        if not after:
            break

    return {"records": records}


def refresh_cache(list_id: str, source: str = SOURCE_PROSPECT, progress=None) -> dict:
    exclusion_data = build_exclusion_set(list_id, source, progress=progress)
    records = exclusion_data["records"]
    meta = {
        "built_at": datetime.now(UTC).isoformat(),
        "list_id": list_id,
        "record_count": len(records),
        "records": records
    }
    _cache_write(list_id, meta)
    return meta


# ---------------------------------------------------------------------------
# Resumable refresh (for duration-capped serverless, e.g. Vercel's 300s)
# ---------------------------------------------------------------------------
_READ_WORKERS = 12


def cache_is_fresh(list_id: str) -> bool:
    """True iff this list's cache is within TTL AND no rebuild is mid-flight -
    i.e. a scheduled refresh can safely no-op. Lets the cron be scheduled
    frequently (needed, since a rebuild takes several slices) without
    re-fetching every member every time."""
    if redis_cache.is_configured():
        if (redis_cache.get_json_chunked(_build_state_key(list_id)) or {}).get("after"):
            return False  # a partial build is in progress - keep going
    meta = _cache_read(list_id)
    if not meta or not meta.get("built_at"):
        return False
    try:
        built = datetime.fromisoformat(str(meta["built_at"]).replace("Z", "+00:00"))
    except ValueError:
        return False
    age_h = (datetime.now(UTC) - built).total_seconds() / 3600
    return age_h <= config.EXCLUSION_CACHE_TTL_HOURS


def all_caches_fresh() -> bool:
    return all(cache_is_fresh(lid) for lid, _source in configured_lists())


def _fetch_membership_page(headers: dict, lid: str, after: str | None) -> tuple[list[str], str | None]:
    params = {"limit": _MEMBERSHIP_PAGE}
    if after:
        params["after"] = after
    r = request_with_retry("GET", f"https://api.hubapi.com/crm/v3/lists/{lid}/memberships",
                           headers=headers, params=params, timeout=60)
    r.raise_for_status()
    body = r.json()
    ids = [str(x["recordId"]) for x in body.get("results", [])]
    return ids, body.get("paging", {}).get("next", {}).get("after")


def _email_domain(raw_email: str) -> str:
    """Domain portion of a full address, e.g. 'Jane@Acme.com' -> 'acme.com'.
    normalize_domain() alone isn't enough here - it strips protocol/www/path
    for URLs, but a raw email address has no '/' or 'www.' for it to trim, so
    'jane@acme.com' would pass through unchanged instead of becoming
    'acme.com'. Split on '@' first, then normalize the remainder."""
    if not raw_email or "@" not in raw_email:
        return ""
    return normalize_domain(raw_email.split("@")[-1])


# Sub-classifies a prospect-level DNU match into the three distinct signals
# the list actually bundles together (see config.py): a completed meeting, the
# native HubSpot lifecycle stage's "Do Not Contact (DNC)" value (internal
# value on this portal - confirmed via a read-only properties lookup), or the
# separate "ABM DNC" custom flag. Priority order matters when more than one
# applies to the same contact - most specific/actionable signal first.
_LIFECYCLE_STAGE_DNC = "125972149"


def _classify_prospect_reason(props: dict) -> str | None:
    if props.get("discovery_meeting_held_date"):
        return "Meeting completed (prospect-level DNU)"
    if props.get("lifecyclestage") == _LIFECYCLE_STAGE_DNC:
        return "Lifecycle stage DNC (prospect-level DNU)"
    if (props.get("inside_sales_lead_status") or "") == "Do Not Contact":
        return "Lead status DNC (prospect-level DNU)"
    return None


# Company-level sub-classification (config.py: "Parent Company Type
# (Farming/Churned) / active deal stages"). Any non-blank Parent Company Type
# means the account is being farmed/was churned; hs_num_open_deals > 0 means
# there's a live deal on it. Priority: farming/churned first when an account
# somehow qualifies for both - it's the more permanent designation.
def _classify_company_reason(company_props: dict) -> str | None:
    if (company_props.get("parent_company_type") or "").strip():
        return "Farming/Churned account (company-level DNU)"
    try:
        open_deals = int(float(company_props.get("hs_num_open_deals") or 0))
    except (TypeError, ValueError):
        open_deals = 0
    if open_deals > 0:
        return "Active deal on account (company-level DNU)"
    return None


def _fetch_company_associations(headers: dict, contact_ids: list[str]) -> dict[str, str]:
    """contactId -> primary associated companyId, for company-source contacts
    only (see _read_contact_batch). Parent Company Type and open-deal count
    live on the COMPANY object, not the contact, so classifying a
    company-level DNU match needs this extra hop."""
    if not contact_ids:
        return {}
    r = request_with_retry(
        "POST", "https://api.hubapi.com/crm/v4/associations/contacts/companies/batch/read",
        headers=headers,
        json={"inputs": [{"id": cid} for cid in contact_ids]},
        timeout=60,
    )
    r.raise_for_status()
    out = {}
    for row in r.json().get("results", []):
        to = row.get("to") or []
        if to:
            out[str(row["from"]["id"])] = str(to[0]["toObjectId"])
    return out


def _read_company_batch(headers: dict, company_ids: list[str]) -> dict[str, dict]:
    """companyId -> {parent_company_type, hs_num_open_deals}."""
    if not company_ids:
        return {}
    r = request_with_retry(
        "POST", "https://api.hubapi.com/crm/v3/objects/companies/batch/read",
        headers=headers,
        json={"properties": ["parent_company_type", "hs_num_open_deals"],
              "inputs": [{"id": cid} for cid in company_ids]},
        timeout=60,
    )
    r.raise_for_status()
    return {str(rec["id"]): rec.get("properties", {}) for rec in r.json().get("results", [])}


def _read_contact_batch(headers: dict, chunk: list[str], source: str = SOURCE_PROSPECT) -> list[dict]:
    """Batch-reads one chunk of contacts and maps them to DNU records. Only
    requests properties that are actually read below - the original also asked
    for hs_lead_status/linkedinprofileid/firstname/lastname and never used
    them (name-based matching was retired - see run_exclusion_check). The
    three prospect ones (lifecyclestage/inside_sales_lead_status/
    discovery_meeting_held_date) feed _classify_prospect_reason and are only
    meaningful for source=prospect; harmless to have on a company-source
    record too, just unused there.

    For source=company, two extra API calls per chunk resolve each contact's
    associated company's Parent Company Type / open-deal count (see
    _classify_company_reason) - that data lives on the company object, not
    the contact, so it can't come from this batch/read call alone."""
    br = request_with_retry(
        "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/read",
        headers=headers,
        json={"properties": ["hs_email_domain", "email", "work_email",
                             "company", "website", _LINKEDIN_PROP,
                             "lifecyclestage", "inside_sales_lead_status", "discovery_meeting_held_date"],
              "inputs": [{"id": cid} for cid in chunk]},
        timeout=60,
    )
    br.raise_for_status()
    results = br.json().get("results", [])

    company_props_by_contact = {}
    if source == SOURCE_COMPANY and results:
        contact_ids = [str(rec["id"]) for rec in results]
        company_by_contact = _fetch_company_associations(headers, contact_ids)
        company_props = _read_company_batch(headers, list(set(company_by_contact.values())))
        company_props_by_contact = {
            cid: company_props.get(company_id, {}) for cid, company_id in company_by_contact.items()
        }

    out = []
    for rec in results:
        props = rec.get("properties", {})
        emails = set()
        email_domains = set()
        if props.get("hs_email_domain"):
            email_domains.add(normalize_domain(props.get("hs_email_domain", "")))
        for key in ("email", "work_email"):
            raw = (props.get(key) or "").strip().lower()
            if raw:
                emails.add(raw)
                wd = _email_domain(raw)
                if wd:
                    email_domains.add(wd)
        record = {
            "emails": sorted(emails),
            "email_domains": sorted(email_domains),
            "company_name": (props.get("company", "") or "").strip().lower(),
            "company_domain": normalize_domain(props.get("website", "")),
            "linkedin_url": (props.get(_LINKEDIN_PROP, "") or "").strip().lower(),
            "prospect_reason": _classify_prospect_reason(props),
            "company_reason": _classify_company_reason(company_props_by_contact.get(str(rec["id"]), {})),
        }
        if any([record["emails"], record["email_domains"], record["company_name"],
                record["company_domain"], record["linkedin_url"]]):
            out.append(record)
    return out


def refresh_cache_resumable(list_id: str, source: str = SOURCE_PROSPECT, budget_seconds: int = 240, progress=None) -> dict:
    """Rebuilds one list's DNU cache in bounded slices so it can run under a
    hard function-duration cap, persisting progress between invocations.

    Why this exists: a full rebuild can't fit in Vercel's 300s cap and can't
    be made to. Measured against the (prospect) live list - membership
    pagination alone is ~486 pages x ~0.8s = ~391s, and it's cursor-based so
    it CANNOT be parallelized; batch reads add ~96s even across 12 workers.
    The old refresh_cache() only wrote the cache after finishing everything,
    so every capped invocation was killed having persisted nothing - the
    nightly Vercel cron had never once completed and the served snapshot was
    days stale.

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
    state = redis_cache.get_json_chunked(_build_state_key(list_id)) or {}
    records: list[dict] = state.get("records", [])
    after: str | None = state.get("after")
    pages = state.get("pages", 0)
    resumed = bool(state)

    headers = _headers()
    exhausted = False

    while time.time() - started < budget_seconds:
        ids, next_after = _fetch_membership_page(headers, list_id, after)
        if not ids:
            exhausted = True
            break
        chunks = [ids[i:i + _READ_BATCH] for i in range(0, len(ids), _READ_BATCH)]
        with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
            for batch in pool.map(lambda c: _read_contact_batch(headers, c, source), chunks):
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
            "list_id": list_id,
            "record_count": len(records),
            "records": records,
        }
        _cache_write(list_id, meta)
        redis_cache.set_json_chunked(_build_state_key(list_id), {})  # clear resume state
        return {"done": True, "record_count": len(records), "pages": pages,
                "built_at": meta["built_at"], "resumed": resumed,
                "elapsed_s": round(time.time() - started, 1)}

    redis_cache.set_json_chunked(_build_state_key(list_id),
                                 {"records": records, "after": after, "pages": pages})
    return {"done": False, "record_count_so_far": len(records), "pages": pages,
            "resumed": resumed, "elapsed_s": round(time.time() - started, 1)}


def load_exclusion_records(list_id: str, progress=None) -> tuple[list[dict], dict]:
    """Returns (records_list, meta) for one list. Serves whatever is cached -
    a Vercel Cron Job (see app/routes/cron.py, daily) is the ONLY thing that
    rebuilds this; a real user request never rebuilds inline anymore (that
    used to be a ~25-30 min blocking fallback on cache miss, which cannot run
    inside a Vercel function's duration limit - or, frankly, inside a request
    a human is waiting on at all). If the cache is past its TTL, it's still
    used (a slightly-stale DNU list beats none), just flagged as stale. Only
    raises if there's no cache at all yet (first-ever deploy, or a
    company-level list ID configured before its first cron run) - the caller
    already treats that as "mark everyone OK for this source" rather than
    blocking."""
    data = _cache_read(list_id)  # single fetch - reused below for both age and records
    if data is None:
        raise RuntimeError(
            f"Exclusion cache for list {list_id} has never been built - the daily cron "
            "(app/routes/cron.py) populates it; wait for the next run or trigger it manually."
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
    """Prebuilds hash lookups so matching is O(1) per row instead of a full
    linear rescan (run_exclusion_check used to scan all ~121k records
    repeatedly per input row - see git history for the pre-index numbers).

    Deliberately source-scoped, not just field-scoped: a prospect-source
    record (meeting completed / DNC) only ever contributes to the narrow
    email/LinkedIn sets, and a company-source record (Farming/deal-stage)
    only ever contributes to the broad domain/name sets. Mixing them back
    together would recreate the exact bug this split was built to fix - one
    person's meeting excluding their whole company via a domain/name match.

    Matching semantics for the domain-based rules preserve the bidirectional
    subdomain rule (input.endswith('.'+dnu) OR dnu.endswith('.'+input)) from
    the original single-list implementation. That reverse direction is what
    `*_parents` covers: a DNU domain x is a subdomain of input d exactly when
    d is one of x's parent suffixes.

    prospect_emails/prospect_linkedin_urls map identifier -> reason string
    (not plain sets) so a match can report WHICH prospect-level signal fired
    (see _classify_prospect_reason), falling back to the generic reason when
    none of the three classified properties were populated. Same idea for
    company_*_reason (see _classify_company_reason) - exact-key lookups only,
    so a match found via the parent-suffix/subdomain fallback in _domain_hit
    still falls back to the generic reason rather than a wrong one."""
    idx = {
        "prospect_emails": {},
        "prospect_linkedin_urls": {},
        "company_email_exact": set(), "company_email_parents": set(), "company_email_reason": {},
        "company_domain_exact": set(), "company_domain_parents": set(), "company_domain_reason": {},
        "company_names": set(), "company_name_reason": {},
    }
    for rec in dnu_records:
        if rec.get("source") == SOURCE_PROSPECT:
            reason = rec.get("prospect_reason")
            for e in (rec.get("emails") or []):
                idx["prospect_emails"].setdefault(e, reason)
            if rec.get("linkedin_url"):
                idx["prospect_linkedin_urls"].setdefault(rec["linkedin_url"], reason)
        else:  # SOURCE_COMPANY
            reason = rec.get("company_reason")
            for d in (rec.get("email_domains") or []):
                idx["company_email_exact"].add(d)
                idx["company_email_parents"].update(_parent_suffixes(d))
                if reason:
                    idx["company_email_reason"].setdefault(d, reason)
            cd = rec.get("company_domain")
            if cd:
                idx["company_domain_exact"].add(cd)
                idx["company_domain_parents"].update(_parent_suffixes(cd))
                if reason:
                    idx["company_domain_reason"].setdefault(cd, reason)
            if rec.get("company_name"):
                idx["company_names"].add(rec["company_name"])
                if reason:
                    idx["company_name_reason"].setdefault(rec["company_name"], reason)
    return idx


def _list_ids_label(sources: set[str] | None = None) -> str:
    return ", ".join(f"{lid} ({source})" for lid, source in configured_lists(sources))


def _domain_hit(domain: str, exact: set, parents: set) -> bool:
    """True iff any indexed domain x satisfies the original triple condition:
    domain == x, domain.endswith('.'+x), or x.endswith('.'+domain)."""
    if domain in exact:
        return True
    for suffix in _parent_suffixes(domain):  # domain.endswith("." + x)
        if suffix in exact:
            return True
    return domain in parents  # x.endswith("." + domain)


def run_exclusion_check(df: pd.DataFrame, domain_col: str | None, progress=None,
                        sources: set[str] | None = None):
    """Marks each row Excluded if it matches either configured DNU list:

    - Prospect-level list: exact email address, or exact LinkedIn URL.
      Deliberately narrow - a prospect-list member is on it for a reason
      about THEM (meeting completed, personal DNC), not their employer, so
      matching must not spill over to their colleagues.
    - Company-level list (skipped entirely until configured): email domain,
      company domain, or company name. Deliberately broad - a company-list
      member is on it for a reason about their ACCOUNT (active deal, farmed
      relationship), so the whole account should be protected.

    `sources` restricts which list(s) get checked this call - pass
    {SOURCE_COMPANY} for the early, account-dropping pipeline stage, or
    {SOURCE_PROSPECT} for the late, single-person stage right before the
    HubSpot/HeyReach/Interakt push. Omit to check whatever's configured (used
    by the campaign-idea flow, which only runs once).

    Output contract: 'Exclusion Status' in {'Excluded','OK to reach out'} + 'Exclusion Reason'.
    Robust: handles cache failures, missing columns, and row errors gracefully."""

    # Load each configured (and requested) list's cache, tagging every record
    # with its source so the index (and the matching below) keeps them apart.
    all_records: list[dict] = []
    per_source_meta: dict = {}
    any_loaded = False
    for list_id, source in configured_lists(sources):
        try:
            recs, meta = load_exclusion_records(list_id, progress=progress)
            for r in recs:
                r["source"] = source
            all_records.extend(recs)
            per_source_meta[source] = meta
            any_loaded = True
        except Exception as e:
            per_source_meta[source] = {"error": str(e), "record_count": 0, "source": "failed"}

    # If nothing loaded, mark all OK and return
    if not any_loaded or not all_records:
        statuses = ["OK to reach out"] * len(df)
        reasons = ["DNU list unavailable"] * len(df)
        out = df.copy()
        out["Exclusion Status"] = statuses
        out["Exclusion Reason"] = reasons
        return out, {
            "total": len(out), "excluded": 0, "ok_to_reach_out": len(out),
            "dnu_record_count": 0, "dnu_list_id": _list_ids_label(sources), "cache": per_source_meta,
        }

    # Find columns - be flexible with naming. email_col is the prospect's OWN
    # email address (exact match); company_domain_col is their company's
    # domain (broad match) - kept distinct, unlike the old single "email
    # domain" rule which conflated the two.
    email_col = next(
        (c for c in df.columns if "email" in c.lower() and "domain" not in c.lower()), None
    )
    linkedin_col = next((c for c in df.columns if any(x in c.lower() for x in ["linkedin", "social"])), None)
    company_col = next((c for c in df.columns if "company" in c.lower()), None)
    company_domain_col = domain_col if (domain_col and domain_col in df.columns) else next(
        (c for c in df.columns if any(x in c.lower() for x in ["domain", "website"])), None
    )

    statuses, reasons = [], []
    excluded = 0
    idx = _build_dnu_index(all_records)

    for _, row in df.iterrows():
        match_reason = None

        try:
            row_email = (row.get(email_col) or "").strip().lower() if email_col else ""
        except Exception:
            row_email = ""
        try:
            row_linkedin = (row.get(linkedin_col) or "").strip().lower() if linkedin_col else ""
        except Exception:
            row_linkedin = ""
        try:
            row_company_domain = normalize_domain(row.get(company_domain_col)) if company_domain_col else ""
        except Exception:
            row_company_domain = ""
        try:
            row_company_name = (row.get(company_col) or "").strip().lower() if company_col else ""
        except Exception:
            row_company_name = ""

        # Prospect-level: exact identifiers ONLY. No domain or name fallback
        # here on purpose - that's what used to let one person's meeting/DNC
        # status exclude their whole company (see config.py for the full
        # reasoning behind the two-list split).
        if row_email and row_email in idx["prospect_emails"]:
            match_reason = idx["prospect_emails"][row_email] or "Email matches prospect-level DNU"

        if not match_reason and row_linkedin and row_linkedin in idx["prospect_linkedin_urls"]:
            match_reason = idx["prospect_linkedin_urls"][row_linkedin] or "LinkedIn profile matches prospect-level DNU"

        # Company-level: broad, account-wide protection. No-ops entirely
        # while HUBSPOT_EXCLUSION_LIST_ID_COMPANY is unset, since idx's
        # company_* sets are empty in that case.
        if not match_reason and row_company_domain and _domain_hit(
                row_company_domain, idx["company_email_exact"], idx["company_email_parents"]):
            match_reason = idx["company_email_reason"].get(row_company_domain, "Email domain matches company-level DNU")

        if not match_reason and row_company_domain and _domain_hit(
                row_company_domain, idx["company_domain_exact"], idx["company_domain_parents"]):
            match_reason = idx["company_domain_reason"].get(row_company_domain, "Company domain matches company-level DNU")

        if not match_reason and row_company_name and row_company_name in idx["company_names"]:
            match_reason = idx["company_name_reason"].get(row_company_name, "Company name matches company-level DNU")

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
        "dnu_record_count": len(all_records),
        "dnu_record_count_by_source": {
            source: sum(1 for r in all_records if r.get("source") == source)
            for _lid, source in configured_lists(sources)
        },
        "dnu_list_id": _list_ids_label(sources),
        "cache": per_source_meta,
    }
    return out, stats


if __name__ == "__main__":  # warm-up / scheduled refresh entrypoint
    def _p(fetched, rec_count):
        print(f"  fetched {fetched} members, {rec_count} unique records", flush=True)
    for _list_id, _source in configured_lists():
        print(f"Refreshing exclusion cache for {_source} list {_list_id} ...")
        m = refresh_cache(_list_id, _source, progress=_p)
        dest = _redis_key(_list_id) if redis_cache.is_configured() else _cache_file(_list_id)
        print(f"Done: {m['record_count']} DNU records cached at {dest}")
