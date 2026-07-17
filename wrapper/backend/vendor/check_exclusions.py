#!/usr/bin/env python3
"""
Account exclusion checker for Xoxoday ABM/Outbound team.

Checks a prospect list against the master Account Mapping sheet and flags
any prospect that is (or belongs to the same parent as) an existing client
relationship that is NOT fully "Dead".

Exclusion rule
--------------
A matched master row is considered SAFE TO REACH OUT only if BOTH:
    Type 1 == "Dead"
    AND Parent Company Status == "Dead"

If a prospect matches one or more master rows and ANY of those rows has
Type 1 != Dead OR Parent Company Status != Dead -> EXCLUDED.

If a prospect matches no master rows at all -> OK TO REACH OUT (new account,
not in CRM).

Matching is attempted, in order, against:
    1. Domain (exact match after normalization - strip http(s)://, www., 
       trailing slash, lowercase)
    2. Client Name (fuzzy match after normalizing legal suffixes)
    3. Parent Company (fuzzy match after normalizing legal suffixes) -- this
       catches the case where the prospect is a subsidiary/sibling of an
       existing account under the same parent.

Usage
-----
    python check_exclusions.py \
        --master /path/to/Account_Mapping_Sheet.csv \
        --prospects /path/to/prospect_list.csv \
        --output /path/to/output.csv \
        --name-col "Company Name" \
        --domain-col "Domain"

If --name-col / --domain-col are omitted, the script tries to auto-detect
common header names (Company, Company Name, Account Name, Domain, Website).
"""

import argparse
import csv
import difflib
import re
import sys

DEAD = "dead"

MASTER_NAME_COL = "Client Name"
MASTER_DOMAIN_COL = "Domain"
MASTER_PARENT_COL = "Parent Company"
MASTER_TYPE1_COL = "Type 1"
MASTER_PARENT_STATUS_COL = "Parent Company Status"

NAME_CANDIDATES = [
    "Company Name", "Company", "Account Name", "Client Name", "Organization",
    "Prospect Company", "Business Name",
]
DOMAIN_CANDIDATES = [
    "Domain", "Website", "Company Domain", "Website Domain", "URL",
]

LEGAL_SUFFIXES = re.compile(
    r"\b(pvt|private|ltd|limited|llc|inc|incorporated|corp|corporation|"
    r"co|company|llp|plc|gmbh|sa|srl|bv|ag|group|holdings?)\b\.?",
    re.IGNORECASE,
)

FUZZY_THRESHOLD = 0.88


def read_csv_any_encoding(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                return rows, reader.fieldnames
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path} with utf-8 or latin-1")


def normalize_domain(value):
    if not value:
        return ""
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.split("/")[0]
    v = v.rstrip(".")
    return v


