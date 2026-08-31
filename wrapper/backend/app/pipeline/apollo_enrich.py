"""Wraps the 3 existing Apollo scripts directly (search -> reveal email/fields
-> reveal phone), reusing their exact tested logic rather than reimplementing
it. Apollo-only per current scope - Lusha is intentionally not wired in here."""
from __future__ import annotations
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .. import config, redis_cache

sys.path.insert(0, str(config.SCRIPTS_DIR))
import search_company_contacts_apollo as _search  # noqa: E402
import enrich_full_fields_apollo as _enrich  # noqa: E402
import enrich_phone_apollo as _phone  # noqa: E402
import enrich_contacts_apollo as _contacts  # noqa: E402
import icp_titles as _icp_titles  # noqa: E402

import json as _json

DEFAULT_WORKERS = 8
# search_candidates_by_icp paginates Apollo's people search directly (no
# per-company loop to bound it), so this caps worst-case spend if a target
# count is set unreasonably high or Apollo keeps returning full pages.
MAX_ICP_PAGES = 10

# Apollo's person_locations filter matches on literal place names ("Saudi
# Arabia"), not abbreviations - confirmed by hand: filtering on "KSA" returned
# 0 results where "Saudi Arabia" returned real matches. REGION_GROUPS is the
# one-to-many expansion from a broad label offered in the UI to the literal
# country names Apollo actually recognizes. Anything not in this map (a
# country picked directly, e.g. "Qatar") is passed through unchanged.
REGION_GROUPS: dict[str, list[str]] = {
    "US": ["United States"],
    "UK": ["United Kingdom"],
    "Europe": ["United Kingdom", "Germany", "France", "Netherlands", "Spain", "Italy",
               "Ireland", "Sweden", "Switzerland", "Belgium", "Poland"],
    "APAC": ["Australia", "Singapore", "Japan", "India", "Hong Kong", "New Zealand", "South Korea"],
    "GCC": ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"],
    "Saudi Arabia": ["Saudi Arabia"],
    "Africa": ["South Africa", "Nigeria", "Kenya", "Egypt", "Ghana", "Morocco"],
    "SEA": ["Singapore", "Malaysia", "Indonesia", "Philippines", "Thailand", "Vietnam"],
    "Philippines": ["Philippines"],
    "Indonesia": ["Indonesia"],
    "Canada": ["Canada"],
    "Australia": ["Australia"],
    "India": ["India"],
    "Global": [],  # explicitly "no filter" - a bare "Global" used to be sent to Apollo literally
}


def expand_person_locations(selected: list[str] | None) -> list[str] | None:
    """Expand any broad region labels into the literal country names Apollo's
    person_locations filter matches on; individual countries pass through
    unchanged. Single choke point right before the Apollo call, so every
    caller (discovery form, campaign-idea search, "add more" loops) gets this
    fix for free. Returns None for "no filter" (blank, or only "Global")."""
    if not selected:
        return None
    expanded: list[str] = []
    for label in selected:
        expanded.extend(REGION_GROUPS.get(label, [label]))
    seen: set[str] = set()
    out = []
    for loc in expanded:
        if loc and loc not in seen:
            seen.add(loc)
            out.append(loc)
    return out or None

# Re-exported so callers (inngest_runner's discovery_form) don't need their
# own sys.path hookup into scripts/search_company_contacts_apollo.py just to
# read these two enums.
DEFAULT_SENIORITIES = _search.DEFAULT_SENIORITIES
ALL_SENIORITIES = _search.ALL_SENIORITIES
ALL_FUNCTIONS = _search.ALL_FUNCTIONS

SENIORITY_LABELS = {
    "owner": "Owner", "founder": "Founder", "c_suite": "C-Suite", "partner": "Partner",
    "vp": "VP", "head": "Head", "director": "Director", "manager": "Manager",
    "senior": "Senior", "entry": "Entry", "intern": "Intern",
}
FUNCTION_LABELS = {
    "sales": "Sales", "marketing": "Marketing", "engineering": "Engineering",
    "product_management": "Product Management", "finance": "Finance", "accounting": "Accounting",
    "operations": "Operations", "human_resources": "Human Resources",
    "information_technology": "Information Technology", "legal": "Legal",
    "consulting": "Consulting", "administrative": "Administrative", "education": "Education",
    "entrepreneurship": "Entrepreneurship", "support": "Support", "data_science": "Data Science",
}
SENIORITY_OPTIONS = [{"value": v, "label": SENIORITY_LABELS[v]} for v in ALL_SENIORITIES]
FUNCTION_OPTIONS = [{"value": v, "label": FUNCTION_LABELS[v]} for v in ALL_FUNCTIONS]


