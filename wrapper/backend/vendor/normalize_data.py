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
  - Swaps an initials-only First Name (e.g. "S." or "KMG") with a usable name
    sitting in the other slot, so personalization doesn't address someone as
    "Hi S.,".
  - Repairs mojibake (cp1252/utf-8 mix-ups) and strips invisible/smart-quote
    characters that scrape tools leave behind.
  - Strips LinkedIn-scrape pipe noise ("A2MP | Africa Minerals... | LinkedIn"),
    "a company of X" / "a subsidiary of Y" descriptors, and [DUPE]/[TEST]-style
    quality markers from company names.
  - Strips legal-entity suffixes (Pvt Ltd, LLC, Inc, Corp, GmbH, Sdn Bhd, ...)
    from company names and proper-cases what's left, while preserving short
    ALL-CAPS acronyms (IBM, HDFC, HR) and known brand casing (eBay, PayPal).
  - Never overwrites original columns -- always writes new "Cleaned ..."
    columns next to the originals, so raw data is preserved.

Usage:
    python normalize_data.py <input_file> [output_file]

If output_file is omitted, writes "<input_stem>_normalized.<ext>" next to
the input file (same format: .csv stays .csv, .xlsx stays .xlsx).
"""

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

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
# (e.g. "private limited") are matched before their component words. Covers
# India-focused entity types plus the common global jurisdictions seen in
# scraped/ABM lead lists.
COMPANY_SUFFIXES = [
    "private limited",
    # Bare "private"/"pvt" with no "limited" attached - a common truncation
    # in scraped/exported Indian company names ("Acme Solutions Private").
    "private", "pvt.", "pvt",
    "pvt ltd", "pvt. ltd.", "pvt. ltd", "pte ltd",
    "pte. ltd.", "pte. ltd", "pty ltd", "pty. ltd.", "pty. ltd",
    "public limited company", "limited liability company",
    "limited liability partnership", "one person company", "opc",
    "hindu undivided family", "huf", "sole proprietorship",
    "sdn bhd", "sdn. bhd.", "co., ltd.", "co. ltd.", "co ltd", "co.,ltd",
    "s.a. de c.v.", "sa de cv", "s. de r.l.", "s de rl", "s.r.l.", "s.r.o.",
    "sp. z o.o.", "sp z oo", "d.o.o.", "gesellschaft mit beschrankter haftung",
    "s.a.s.", "s.a.r.l.", "sarl", "sas", "spa", "s.p.a.", "srl", "gmbh",
    "mbh", "ohg", "kgaa", "kg", "ug", "nv", "n.v.", "bv", "b.v.",
    "cv", "vof", "asa", "aps", "oyj", "kft", "zrt", "nyrt",
    "ltda", "ltda.", "eirl", "sac", "s.a.c.", "plc", "p.l.c.",
    "l.l.c.", "l.l.p.", "lllp", "pllc", "p.c.",
    "limited", "ltd.", "ltd", "llp",
    "llc", "inc.", "inc", "incorporated", "corporation", "corp.",
    "corp", "& co.", "& co", "& company", "co.", "co", "company", "ag",
    "kk", "oy", "ab", "s.a.", "sa",
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


# ---------------------------------------------------------------------------
# Text hygiene -- mojibake repair and invisible/smart-punctuation cleanup.
# Scraped lead lists routinely carry cp1252/utf-8 mix-ups ("Great Place To
# Workâ€¢") and non-breaking spaces / smart quotes that break downstream
# string matching (legal-suffix stripping, dedup, merge tags).
# ---------------------------------------------------------------------------

INVISIBLE = {
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "　": " ", "​": "", "‌": "", "‍": "", "﻿": "",
    "­": "", " ": " ", " ": " ",
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "‒": "-", "―": "-", "−": "-",
    "…": "...",
}
_INVIS_RE = re.compile("|".join(map(re.escape, INVISIBLE)))

MOJIBAKE_HINTS = ("Ã©", "Ã¨", "Ã¼", "Ã¶", "Ã±", "Ã¡", "Ã³", "Ã­", "â€™", "â€œ", "â€\x9d", "â€“", "Â ")

EMOJI_RE = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF" "\U00002B00-\U00002BFF" "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF" "™®©✓✔✅❌⭐" "]+", flags=re.UNICODE,
)


def _fix_mojibake(s):
    if not s or not any(h in s for h in MOJIBAKE_HINTS):
        return s
    try:
        return s.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def clean_text(s):
    """Normalize whitespace, invisibles, mojibake, smart punctuation. Never drops letters."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    s = _fix_mojibake(s)
    s = unicodedata.normalize("NFC", s)
    s = _INVIS_RE.sub(lambda m: INVISIBLE[m.group()], s)
    s = EMOJI_RE.sub(" ", s)
    s = re.sub(r"[\t\r\n\f\v]+", " ", s)
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


def _looks_like_formula_injection(s):
    return bool(s) and s[0] in ("=", "+", "@") and re.search(r"[A-Za-z]+\(|![A-Z]", s)


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


