#!/usr/bin/env python3
"""
normalize_data.py

Normalizes First Name / Last Name / Full Name / Company Name columns in a
CSV or Excel file:
  - Splits a "Full Name" column into First Name + Last Name when First/Last
    don't already exist (middle names fold into Last Name).
  - Strips honorific prefixes (Mr., Dr., Shri, ...) and suffixes (Jr., PhD, ...)
    from names.
  - Proper-cases names (JOHN -> John, o'brien -> O'Brien, mary-jane -> Mary-Jane).
  - Strips legal-entity suffixes (Pvt Ltd, LLC, Inc, Corp, ...) from company
    names and proper-cases what's left, while preserving short ALL-CAPS
    acronyms (IBM, HDFC, HR).
  - Never overwrites original columns -- always writes new "Cleaned ..."
    columns next to the originals, so raw data is preserved.

Usage:
    python normalize_data.py <input_file> [output_file]

If output_file is omitted, writes "<input_stem>_normalized.<ext>" next to
the input file (same format: .csv stays .csv, .xlsx stays .xlsx).
"""

import sys
import re
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Reference lists -- edit these here if the user's data needs more coverage.
# See references/prefixes_suffixes.md for the full lists with explanations.
# ---------------------------------------------------------------------------

NAME_PREFIXES = {
    "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "shri", "smt",
    "sri", "er", "eng", "capt", "col", "maj", "rev", "fr", "sir", "madam",
    "hon", "adv", "ca", "cs", "ar",
}

NAME_SUFFIXES = {
    "jr", "sr", "ii", "iii", "iv", "v", "phd", "ph.d", "md", "m.d", "mba",
    "m.b.a", "esq", "cfa", "cpa", "cma", "cissp", "pmp", "dds", "jd", "llb",
    "llm", "ba", "bsc", "msc", "ma",
}

# Company legal-entity suffixes, longest phrases first so multi-word ones
# (e.g. "private limited") are matched before their component words.
COMPANY_SUFFIXES = [
    "private limited", "pvt ltd", "pvt. ltd.", "pvt. ltd", "pte ltd",
    "pte. ltd.", "pte. ltd", "pty ltd", "pty. ltd.", "pty. ltd",
    "public limited company", "limited liability company",
    "limited liability partnership", "one person company", "opc",
    "hindu undivided family", "huf", "sole proprietorship",
    "limited", "ltd.", "ltd", "llp",
    "llc", "l.l.c.", "inc.", "inc", "incorporated", "corporation", "corp.",
    "corp", "& co.", "& co", "& company", "co.", "co", "company", "gmbh", "plc", "s.a.", "sa", "ag",
    "s.r.l.", "srl", "bv", "n.v.", "nv", "kk", "oy", "ab",
]

FULL_NAME_COL_CANDIDATES = ["full name", "name", "contact name", "prospect name"]
FIRST_NAME_COL_CANDIDATES = ["first name", "firstname", "given name"]
LAST_NAME_COL_CANDIDATES = ["last name", "lastname", "surname", "family name"]
COMPANY_COL_CANDIDATES = ["company name", "company", "organization", "organisation", "account name"]


def find_column(columns, candidates):
    """Case-insensitive, whitespace-tolerant lookup of a column name."""
    normalized = {c.strip().lower(): c for c in columns}
    for cand in candidates:
        if cand in normalized:
            return normalized[cand]
    return None


_INITIAL_VOWELS = set("aeiouy")  # "y" counts as a vowel here so real names
# like "Lynn" or "Kim" aren't mistaken for initials.


def _looks_like_initials(token: str) -> bool:
    """True for a token that reads as initials rather than a usable first
    name: a single letter (with or without a trailing period, e.g. "S."),
    or a short (2-5 letter) vowel-less run of letters (e.g. "KMG")."""
    t = token.strip(". ")
    if not t or not t.isalpha():
        return False
    if len(t) == 1:
        return True
    return 2 <= len(t) <= 5 and not any(c.lower() in _INITIAL_VOWELS for c in t)