def icp_cluster_options() -> list[dict]:
    """Cluster picker options for the discovery form - one entry per
    scripts/icp_titles.py family (52 canonical Xoxoday title clusters derived
    from the ABM Campaign Planner), grouped by product in the UI."""
    return [
        {"key": f["key"], "label": f["label"], "products": f["products"], "role": f["role"]}
        for f in _icp_titles.FAMILIES
    ]


def titles_for_clusters(cluster_keys: list[str] | None) -> list[str] | None:
    """Expand selected cluster keys into their Apollo-ready title variants
    (deduped, order-preserving). icp_titles.py's variants are deliberately
    broad substrings (e.g. "hr business partner" is meant to also match
    "Senior HR Business Partner, EMEA") - callers should search/select with
    exact_titles=False when driven by cluster variants, not a literal title
    the user typed themselves."""
    if not cluster_keys:
        return None
    titles: list[str] = []
    seen = set()
    for key in cluster_keys:
        family = _icp_titles.BY_KEY.get(key)
        if not family:
            continue
        for v in family["variants"]:
            if v not in seen:
                seen.add(v)
                titles.append(v)
    return titles or None


# Local reveal caches so a re-run never re-pays Apollo for the same person:
#   email    -> keyed name@domain (People Match, ~1 credit)
#   person   -> keyed apollo_id  (full-field reveal, ~1 credit)
#   details  -> keyed name@domain (LinkedIn/company/seniority backfill for
#               existing-contact sheets, ~1 credit - see fill_missing_details)
# Phone has its own cache in the phone script (reference/phone_reveal_cache.csv).
# Redis (Upstash, via app/redis_cache.py) is used when configured - required
# on Vercel, where the local file paths below aren't writable/persistent
# across invocations. Falls back to the local file otherwise. The person
# cache runs into the tens of MB (confirmed ~22MB in practice) so it uses the
# chunked Redis helper; the other two stay well under 1MB.
_EMAIL_CACHE = config.CACHE_DIR / "email_reveal_cache.json"
_PERSON_CACHE = config.CACHE_DIR / "person_enrich_cache.json"
_DETAILS_CACHE = config.CACHE_DIR / "existing_contact_details_cache.json"
_EMAIL_REDIS_KEY = "cache:email_reveal"
_PERSON_REDIS_KEY = "cache:person_enrich"
_DETAILS_REDIS_KEY = "cache:existing_contact_details"

# (redis key, chunked?) per cache file - chunked is only needed for the
# person cache's tens-of-MB size (see redis_cache.set_json_chunked).
_CACHE_REDIS = {
    _EMAIL_CACHE: (_EMAIL_REDIS_KEY, False),
    _PERSON_CACHE: (_PERSON_REDIS_KEY, True),
    _DETAILS_CACHE: (_DETAILS_REDIS_KEY, False),
}


def _load_cache(path):
    if redis_cache.is_configured():
        key, chunked = _CACHE_REDIS[path]
        getter = redis_cache.get_json_chunked if chunked else redis_cache.get_json
        return getter(key) or {}
    try:
        return _json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _save_cache(path, cache):
    if redis_cache.is_configured():
        key, chunked = _CACHE_REDIS[path]
        setter = redis_cache.set_json_chunked if chunked else redis_cache.set_json
        setter(key, cache)
        return
    try:
        path.write_text(_json.dumps(cache))
    except Exception:
        pass


def _run_parallel(items, fn, max_workers, progress=None):
    """Run fn(item) -> (key, value, label) across a thread pool, returning
    {key: value}. Fires progress(done, total, label) as each completes (real
    time, not input-ordered). One item's exception is dropped, not fatal."""
    total = len(items)
    results: dict = {}
    if not items:
        return results
    done = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=min(max_workers, total)) as ex:
        futs = [ex.submit(fn, it) for it in items]
        for fut in as_completed(futs):
            try:
                key, value, label = fut.result()
            except Exception:
                continue
            results[key] = value
            with lock:
                done += 1
                d = done
            if progress:
                try:
                    progress(d, total, label)
                except Exception:
                    pass
    return results