# LinkedIn-style banner text pasted into name fields ("Jane Doe | Open to
# Work", "John Smith - Hiring Now").
_NAME_NOISE_RE = re.compile(
    r"\s*[|/•·]\s*.*$|\s*[-–]\s*(?:open to work|#opentowork|hiring|"
    r"we'?re hiring|now hiring|looking for work)\b.*$",
    re.IGNORECASE,
)


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
    text = clean_text(text)
    if _looks_like_formula_injection(text):
        return ""
    text = _NAME_NOISE_RE.sub("", text)
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

    # A First Name column that already holds the whole name (e.g. First =
    # "Ombir Singh", Last = "Singh" duplicated from it) - combine and
    # re-split via split_full_name instead of keeping the multi-word value
    # in First. An explicit, distinct Last value found inside the combined
    # name is trusted over the naive tail split, same as split_full_name's
    # caller does for a real Full Name column.
    if len(first_stripped.split()) > 1:
        combined = (first_stripped + " " + last_stripped).strip() if last_stripped else first_stripped
        first_split, last_split = split_full_name(combined, prefixes, suffixes)
        if last_stripped and last_stripped.lower() != last_split.lower() \
                and last_stripped.lower() in combined.lower():
            last_split = last_stripped
        return proper_case_name(first_split), proper_case_name(last_split)

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


# "Cora, a company of Blank" / ", a subsidiary of X" / "(an Acme company)"
_DESCRIPTOR_RE = re.compile(
    r"""(?:
          \s*[,;\-]\s*(?:an?|the)\s+[^,;]{0,60}?\s*
              (?:company|business|brand|group|firm|venture|entity|subsidiary|
                 division|unit|portfolio\s+company|agency|studio|practice)\b.*$
        | \s*[,;\-]\s*(?:an?|the)\s+
              (?:company|subsidiary|division|unit|brand|part|member|affiliate)\s+of\s+.*$
        | \s*[,;\-]\s*(?:part|member|division|subsidiary|unit|affiliate)\s+of\s+.*$
        | \s*[,;\-]\s*(?:owned|acquired|backed|operated|powered)\s+by\s+.*$
        | \s*[,;\-]\s*(?:d/?b/?a|dba|doing\s+business\s+as|f/?k/?a|fka|
                          formerly\s+known\s+as|formerly|now|nee)\b.*$
        | \s*\(\s*(?:an?|the)\s+[^)]{0,60}?
              (?:company|subsidiary|division|brand|group|business)\s*\)\s*
        | \s*\(\s*(?:part|member|division|subsidiary|unit)\s+of\s+[^)]*\)\s*
        | \s*\(\s*(?:formerly|fka|f\.k\.a\.|dba|d/b/a|now|acquired\s+by)\b[^)]*\)\s*
      )""",
    re.IGNORECASE | re.VERBOSE,
)

# Bracketed/trailing quality markers left by scrape or QA tools.
_QUALITY_MARKER_RE = re.compile(
    r"""(?:
          \s*[\(\[\{]\s*(?:dupe|duplicate|test|testing|inactive|do\s*not\s*use|
              dnu|obsolete|old|delete|deleted|invalid|sample|demo|placeholder|
              xxx|tbd|unverified|needs\s*review|check|archive[d]?)\s*[\)\]\}]\s*
        | [\s,;\-]+(?:dupe|duplicate|do\s*not\s*use|dnu|inactive|obsolete|
              deleted|placeholder|unverified|needs\s*review)\s*$
      )""",
    re.IGNORECASE | re.VERBOSE,
)

# Short words that are real words, not acronyms. When an ALL-CAPS company name
# is re-cased, any short token NOT in this set is assumed to be an acronym and
# kept uppercase, so "FMFE, CPA" survives but "VODAFONE IDEA" -> "Vodafone Idea"
# instead of the false-positive "Vodafone IDEA".
COMMON_SHORT_WORDS = {
    "the", "and", "for", "our", "you", "all", "new", "old", "one", "two", "six",
    "ten", "top", "key", "pro", "max", "web", "net", "sun", "sky", "box", "bay",
    "oak", "red", "big", "way", "car", "air", "gas", "oil", "law", "tax", "pay",
    "buy", "get", "run", "fit", "eat", "joy", "art", "ace", "age", "aim", "arm",
    "bar", "bed", "bit", "bus", "cap", "cat", "cup", "cut", "day", "dog", "ear",
    "egg", "end", "eye", "fan", "far", "few", "fly", "fun", "gap", "gym", "hat",
    "hit", "hot", "ice", "ink", "jar", "job", "kid", "lab", "lap", "leg", "lid",
    "log", "lot", "low", "man", "map", "men", "mix", "now", "nut", "odd", "off",
    "out", "own", "pan", "pen", "pet", "pie", "pig", "pin", "pit", "pot", "pub",
    "raw", "rib", "rim", "row", "rug", "sea", "set", "she", "sit", "ski", "son",
    "tab", "tag", "tan", "tap", "tea", "tie", "tin", "tip", "toe", "ton", "toy",
    "try", "use", "van", "war", "wax", "wet", "win", "zip", "inn", "eco", "bio",
    "real", "test", "best", "care", "home", "life", "work", "tech", "data",
    "food", "bank", "city", "east", "west", "gold", "high", "land", "main",
    "next", "open", "park", "plus", "pure", "road", "safe", "star", "true",
    "view", "wave", "wise", "zero", "blue", "bold", "core", "edge", "fast",
    "fine", "fire", "free", "good", "grow", "help", "idea", "king", "lead",
    "link", "live", "look", "love", "mind", "move", "nova", "only", "path",
    "peak", "plan", "play", "rise", "rock", "sage", "seed", "ship", "site",
    "soft", "solo", "span", "spot", "sure", "team", "time", "tree", "unit",
    "vast", "well", "wide", "wild", "wood", "yard", "your", "auto", "with",
    "from", "into", "over", "more", "less", "each", "both", "some", "such",
}