def _looks_like_a_name(text: str) -> bool:
    """True if `text` reads as an actual name rather than initials/junk -
    has at least one vowel and at least 2 letters."""
    letters = re.sub(r"[^a-zA-Z]", "", text or "")
    return len(letters) >= 2 and any(c.lower() in _INITIAL_VOWELS for c in letters)


def strip_prefix_suffix_tokens(text, prefixes, suffixes):
    """Remove honorific/degree tokens wherever they appear in the name.

    Titles and suffixes (Mr., Jr., PhD...) essentially never double as a
    real given/family name, so it's safe -- and necessary -- to strip them
    from anywhere in the string, not just the very first/last token. This
    matters for names like "Mr. Robert Jr. Johnson" where the suffix sits
    in the middle rather than at the end.
    """
    if not text:
        return text
    tokens = text.strip().split()
    if not tokens:
        return text

    def clean_token(t):
        return t.strip(".,").lower()

    combined = prefixes | suffixes
    kept = [t for t in tokens if clean_token(t) not in combined]
    return " ".join(kept).strip()


def proper_case_name(text):
    """Title-case a name, handling apostrophes, hyphens, and Mc/Mac prefixes."""
    if not text:
        return text

    def cap_word(word):
        if not word:
            return word
        # Handle hyphenated parts (Mary-Jane) and apostrophes (O'Brien) separately
        parts = re.split(r"(-|')", word)
        out = []
        for i, part in enumerate(parts):
            if part in ("-", "'"):
                out.append(part)
                continue
            if not part:
                out.append(part)
                continue
            lower = part.lower()
            # Mc/Mac special-case: McDonald, MacArthur
            if lower.startswith("mc") and len(lower) > 2:
                out.append("Mc" + lower[2:3].upper() + lower[3:])
            elif lower.startswith("mac") and len(lower) > 3:
                out.append("Mac" + lower[3:4].upper() + lower[4:])
            else:
                out.append(lower[:1].upper() + lower[1:])
        return "".join(out)

    words = text.strip().split()
    return " ".join(cap_word(w) for w in words)


def split_full_name(full_name, prefixes, suffixes):
    """Split a full name into (first_name, last_name). Middle name folds into last."""
    if not full_name or not str(full_name).strip():
        return "", ""
    cleaned = strip_prefix_suffix_tokens(str(full_name), prefixes, suffixes)
    tokens = cleaned.split()
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    # A first name that's really just initials (e.g. "S." or "KMG") isn't
    # usable for personalization - "Hi S.," reads badly. If the next token
    # looks like an actual name, swap them so the real name leads instead
    # (e.g. "KMG Stephen" -> first "Stephen", last "KMG").
    if _looks_like_initials(tokens[0]) and _looks_like_a_name(tokens[1]):
        tokens[0], tokens[1] = tokens[1], tokens[0]
    first = tokens[0]
    last = " ".join(tokens[1:])  # middle name(s) fold into last name
    return first, last


def finalize_first_last(first_raw, last_raw, prefixes, suffixes):
    """Cleans an already-split First Name / Last Name pair, applying the
    same initials-swap as split_full_name: if First is just initials (e.g.
    "KMG") and Last starts with an actual name (e.g. "Stephen"), swap them."""
    first_stripped = strip_prefix_suffix_tokens(
        str(first_raw) if first_raw and not pd.isna(first_raw) else "", prefixes, suffixes)
    last_stripped = strip_prefix_suffix_tokens(
        str(last_raw) if last_raw and not pd.isna(last_raw) else "", prefixes, suffixes)
    last_tokens = last_stripped.split()
    if _looks_like_initials(first_stripped) and last_tokens and _looks_like_a_name(last_tokens[0]):
        first_stripped, last_stripped = last_tokens[0], " ".join([first_stripped] + last_tokens[1:])
    return proper_case_name(first_stripped), proper_case_name(last_stripped)