def search_candidates(df: pd.DataFrame, company_col: str, domain_col: str, person_locations=None, persona_titles=None,
                       max_per_company=None, per_title_cap=None, employee_ranges=None, exact_titles=True,
                       organization_locations=None, person_seniorities=None, person_functions=None,
                       exclude_titles=None, industries=None):
    """per_title_cap (1-3 typically) switches selection to
    select_candidates_per_persona: every title in persona_titles is guaranteed
    up to per_title_cap candidates per company, instead of ranking against the
    hardcoded HR-only PERSONA_TIERS list. Leave it None to keep the original
    flat-cap behavior (used by the Apollo-search-from-campaign-idea flow).

    exact_titles (only meaningful when per_title_cap is set - the default HR
    tier list has no single "requested title" to be exact about) restricts
    matches to the same title as requested (word-order-insensitive) rather
    than any title containing it as a substring. True is the default so a
    request for "Total Rewards Head" doesn't silently pull in "Total Rewards
    Manager"; the "include similar/lookalike titles" UI option sets this False.

    organization_locations is separate from person_locations: it filters by
    the target company's HQ (city/state/country, free text - e.g. "Austin,
    Texas", "California, US"), for "HQ based" use cases where you want
    contacts at companies headquartered somewhere specific, regardless of
    where the individual contact is personally based. No region-group
    expansion is applied to it (unlike person_locations) since it's expected
    to be specific city/state/country entries, not broad UI labels.

    person_seniorities ("Management Level") and person_functions
    ("Departments & Job Function") are real Apollo mixed_people/api_search
    filters (see search_company_contacts_apollo.py's ALL_SENIORITIES /
    ALL_FUNCTIONS for how each was verified) - both None keeps the prior
    hardcoded-seniority, no-function-filter behavior.

    exclude_titles is NOT an Apollo API parameter - Apollo's search has no
    native title-exclusion filter (confirmed against their docs). This is a
    post-filter applied to whatever Apollo returns, dropping any candidate
    whose title contains an excluded phrase (lookalike/substring match, same
    rule title_matches_any(exact=False) uses) before selection - so an
    excluded candidate is never selected or counted, regardless of
    per_title_cap mode.

    industries is free-text industry/keyword filtering (e.g. "healthcare",
    "fintech") sent through Apollo's documented q_organization_keyword_tags
    filter - Apollo's search has no public, documented industry-taxonomy-ID
    filter, so this is keyword matching rather than a curated category."""
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

    person_locations = expand_person_locations(person_locations)
    personas = persona_titles or _search.PERSONAS
    cap = min(max_per_company or _search.MAX_PER_COMPANY, 10)
    rows = []
    per_company_counts = {}
    for _, row in df.iterrows():
        company, domain = row[company_col], row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            per_company_counts[company] = 0
            continue
        old_personas, old_cap = _search.PERSONAS, _search.MAX_PER_COMPANY
        _search.PERSONAS, _search.MAX_PER_COMPANY = personas, cap
        try:
            people = _search.search_people(session, domain, person_locations, employee_ranges, organization_locations,
                                            person_seniorities, person_functions, industries)
            if exclude_titles:
                people = [p for p in people if not title_matches_any(p.get("title"), exclude_titles, exact=False)]
            if per_title_cap:
                selected = _search.select_candidates_per_persona(people, personas, per_title_cap, exact=exact_titles)
                # select_candidates_per_persona guarantees per-title coverage with
                # no overall ceiling - without this, a broad cluster expanding into
                # many titles could return far more than `cap` per company. Persona
                # order is priority order, so truncating here keeps the
                # highest-priority personas' picks over lower ones.
                selected = selected[:cap]
            else:
                selected = _search.select_candidates(people)
        finally:
            _search.PERSONAS, _search.MAX_PER_COMPANY = old_personas, old_cap
        per_company_counts[company] = len(selected)
        for p in selected:
            rows.append({
                "Company": company, "Domain": domain, "apollo_id": p.get("id"),
                "obfuscated_name": f"{p.get('first_name', '')} {p.get('last_name_obfuscated', '')}",
                "title": p.get("title"), "persona_tier": p["_tier"],
                "has_email": p.get("has_email"), "has_direct_phone": p.get("has_direct_phone"),
            })
        time.sleep(0.3)

    candidates_df = pd.DataFrame(rows)
    zero_match_companies = [c for c, n in per_company_counts.items() if n == 0]
    return candidates_df, {
        "companies_searched": len(per_company_counts),
        "candidates_found": len(rows),
        "zero_match_companies": zero_match_companies,
    }


