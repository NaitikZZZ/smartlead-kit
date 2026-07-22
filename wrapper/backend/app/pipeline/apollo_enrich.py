"""Wraps the 3 existing Apollo scripts directly (search -> reveal email/fields
-> reveal phone), reusing their exact tested logic rather than reimplementing
it. Apollo-only per current scope - Lusha is intentionally not wired in here."""
from __future__ import annotations
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .. import config

sys.path.insert(0, str(config.SCRIPTS_DIR))
import search_company_contacts_apollo as _search  # noqa: E402
import enrich_full_fields_apollo as _enrich  # noqa: E402
import enrich_phone_apollo as _phone  # noqa: E402
import enrich_contacts_apollo as _contacts  # noqa: E402

import json as _json

DEFAULT_WORKERS = 8

# Local reveal caches so a re-run never re-pays Apollo for the same person:
#   email  -> keyed name@domain (People Match, ~1 credit)
#   person -> keyed apollo_id  (full-field reveal, ~1 credit)
# Phone has its own cache in the phone script (reference/phone_reveal_cache.csv).
_EMAIL_CACHE = config.CACHE_DIR / "email_reveal_cache.json"
_PERSON_CACHE = config.CACHE_DIR / "person_enrich_cache.json"


def _load_cache(path):
    try:
        return _json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _save_cache(path, cache):
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


def search_candidates(df: pd.DataFrame, company_col: str, domain_col: str, person_locations=None, persona_titles=None, max_per_company=None):
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

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
            people = _search.search_people(session, domain, person_locations)
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
    _save_cache(_EMAIL_CACHE, cache)

    out["Email Fill Note"] = [notes.get(i, "Lookup error") for i in out.index]
    return out, {
        "already_had_email": already_had, "filled": filled + from_cache, "filled_new": filled,
        "from_cache": from_cache, "skipped_no_domain": skipped, "paid_lookups": len(tasks),
        "job_changes_refreshed": len([1 for t in tasks if t[5]]), "total": len(out),
    }


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