def normalize_name(value):
    if not value:
        return ""
    v = value.strip().lower()
    v = LEGAL_SUFFIXES.sub("", v)
    v = re.sub(r"[^a-z0-9]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def auto_detect_col(fieldnames, candidates):
    lower_map = {fn.strip().lower(): fn for fn in fieldnames}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def is_dead(value):
    return (value or "").strip().lower() == DEAD


def build_master_index(master_rows):
    """Build lookup structures keyed by normalized domain / name / parent."""
    by_domain = {}
    by_name = {}
    by_parent = {}
    all_norm_names = []  # (normalized, source_row) for fuzzy fallback
    all_norm_parents = []

    for row in master_rows:
        domain_norm = normalize_domain(row.get(MASTER_DOMAIN_COL, ""))
        name_norm = normalize_name(row.get(MASTER_NAME_COL, ""))
        parent_norm = normalize_name(row.get(MASTER_PARENT_COL, ""))

        if domain_norm:
            by_domain.setdefault(domain_norm, []).append(row)
        if name_norm:
            by_name.setdefault(name_norm, []).append(row)
            all_norm_names.append((name_norm, row))
        if parent_norm:
            by_parent.setdefault(parent_norm, []).append(row)
            all_norm_parents.append((parent_norm, row))

    return {
        "by_domain": by_domain,
        "by_name": by_name,
        "by_parent": by_parent,
        "all_norm_names": all_norm_names,
        "all_norm_parents": all_norm_parents,
    }


def fuzzy_lookup(norm_value, exact_map, all_pairs, threshold=FUZZY_THRESHOLD):
    """Try exact match first, then fuzzy match via difflib ratio."""
    if not norm_value:
        return []
    if norm_value in exact_map:
        return exact_map[norm_value]

    best_ratio = 0.0
    best_rows = []
    seen_keys = set()
    for candidate_norm, row in all_pairs:
        if candidate_norm in seen_keys:
            continue
        ratio = difflib.SequenceMatcher(None, norm_value, candidate_norm).ratio()
        if ratio >= threshold and ratio > best_ratio:
            best_ratio = ratio
            best_rows = exact_map.get(candidate_norm, [row])
            seen_keys.add(candidate_norm)
    return best_rows


def evaluate_prospect(prospect_name, prospect_domain, index):
    """Return (status, reason, matched_rows)."""
    matched_rows = []
    match_basis = None

    domain_norm = normalize_domain(prospect_domain)
    if domain_norm and domain_norm in index["by_domain"]:
        matched_rows = index["by_domain"][domain_norm]
        match_basis = f"domain match ({domain_norm})"

    if not matched_rows:
        name_norm = normalize_name(prospect_name)
        rows = fuzzy_lookup(name_norm, index["by_name"], index["all_norm_names"])
        if rows:
            matched_rows = rows
            match_basis = f"client name match ({prospect_name})"

    if not matched_rows:
        name_norm = normalize_name(prospect_name)
        rows = fuzzy_lookup(name_norm, index["by_parent"], index["all_norm_parents"])
        if rows:
            matched_rows = rows
            match_basis = f"parent company match ({prospect_name})"

    if not matched_rows:
        domain_norm2 = normalize_domain(prospect_domain)
        rows = fuzzy_lookup(domain_norm2, index["by_parent"], index["all_norm_parents"], threshold=0.95)
        if rows:
            matched_rows = rows
            match_basis = f"parent company match via domain ({domain_norm2})"

    if not matched_rows:
        return "OK to reach out", "No match found in Account Mapping sheet (new account)", []

    # Decide exclusion: excluded if ANY matched row has Type1 != Dead OR Parent Status != Dead
    blocking_rows = [
        r for r in matched_rows
        if not (is_dead(r.get(MASTER_TYPE1_COL, "")) and is_dead(r.get(MASTER_PARENT_STATUS_COL, "")))
    ]

    if blocking_rows:
        r = blocking_rows[0]
        reason = (
            f"Excluded - matched via {match_basis}. "
            f"Type 1='{r.get(MASTER_TYPE1_COL, '').strip()}', "
            f"Parent Company Status='{r.get(MASTER_PARENT_STATUS_COL, '').strip()}' "
            f"(both must be 'Dead' to reach out)."
        )
        return "Excluded", reason, matched_rows
    else:
        reason = f"OK to reach out - matched via {match_basis}, but Type 1 and Parent Company Status are both 'Dead'."
        return "OK to reach out", reason, matched_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", required=True, help="Path to master Account Mapping CSV")
    ap.add_argument("--prospects", required=True, help="Path to prospect list CSV")
    ap.add_argument("--output", required=True, help="Path to write annotated output CSV")
    ap.add_argument("--name-col", default=None, help="Column name in prospect file for company name")
    ap.add_argument("--domain-col", default=None, help="Column name in prospect file for domain/website")
    args = ap.parse_args()

    master_rows, master_fields = read_csv_any_encoding(args.master)
    for required in (MASTER_NAME_COL, MASTER_DOMAIN_COL, MASTER_TYPE1_COL, MASTER_PARENT_STATUS_COL):
        if required not in master_fields:
            print(f"ERROR: master sheet missing expected column '{required}'. Found: {master_fields}", file=sys.stderr)
            sys.exit(1)

    prospect_rows, prospect_fields = read_csv_any_encoding(args.prospects)

    name_col = args.name_col or auto_detect_col(prospect_fields, NAME_CANDIDATES)
    domain_col = args.domain_col or auto_detect_col(prospect_fields, DOMAIN_CANDIDATES)

    if not name_col and not domain_col:
        print(
            f"ERROR: could not detect a company-name or domain column in prospect file. "
            f"Found columns: {prospect_fields}. Pass --name-col / --domain-col explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Using prospect name column: {name_col!r}, domain column: {domain_col!r}", file=sys.stderr)

    index = build_master_index(master_rows)

    excluded_count = 0
    ok_count = 0
    out_fields = list(prospect_fields) + ["Exclusion Status", "Exclusion Reason"]

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        for row in prospect_rows:
            pname = row.get(name_col, "") if name_col else ""
            pdomain = row.get(domain_col, "") if domain_col else ""
            status, reason, _matched = evaluate_prospect(pname, pdomain, index)
            if status == "Excluded":
                excluded_count += 1
            else:
                ok_count += 1
            out_row = dict(row)
            out_row["Exclusion Status"] = status
            out_row["Exclusion Reason"] = reason
            writer.writerow(out_row)

    total = excluded_count + ok_count
    print(f"Done. {total} prospects checked -> {excluded_count} Excluded, {ok_count} OK to reach out.", file=sys.stderr)
    print(f"Output written to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