def search_candidates_by_icp(person_locations=None, persona_titles=None, target_count=100,
                              employee_ranges=None, organization_locations=None, person_seniorities=None,
                              person_functions=None, exclude_titles=None, industries=None,
                              per_title_cap=None, exact_titles=True):
    """Domain-less counterpart to search_candidates - for building an account
    list from scratch, when there are no target companies to search yet (just
    ICP filters: job titles/employee size/region/industry). Paginates Apollo's
    mixed_people/api_search directly (no q_organization_domains_list) instead
    of looping per company, since matches can land at any number of different
    organizations. Company/Domain per candidate come from Apollo's own
    organization data on each person, not a caller-supplied list.

    target_count is a soft cap - pagination stops once at least that many
    people have been fetched (then selection may trim further), or once
    Apollo returns a short page (no more results), or after MAX_ICP_PAGES."""
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

    person_locations = expand_person_locations(person_locations)
    personas = persona_titles or _search.PERSONAS

    old_personas = _search.PERSONAS
    _search.PERSONAS = personas
    people = []
    page = 1
    try:
        while len(people) < target_count and page <= MAX_ICP_PAGES:
            batch = _search.search_people(
                session, None, person_locations, employee_ranges, organization_locations,
                person_seniorities, person_functions, industries, page=page, per_page=100)
            if not batch:
                break
            people.extend(batch)
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.3)
    finally:
        _search.PERSONAS = old_personas

    if exclude_titles:
        people = [p for p in people if not title_matches_any(p.get("title"), exclude_titles, exact=False)]

    if per_title_cap:
        selected = _search.select_candidates_per_persona(people, personas, per_title_cap, exact=exact_titles)
    else:
        selected = _search.select_candidates(people)
    selected = selected[:target_count]

    rows = []
    companies_seen = set()
    for p in selected:
        org = p.get("organization") or {}
        company = org.get("name") or "Unknown"
        domain = org.get("primary_domain")
        companies_seen.add(company)
        rows.append({
            "Company": company, "Domain": domain, "apollo_id": p.get("id"),
            "obfuscated_name": f"{p.get('first_name', '')} {p.get('last_name_obfuscated', '')}",
            "title": p.get("title"), "persona_tier": p["_tier"],
            "has_email": p.get("has_email"), "has_direct_phone": p.get("has_direct_phone"),
        })

    candidates_df = pd.DataFrame(rows)
    return candidates_df, {
        "companies_searched": len(companies_seen),
        "candidates_found": len(rows),
        "zero_match_companies": [],
    }


