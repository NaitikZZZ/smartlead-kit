"""Wraps the 3 existing Apollo scripts directly (search -> reveal email/fields
-> reveal phone), reusing their exact tested logic rather than reimplementing
it. Apollo-only per current scope - Lusha is intentionally not wired in here."""
from __future__ import annotations
import sys
import time

import pandas as pd
import requests

from .. import config

sys.path.insert(0, str(config.SCRIPTS_DIR))
import search_company_contacts_apollo as _search  # noqa: E402
import enrich_full_fields_apollo as _enrich  # noqa: E402
import enrich_phone_apollo as _phone  # noqa: E402
import enrich_contacts_apollo as _contacts  # noqa: E402


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


def enrich_candidates(candidates_df: pd.DataFrame, full_dump: bool = False):
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

    rows = []
    for _, row in candidates_df.iterrows():
        p = _enrich.enrich(session, row["apollo_id"])
        flat = _enrich.flatten_person(p)
        flat["search_company"] = row.get("Company")
        flat["search_domain"] = row.get("Domain")
        email = flat.get("email", "") or ""
        if email:
            _, note = _enrich.domain_match_check(email, row.get("Domain"))
            flat["email_domain_confidence"] = note
        else:
            flat["email_domain_confidence"] = "No email found"
        rows.append(flat)
        time.sleep(0.3)

    out = pd.DataFrame(rows)
    if "organization_technology_names" in out.columns:
        out["technologies"] = out["organization_technology_names"].apply(_enrich.truncate_technologies)

    keep = [c for c in _enrich.CORE_COLUMNS if c in out.columns]
    core = out[keep].copy() if not full_dump else out.copy()

    has_email = int(core["email"].notna().sum()) if "email" in core.columns else 0
    has_linkedin = int(core["linkedin_url"].notna().sum()) if "linkedin_url" in core.columns else 0
    return core, out, {"contacts_enriched": len(core), "has_email": has_email, "has_linkedin": has_linkedin}


def enrich_existing_contacts(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str, email_col: str | None):
    """For sheets that already contain named contacts (not just companies) -
    fills a missing email via Apollo People Match with the standard
    domain-match safety check, but never re-searches for different people and
    never spends a credit on a row that already has an email."""
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

    out = df.copy()
    if "email" not in out.columns:
        out["email"] = out[email_col] if email_col and email_col in out.columns else None
    elif email_col and email_col != "email" and email_col in out.columns:
        out["email"] = out["email"].where(out["email"].notna() & (out["email"].astype(str).str.strip() != ""), out[email_col])

    notes = []
    filled, already_had, skipped = 0, 0, 0
    for i, row in out.iterrows():
        existing_email = row.get("email")
        if existing_email and str(existing_email).strip() and str(existing_email).lower() != "nan":
            already_had += 1
            notes.append("Already had email")
            continue
        domain = row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            skipped += 1
            notes.append("Skipped - no domain")
            continue
        p = _contacts.enrich(session, row.get(first_col), row.get(last_col), domain)
        raw_email = p.get("email", "") or ""
        email, note = _contacts.domain_match_check(raw_email, domain)
        if email:
            out.at[i, "email"] = email
            filled += 1
        notes.append(note)
        time.sleep(0.3)

    out["Email Fill Note"] = notes
    return out, {"already_had_email": already_had, "filled": filled, "skipped_no_domain": skipped, "total": len(out)}


def enrich_phones(df: pd.DataFrame, first_col: str, last_col: str, domain_col: str):
    cache = _phone.load_cache()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))

    out_rows = {}
    need_lookup = []
    for i, row in df.iterrows():
        domain = row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            out_rows[i] = {"Phone Number": "", "Phone Type": "", "Phone Confidence": "", "Phone Note": "No domain", "Phone Source": "Skipped"}
            continue
        key = _phone.cache_key(row.get(first_col), row.get(last_col), domain)
        if key in cache:
            c = cache[key]
            out_rows[i] = {"Phone Number": c["phone_number"], "Phone Type": c["phone_type"], "Phone Confidence": c["phone_confidence"], "Phone Note": c["note"], "Phone Source": "Cache"}
        else:
            need_lookup.append((i, row, key))

    if need_lookup:
        token, webhook_url = _phone.create_webhook()
        row_to_person_id = {}
        try:
            for i, row, key in need_lookup:
                domain = row[domain_col]
                pid = _phone.request_phone(session, row.get(first_col), row.get(last_col), domain, webhook_url)
                if pid:
                    row_to_person_id[i] = (pid, key, row)
                else:
                    out_rows[i] = {"Phone Number": "", "Phone Type": "", "Phone Confidence": "", "Phone Note": "No person match", "Phone Source": "Apollo"}
                time.sleep(0.3)

            expected_ids = {pid for pid, _, _ in row_to_person_id.values()}
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
