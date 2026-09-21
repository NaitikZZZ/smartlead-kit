"""Excludes accounts that are Xoxoday competitors, per a static reference
list (config.REFERENCE_DIR / "xoxoday-competitors.csv", ~530 companies with
category/threat/notes - see CLAUDE.md's Step 5.5 for the manual-kit
equivalent this mirrors).

Unlike hubspot_exclusion.py, this needs no cache/refresh cycle - it's a
static file shipped with the repo, not a live HubSpot list. Runs in the same
pipeline slot as the company-level HubSpot DNU check (see runner.py's Step 3)
since both are "drop the whole account before spending enrichment credits"
checks; both flow into the same "Exclusion Status"/"Exclusion Reason"
columns, so a row already excluded by one reason is left alone by the other.
"""
from __future__ import annotations

import csv
import difflib
import re
from collections import defaultdict
from functools import lru_cache

from .._lazy import pd

from .. import config
from .hubspot_exclusion import normalize_domain  # shared domain normalization

FUZZY_CUTOFF = 0.88

LEGAL_SUFFIXES = [
    "pvt ltd", "private limited", "pvt. ltd.", "llc", "l.l.c.", "inc", "inc.",
    "incorporated", "ltd", "ltd.", "limited", "corp", "corp.", "corporation",
    "co", "co.", "company", "group", "gmbh", "plc", "llp", "s.a.", "sa",
    "b.v.", "bv",
]


def _normalize_whitespace(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def normalize_company(s) -> str:
    s = _normalize_whitespace(s).lower()
    if not s:
        return ""
    s = re.sub(r"[.,\-&()]", " ", s)
    s = _normalize_whitespace(s)
    words = s.split(" ")
    for suffix in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
        suffix_words = suffix.replace(".", "").split(" ")
        n = len(suffix_words)
        if len(words) > n and words[-n:] == suffix_words:
            words = words[:-n]
            break
    return _normalize_whitespace(" ".join(words))


def competitor_list_path():
    return config.REFERENCE_DIR / "xoxoday-competitors.csv"


@lru_cache(maxsize=1)
def _load_index():
    """(by_company_exact, unique_company_buckets, by_domain, row_count).
    Cached for the life of the process - it's a small (~530 row) static file,
    re-read fresh on every cold start/deploy."""
    path = competitor_list_path()
    if not path.exists():
        return None

    # source file has stray non-UTF-8 bytes in unrelated columns (currency
    # symbols in Revenue/Funding); replace rather than crash since only
    # Name/Website are used for matching.
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))

    by_company_exact = defaultdict(list)
    unique_company_buckets = defaultdict(set)
    by_domain = {}

    for row in rows:
        name = row.get("Name") or row.get("name") or ""
        company_norm = normalize_company(name)
        if company_norm:
            by_company_exact[company_norm].append(row)
            unique_company_buckets[company_norm[:2]].add(company_norm)

        website = row.get("Website") or row.get("website") or ""
        domain_norm = normalize_domain(website)
        if domain_norm and domain_norm not in by_domain:
            by_domain[domain_norm] = row

    return {
        "by_company_exact": by_company_exact,
        "unique_company_buckets": {k: sorted(v) for k, v in unique_company_buckets.items()},
        "by_domain": by_domain,
        "row_count": len(rows),
    }


def _describe(row: dict) -> str:
    name = row.get("Name") or row.get("name") or "(unnamed)"
    threat = row.get("Threat") or row.get("threat")
    category = row.get("Category") or row.get("category")
    bits = [b for b in [category, f"{threat} threat" if threat else None] if b]
    return f"{name}" + (f" ({', '.join(bits)})" if bits else "")


def _match(company: str, domain: str, idx: dict) -> str | None:
    if domain and domain in idx["by_domain"]:
        return f"Domain matches competitor {_describe(idx['by_domain'][domain])}"

    company_norm = normalize_company(company)
    if not company_norm:
        return None
    if company_norm in idx["by_company_exact"]:
        return f"Company name matches competitor {_describe(idx['by_company_exact'][company_norm][0])}"

    bucket = idx["unique_company_buckets"].get(company_norm[:2], [])
    close = difflib.get_close_matches(company_norm, bucket, n=1, cutoff=FUZZY_CUTOFF)
    if close:
        score = difflib.SequenceMatcher(None, company_norm, close[0]).ratio()
        row = idx["by_company_exact"][close[0]][0]
        return f"Company name {score:.0%} similar to competitor {_describe(row)}"
    return None


def run_exclusion_check(df: pd.DataFrame, domain_col: str | None, company_col: str | None = None):
    """Marks each row not already Excluded as Excluded if it matches the
    competitor list (website/email domain, or company name exact/fuzzy).
    Rows already 'Excluded' (e.g. by hubspot_exclusion's company-level check)
    are left untouched - their existing reason stands.

    Output contract matches hubspot_exclusion.run_exclusion_check: sets/updates
    'Exclusion Status' in {'Excluded','OK to reach out'} and 'Exclusion Reason'."""
    idx = _load_index()
    out = df.copy()
    if "Exclusion Status" not in out.columns:
        out["Exclusion Status"] = "OK to reach out"
    if "Exclusion Reason" not in out.columns:
        out["Exclusion Reason"] = ""

    if idx is None:
        stats = {"total": len(out), "excluded": 0,
                  "ok_to_reach_out": int((out["Exclusion Status"] == "OK to reach out").sum()),
                  "competitor_count": 0, "error": f"Competitor list not found at {competitor_list_path()}"}
        return out, stats

    company_col = company_col or next((c for c in df.columns if "company" in c.lower()), None)
    domain_col = domain_col if (domain_col and domain_col in df.columns) else next(
        (c for c in df.columns if any(x in c.lower() for x in ["domain", "website"])), None
    )

    newly_excluded = 0
    for i, row in out.iterrows():
        if row.get("Exclusion Status") == "Excluded":
            continue  # already dropped for another reason - don't relabel
        try:
            company = row.get(company_col) if company_col else ""
            company = "" if pd.isna(company) else str(company)
        except Exception:
            company = ""
        try:
            domain = normalize_domain(row.get(domain_col)) if domain_col else ""
        except Exception:
            domain = ""

        reason = _match(company, domain, idx)
        if reason:
            out.at[i, "Exclusion Status"] = "Excluded"
            out.at[i, "Exclusion Reason"] = reason
            newly_excluded += 1

    stats = {
        "total": len(out),
        "excluded": newly_excluded,
        "ok_to_reach_out": int((out["Exclusion Status"] == "OK to reach out").sum()),
        "competitor_count": idx["row_count"],
        "competitor_list_path": str(competitor_list_path()),
    }
    return out, stats