def enrich_candidates(candidates_df: pd.DataFrame, full_dump: bool = False, progress=None, max_workers: int = DEFAULT_WORKERS):
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))

    def _apply_row(flat_base, company, domain):
        flat = dict(flat_base)
        flat["search_company"] = company
        flat["search_domain"] = domain
        email = flat.get("email", "") or ""
        flat["email_domain_confidence"] = (_enrich.domain_match_check(email, domain)[1] if email else "No email found")
        return flat

    cache = _load_cache(_PERSON_CACHE)
    items = list(candidates_df.iterrows())
    result_map = {}
    tasks = []
    for idx, row in items:
        aid = str(row["apollo_id"])
        if aid in cache:  # already revealed before -> free
            result_map[idx] = _apply_row(cache[aid], row.get("Company"), row.get("Domain"))
        else:
            tasks.append((idx, row, aid))

    def _one(t):
        idx, row, aid = t
        p = _enrich.enrich(session, aid)
        flat = _enrich.flatten_person(p)
        return idx, (flat, aid, row.get("Company"), row.get("Domain")), (flat.get("first_name") or row.get("Company") or "")

    fetched = _run_parallel(tasks, _one, max_workers, progress)
    for idx, (flat, aid, company, domain) in fetched.items():
        cache[aid] = flat  # store the base reveal (no per-row search fields)
        result_map[idx] = _apply_row(flat, company, domain)
    if fetched:
        # Skip the write when nothing changed - this cache is a single JSON
        # blob (23MB+ after this session's testing), and rewriting it whole
        # on every call, even a 100%-cache-hit one, risks timing out the
        # Redis pipeline POST for no reason (confirmed live).
        _save_cache(_PERSON_CACHE, cache)

    rows = [result_map[idx] for idx, _ in items if idx in result_map]
    paid = len(tasks)

    out = pd.DataFrame(rows)
    if "organization_technology_names" in out.columns:
        out["technologies"] = out["organization_technology_names"].apply(_enrich.truncate_technologies)

    keep = [c for c in _enrich.CORE_COLUMNS if c in out.columns]
    core = out[keep].copy() if not full_dump else out.copy()

    has_email = int(core["email"].notna().sum()) if "email" in core.columns else 0
    has_linkedin = int(core["linkedin_url"].notna().sum()) if "linkedin_url" in core.columns else 0
    return core, out, {"contacts_enriched": len(core), "has_email": has_email, "has_linkedin": has_linkedin,
                       "paid_lookups": paid, "from_cache": len(items) - paid}


def enrich_existing_contacts(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str, email_col: str | None,
                             force_idx: set | None = None, progress=None, max_workers: int = DEFAULT_WORKERS):
    """For sheets that already contain named contacts - fills a missing email
    via Apollo People Match (~1 credit), cached to disk so a re-run is free.
    Rows in force_idx (job changes) always re-fetch, bypassing both the
    'already had email' skip and the cache, since their old email is stale."""
    force_idx = force_idx or set()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))
    cache = _load_cache(_EMAIL_CACHE)

    out = df.copy()
    if "email" not in out.columns:
        out["email"] = out[email_col] if email_col and email_col in out.columns else None
    elif email_col and email_col != "email" and email_col in out.columns:
        out["email"] = out["email"].where(out["email"].notna() & (out["email"].astype(str).str.strip() != ""), out[email_col])

    notes: dict = {}
    already_had = skipped = from_cache = 0
    tasks = []
    for i, row in out.iterrows():
        forced = i in force_idx
        existing_email = row.get("email")
        has_email = existing_email and str(existing_email).strip() and str(existing_email).lower() != "nan"
        if has_email and not forced:
            already_had += 1
            notes[i] = "Already had email"
            continue
        domain = row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            skipped += 1
            notes[i] = "Skipped - no domain"
            continue
        key = _phone.cache_key(row.get(first_col), row.get(last_col), domain)
        if key in cache and not forced:  # reuse prior match -> free
            c = cache[key]
            if c.get("email"):
                out.at[i, "email"] = c["email"]
                from_cache += 1
            notes[i] = f"{c.get('note', 'OK')} (cache)"
            continue
        tasks.append((i, row.get(first_col), row.get(last_col), domain, key, forced))

    def _one(t):
        i, first, last, domain, key, forced = t
        p = _contacts.enrich(session, first, last, domain)
        raw_email = p.get("email", "") or ""
        email, note = _contacts.domain_match_check(raw_email, domain)
        if forced and email:
            note = f"{note} (job-change refresh)"
        return i, (email, note, key), (first or "")

    result_map = _run_parallel(tasks, _one, max_workers, progress)
    filled = 0
    for i, (email, note, key) in result_map.items():
        if email:
            out.at[i, "email"] = email
            filled += 1
        notes[i] = note
        cache[key] = {"email": email, "note": note}
    if result_map:
        _save_cache(_EMAIL_CACHE, cache)

    out["Email Fill Note"] = [notes.get(i, "Lookup error") for i in out.index]
    return out, {
        "already_had_email": already_had, "filled": filled + from_cache, "filled_new": filled,
        "from_cache": from_cache, "skipped_no_domain": skipped, "paid_lookups": len(tasks),
        "job_changes_refreshed": len([1 for t in tasks if t[5]]), "total": len(out),
    }