# Case-preserving brand names that don't proper-case correctly on their own.
BRAND_CASE = {
    "ebay": "eBay", "iphone": "iPhone", "ipad": "iPad", "imac": "iMac",
    "paypal": "PayPal", "youtube": "YouTube", "linkedin": "LinkedIn",
    "github": "GitHub", "gitlab": "GitLab", "whatsapp": "WhatsApp",
    "tiktok": "TikTok", "snapchat": "Snapchat", "salesforce": "Salesforce",
    "hubspot": "HubSpot", "mailchimp": "Mailchimp", "quickbooks": "QuickBooks",
    "wordpress": "WordPress", "woocommerce": "WooCommerce", "bigcommerce": "BigCommerce",
    "shopify": "Shopify", "netsuite": "NetSuite", "servicenow": "ServiceNow",
    "workday": "Workday", "docusign": "DocuSign", "surveymonkey": "SurveyMonkey",
    "zoominfo": "ZoomInfo", "openai": "OpenAI", "deepmind": "DeepMind",
    "xoxoday": "Xoxoday", "loylty": "Loylty", "empuls": "Empuls", "plum": "Plum",
    "freshworks": "Freshworks", "zoho": "Zoho", "postman": "Postman",
    "browserstack": "BrowserStack", "swiggy": "Swiggy", "zomato": "Zomato",
    "flipkart": "Flipkart", "myntra": "Myntra", "makemytrip": "MakeMyTrip",
    "byjus": "BYJU'S", "byju's": "BYJU'S", "paytm": "Paytm", "phonepe": "PhonePe",
    "razorpay": "Razorpay", "mcdonalds": "McDonald's", "mcdonald's": "McDonald's",
    "mckinsey": "McKinsey", "mcafee": "McAfee", "o'reilly": "O'Reilly",
    "oreilly": "O'Reilly", "l'oreal": "L'Oreal",
}


def clean_company_name(value, suffixes):
    if pd.isna(value) or not str(value).strip():
        return ""
    text = clean_text(value)
    if _looks_like_formula_injection(text):
        return ""
    text = _dedupe_pipe_scrape_noise(text)

    if _QUALITY_MARKER_RE.search(text):
        text = _QUALITY_MARKER_RE.sub(" ", text)

    # Bare domain in the company column, e.g. "acme-corp.com".
    if re.fullmatch(r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z]{2,}){1,2}/?", text, re.I):
        host = re.sub(r"^(?:https?://)?(?:www\.)?", "", text, flags=re.I).rstrip("/")
        text = host.split(".")[0].replace("-", " ")

    if _DESCRIPTOR_RE.search(text):
        text = _DESCRIPTOR_RE.sub(" ", text)

    # Remove commas before suffixes, e.g. "Acme, Inc." -> "Acme Inc."
    text = text.replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()

    lowered = text.lower()
    # Try longest suffixes first so multi-word phrases match before their parts
    for suf in suffixes:
        pattern = r"\s+" + re.escape(suf) + r"\.?\s*$"
        if re.search(pattern, lowered):
            candidate = re.sub(pattern, "", text, flags=re.IGNORECASE)
            # Never strip a suffix down to nothing -- "The Company" stays put.
            if candidate.strip(" .,-&/"):
                text = candidate
                lowered = text.lower()

    text = re.sub(r"\s+", " ", text).strip().strip(".,-")

    # "Johnson and Johnson" -> "Johnson & Johnson"
    text = re.sub(r"(?<=\w)\s+and\s+(?=[A-Z])", " & ", text)
    text = re.sub(r"\s*&\s*", " & ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return clean_text(value)

    # Proper-case each word, but preserve short ALL-CAPS acronyms (IBM, HR, HDFC),
    # known brand casing (eBay, PayPal), and intentional mixed-case branding
    # (GreenLeaf) -- a word with more than one uppercase letter that ISN'T
    # all-caps is almost always deliberate stylization, not a typo.
    def cap_word(word):
        low = word.lower().strip(".,&-'")
        if low in BRAND_CASE:
            return BRAND_CASE[low]
        upper_count = sum(1 for c in word if c.isupper())
        if word.isupper() and 1 < len(word) <= 5 and word.isalpha() and low not in COMMON_SHORT_WORDS:
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