def _dedupe_pipe_scrape_noise(text: str) -> str:
    """A LinkedIn-scraped company field often looks like
    "A2MP | Africa Minerals and Metals Processing Platform | LinkedIn" - an
    acronym, its full expansion, and the site name, pipe-separated. Drop the
    "LinkedIn" noise and keep the longest remaining segment (the expanded,
    readable name) instead of the acronym."""
    if "|" not in text:
        return text
    segments = [s.strip() for s in text.split("|") if s.strip() and s.strip().lower() != "linkedin"]
    if not segments:
        return text
    return max(segments, key=len)


def clean_company_name(value, suffixes):
    if pd.isna(value) or not str(value).strip():
        return ""
    text = str(value).strip()
    text = _dedupe_pipe_scrape_noise(text)
    # Remove commas before suffixes, e.g. "Acme, Inc." -> "Acme Inc."
    text = text.replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()

    lowered = text.lower()
    # Try longest suffixes first so multi-word phrases match before their parts
    for suf in suffixes:
        pattern = r"\s+" + re.escape(suf) + r"\.?\s*$"
        if re.search(pattern, lowered):
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
            lowered = text.lower()

    text = re.sub(r"\s+", " ", text).strip().strip(".,-")

    # Proper-case each word, but preserve short ALL-CAPS acronyms (IBM, HR, HDFC)
    # and intentional mixed-case branding (GreenLeaf, PayPal, eBay) -- a word
    # with more than one uppercase letter that ISN'T all-caps is almost always
    # deliberate stylization, not a typo, so leave it as typed.
    def cap_word(word):
        upper_count = sum(1 for c in word if c.isupper())
        if word.isupper() and 1 < len(word) <= 5 and word.isalpha():
            return word
        if upper_count > 1 and not word.isupper() and word.isalpha():
            return word
        return proper_case_name(word)

    return " ".join(cap_word(w) for w in text.split())


def process_dataframe(df):
    columns = list(df.columns)
    full_name_col = find_column(columns, FULL_NAME_COL_CANDIDATES)
    first_name_col = find_column(columns, FIRST_NAME_COL_CANDIDATES)
    last_name_col = find_column(columns, LAST_NAME_COL_CANDIDATES)
    company_col = find_column(columns, COMPANY_COL_CANDIDATES)

    report = []

    if first_name_col and last_name_col:
        finalized = df.apply(
            lambda row: finalize_first_last(row[first_name_col], row[last_name_col], NAME_PREFIXES, NAME_SUFFIXES),
            axis=1,
        )
        df["Cleaned First Name"] = finalized.apply(lambda t: t[0])
        df["Cleaned Last Name"] = finalized.apply(lambda t: t[1])
        report.append(f"Cleaned existing '{first_name_col}' / '{last_name_col}' columns.")
    elif full_name_col:
        split = df[full_name_col].apply(lambda v: split_full_name(v, NAME_PREFIXES, NAME_SUFFIXES))
        df["Cleaned First Name"] = split.apply(lambda t: proper_case_name(t[0]))
        df["Cleaned Last Name"] = split.apply(lambda t: proper_case_name(t[1]))
        report.append(f"Split '{full_name_col}' into Cleaned First Name / Cleaned Last Name.")
    else:
        report.append("No First/Last Name or Full Name column found -- skipped name normalization.")

    if company_col:
        df["Cleaned Company Name"] = df[company_col].apply(lambda v: clean_company_name(v, COMPANY_SUFFIXES))
        report.append(f"Cleaned '{company_col}' into Cleaned Company Name.")
    else:
        report.append("No Company Name column found -- skipped company normalization.")

    return df, report


def load_file(path):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path), "excel"
    return pd.read_csv(path), "csv"


def save_file(df, path, file_type):
    path = Path(path)
    if file_type == "excel":
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False)


def main():
    if len(sys.argv) < 2:
        print("Usage: python normalize_data.py <input_file> [output_file]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    df, file_type = load_file(input_path)
    df, report = process_dataframe(df)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        suffix = ".xlsx" if file_type == "excel" else ".csv"
        output_path = input_path.with_name(input_path.stem + "_normalized" + suffix)

    save_file(df, output_path, file_type)

    print(f"Saved: {output_path}")
    for line in report:
        print(f"- {line}")


if __name__ == "__main__":
    main()