# Fields enrich_existing_contacts's own Apollo call already returns but used
# to throw away (only "email" was ever kept) - a sheet that came in with
# names/titles/emails/phones already filled still has real gaps here that
# the "already had email" skip meant Apollo was never even asked about.
DETAIL_COLUMNS = ["linkedin_url", "organization_linkedin_url", "organization_industry", "seniority", "departments"]


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def _row_missing_details(row) -> bool:
    return any(_is_blank(row.get(c)) for c in DETAIL_COLUMNS)


def _extract_details(p: dict) -> dict:
    org = p.get("organization") or {}
    departments = p.get("departments")
    if isinstance(departments, list):
        departments = "; ".join(str(d) for d in departments)
    return {
        "linkedin_url": p.get("linkedin_url") or "",
        "organization_linkedin_url": org.get("linkedin_url") or "",
        "organization_industry": org.get("industry") or "",
        "seniority": p.get("seniority") or "",
        "departments": departments or "",
    }


def _bulk_match_resolves_row(row, details: dict) -> bool:
    """True if `details` (from a free bulk_match hit) would leave no
    DETAIL_COLUMNS gap in `row` - used by both count_missing_details and
    fill_missing_details to decide whether the free tier alone was enough,
    or the paid people/match fallback is still needed for this row."""
    return all(not _is_blank(row.get(c)) or details.get(c) for c in DETAIL_COLUMNS)


def count_missing_details(df: pd.DataFrame, domain_col: str = "Domain", email_col: str = "email",
                          max_workers: int = DEFAULT_WORKERS) -> int:
    """Accurate pre-run estimate of what fill_missing_details' PAID tier
    would spend: rows still missing a DETAIL_COLUMNS field after a live,
    free bulk_match-by-email precheck (mirrors
    domain_resolution.count_needs_apollo's philosophy - check the free
    option live before counting something as a credit), that also have a
    domain to fall back to the paid people/match tier with."""
    rows_missing = [(i, row) for i, row in df.iterrows() if _row_missing_details(row)]
    if not rows_missing:
        return 0

    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))

    emails_by_idx = {
        i: str(row.get(email_col)).strip().lower()
        for i, row in rows_missing if not _is_blank(row.get(email_col))
    }
    resolved_idx = set()
    if emails_by_idx:
        bulk_results = _contacts.bulk_match_by_email(session, list(set(emails_by_idx.values())))
        for i, email in emails_by_idx.items():
            match = bulk_results.get(email)
            if match and _bulk_match_resolves_row(df.loc[i], _extract_details(match)):
                resolved_idx.add(i)

    n = 0
    for i, row in rows_missing:
        if i in resolved_idx or _is_blank(row.get(domain_col)):
            continue
        n += 1
    return n


def fill_missing_details(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str = "Domain",
                         email_col: str = "email", progress=None, max_workers: int = DEFAULT_WORKERS):
    """Backfills LinkedIn URL, company LinkedIn URL, industry, seniority, and
    department for an already-enriched sheet's contacts, in two tiers,
    cheapest first:

      1. Apollo's bulk_match, queried BY EMAIL for any row that already has
         one. Per Apollo's own docs and this kit's established usage (see
         scripts/01_apollo_bulk_lookup.py, "Zero credit cost"), enriching a
         contact by an email you already possess doesn't cost a credit -
         unlike asking Apollo to find/reveal an email from a name+domain
         guess, which always does (confirmed: even leaving reveal flags
         unset, people/match still charges once it matches a person with
         email/demographics).
      2. Apollo's people/match by name+domain (~1 credit) - the original,
         costed path - only for rows tier 1 couldn't fully resolve (no
         email to query with, or bulk_match found nothing/incomplete).

    Only touches rows genuinely missing at least one DETAIL_COLUMNS field;
    never overwrites a value the sheet already had."""
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))
    cache = _load_cache(_DETAILS_CACHE)

    out = df.copy()
    for col in DETAIL_COLUMNS:
        if col not in out.columns:
            out[col] = None

    def _apply(i, details) -> int:
        n = 0
        for col in DETAIL_COLUMNS:
            if _is_blank(out.at[i, col]) and details.get(col):
                out.at[i, col] = details[col]
                n += 1
        return n

    fields_filled = 0

    # Tier 1: free bulk_match by email.
    email_candidates = [
        (i, str(row.get(email_col)).strip().lower())
        for i, row in out.iterrows()
        if _row_missing_details(row) and not _is_blank(row.get(email_col))
    ]
    free_lookups = len(email_candidates)
    if email_candidates:
        bulk_results = _contacts.bulk_match_by_email(session, [e for _, e in email_candidates])
        for i, email in email_candidates:
            match = bulk_results.get(email)
            if match:
                fields_filled += _apply(i, _extract_details(match))

    # Tier 2: paid people/match by name+domain, only for rows still missing
    # something (tier 1 skipped or fell short) that have a domain to query.
    tasks = []
    for i, row in out.iterrows():
        if not _row_missing_details(row):
            continue
        domain = row.get(domain_col)
        if _is_blank(domain):
            continue
        key = _phone.cache_key(row.get(first_col), row.get(last_col), domain)
        if key in cache:  # reuse prior paid lookup -> free
            fields_filled += _apply(i, cache[key])
            continue
        tasks.append((i, row.get(first_col), row.get(last_col), domain, key))

    def _one(t):
        i, first, last, domain, key = t
        p = _contacts.enrich(session, first, last, domain)
        return i, (_extract_details(p), key), (first or "")

    result_map = _run_parallel(tasks, _one, max_workers, progress)
    for i, (details, key) in result_map.items():
        cache[key] = details
        fields_filled += _apply(i, details)
    if result_map:
        _save_cache(_DETAILS_CACHE, cache)

    return out, {
        "free_lookups": free_lookups, "paid_lookups": len(tasks),
        "fields_filled": fields_filled, "total": len(out),
    }


def title_matches_any(title: str, target_titles: list[str], exact: bool = True) -> bool:
    """True if `title` matches any of target_titles, using the identical
    word-set-exact or substring-lookalike rule select_candidates_per_persona
    applies during Apollo search - exposed here so filtering an
    ALREADY-ASSEMBLED sheet (e.g. dropping non-ICP existing contacts) uses
    the same definition of "matches this title" rather than a second,
    potentially inconsistent one."""
    if not target_titles:
        return True  # nothing to filter against
    t = (title or "").strip().lower()
    if not t:
        return False
    if exact:
        title_words = _search._title_word_set(title)
        return any(_search._title_word_set(target) == title_words for target in target_titles)
    return any((target or "").strip().lower() in t for target in target_titles)


# Job-title keywords that read as individual-contributor / entry level, but
# ONLY when not paired with a senior qualifier - "Sales Executive" and a bare
# "Associate" are junior, "Chief Executive Officer", "Executive Director" and
# "Executive Vice President" are not. Word-boundary matched, case-insensitive.
JUNIOR_TITLE_KEYWORDS = ("associate", "executive")
SENIOR_TITLE_QUALIFIERS = (
    "chief", "vice president", "vp", "svp", "evp", "president", "director",
    "head", "founder", "owner", "partner", "manager", "ceo", "cfo", "coo",
    "cto", "cmo", "chro", "cpo", "cio",
)
# Apollo's own seniority enum (ALL_SENIORITIES above) is ranked
# owner > founder > c_suite > partner > vp > head > director > manager >
# senior > entry > intern - these three are the only values below "manager".
_JUNIOR_SENIORITY_VALUES = {"senior", "entry", "intern"}


def is_below_manager(title, seniority=None) -> bool:
    """True if a contact reads as below managerial level - powers the opt-in
    'exclude junior titles' pipeline step for sheets that already carry named
    contacts (raw uploads/HubSpot exports), where Apollo's own
    person_seniorities search filter never ran. Two signals: Apollo's
    seniority enum when present (senior/entry/intern = junior), and a
    word-boundary title-keyword check otherwise - a senior qualifier
    (chief/vp/director/head/manager/...) anywhere in the title always wins,
    so "Executive Director" and "Chief Executive Officer" are kept while
    "Sales Executive" and a bare "Associate" are not."""
    s = "" if seniority is None or (isinstance(seniority, float) and pd.isna(seniority)) else str(seniority).strip().lower()
    if s in _JUNIOR_SENIORITY_VALUES:
        return True
    t = "" if title is None or (isinstance(title, float) and pd.isna(title)) else str(title).strip().lower()
    combined = " ".join(x for x in (t, s) if x)
    if not combined:
        return False
    if any(re.search(rf"\b{re.escape(q)}\b", combined) for q in SENIOR_TITLE_QUALIFIERS):
        return False
    return any(re.search(rf"\b{re.escape(kw)}\b", combined) for kw in JUNIOR_TITLE_KEYWORDS)


def count_uncached_phones(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str, force_idx: set | None = None) -> int:
    """How many contacts would actually cost a phone reveal (not in the phone
    cache and have a domain). Cached contacts - including 'no phone on file' -
    are free. force_idx (job changes) always count as a paid lookup."""
    force_idx = force_idx or set()
    cache = _phone.load_cache()
    n = 0
    for i, row in df.iterrows():
        domain = row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            continue
        key = _phone.cache_key(row.get(first_col), row.get(last_col), domain)
        if key not in cache or i in force_idx:
            n += 1
    return n


def enrich_phones(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str,
                  force_idx: set | None = None, progress=None, max_workers: int = DEFAULT_WORKERS):
    force_idx = force_idx or set()
    cache = _phone.load_cache()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))

    out_rows = {}
    need_lookup = []
    for i, row in df.iterrows():
        domain = row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            out_rows[i] = {"Phone Number": "", "Phone Type": "", "Phone Confidence": "", "Phone Note": "No domain", "Phone Source": "Skipped"}
            continue
        key = _phone.cache_key(row.get(first_col), row.get(last_col), domain)
        if key in cache and i not in force_idx:  # job changes bypass the cache
            c = cache[key]
            out_rows[i] = {"Phone Number": c["phone_number"], "Phone Type": c["phone_type"], "Phone Confidence": c["phone_confidence"], "Phone Note": c["note"], "Phone Source": "Cache"}
        else:
            need_lookup.append((i, row, key))

    if need_lookup:
        # Pre-seed so no index can go missing if a submit task errors.
        for i, _row, _key in need_lookup:
            out_rows[i] = {"Phone Number": "", "Phone Type": "", "Phone Confidence": "", "Phone Note": "Lookup error", "Phone Source": "Apollo"}

        token, webhook_url = _phone.create_webhook()
        row_to_person_id = {}
        try:
            # Submit all phone-reveal requests in parallel (each is an
            # independent POST; the results still arrive together via the one
            # shared webhook, which we poll once below).
            def _submit(item):
                i, row, key = item
                pid = _phone.request_phone(session, row.get(first_col), row.get(last_col), row[domain_col], webhook_url)
                return i, (pid, key, row), (row.get(first_col) or "")

            submitted = _run_parallel(need_lookup, _submit, max_workers, progress)
            for i, (pid, key, row) in submitted.items():
                if pid:
                    row_to_person_id[i] = (pid, key, row)
                else:
                    out_rows[i] = {"Phone Number": "", "Phone Type": "", "Phone Confidence": "", "Phone Note": "No person match", "Phone Source": "Apollo"}

            expected_ids = {pid for pid, _, _ in row_to_person_id.values()}
            if progress and expected_ids:
                try:
                    progress(len(need_lookup), len(need_lookup), f"waiting for {len(expected_ids)} phone callbacks")
                except Exception:
                    pass
            results = _phone.poll_webhook_results(token, expected_ids)
        finally:
            _phone.delete_webhook(token)

        for i, (pid, key, row) in row_to_person_id.items():
            payload = results.get(pid)
            if payload is None:
                number, ptype, conf, note = "", "", "", "No phone number on file"
            else:
                number, ptype, conf = _phone.best_phone(payload)
                note = "OK" if number else "No phone number on file"
            out_rows[i] = {"Phone Number": number, "Phone Type": ptype, "Phone Confidence": conf, "Phone Note": note, "Phone Source": "Apollo"}
            cache[key] = {"contact_key": key, "first_name": row.get(first_col), "last_name": row.get(last_col), "domain": row.get(domain_col), "phone_number": number, "phone_type": ptype, "phone_confidence": conf, "note": note}

        _phone.save_cache(cache)

    out_df = pd.DataFrame([out_rows[i] for i in df.index])
    out = pd.concat([df.reset_index(drop=True), out_df], axis=1)
    found = sum(1 for r in out_rows.values() if r["Phone Note"] == "OK")
    return out, {"phones_found": found, "total": len(out)}
