"""ICP Mapper - Load predefined ICPs from Excel and map to Apollo filters."""
from __future__ import annotations

import re
from .._lazy import pd
from typing import Dict, List, Optional

from .. import config

# Path to the ICP Excel file. Was previously hand-counting parent dirs from
# this file's own location and landing one level short (wrapper/reference/
# instead of smartlead-kit/reference/) - always 404ing, silently, since every
# caller here catches the resulting ValueError and degrades to a manual
# fallback. Reuse config's already-correct SMARTLEAD_KIT_DIR instead.
ICP_FILE = config.SMARTLEAD_KIT_DIR / "reference" / "Use cases & ICP.xlsx"

# Shared source-of-truth copy, so the UI can link back to it for a human to
# check/edit rather than just trusting the extracted mapping blind.
ICP_SHEET_URL = (
    "https://giift-my.sharepoint.com/:x:/r/personal/manoj_xoxoday_com/_layouts/15/Doc.aspx"
    "?sourcedoc=%7B4A9C3D68-43AE-467E-8D0F-9537BB88E92C%7D&file=Use%20cases%20&%20ICP.xlsx="
    "&fromShare=true&action=default&mobileredirect=true"
)


def load_icp_workbook() -> Dict[str, pd.DataFrame]:
    """Load all sheets from the ICP Excel file."""
    try:
        xls = pd.ExcelFile(ICP_FILE)
        sheets = {}
        for sheet_name in xls.sheet_names:
            sheets[sheet_name] = pd.read_excel(ICP_FILE, sheet_name=sheet_name)
        return sheets
    except FileNotFoundError:
        raise ValueError(f"ICP file not found: {ICP_FILE}")


def _find_col(columns, candidates: List[str]) -> Optional[str]:
    """Case-insensitive column match: exact first, then substring - so
    "Economic Buyer (brand side)" matches candidate "economic buyer", and
    "Use Case (popular in US / Europe)" matches candidate "use case". Sheets
    in the real workbook don't all use identical headers."""
    lower_map = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for cand in candidates:
        for header, original in lower_map.items():
            if cand.lower() in header:
                return original
    return None


def _split_titles(raw) -> List[str]:
    """Job-title cells in the real sheet aren't consistently comma-separated -
    most use " / " ("CHRO / CPO"), some use commas ("HRBP, Comp & Benefits
    manager"). Split on whichever the cell actually contains; never split on a
    bare "/" with no surrounding spaces, since that appears inside a single
    compound title ("Regional sales/marketing manager")."""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return []
    if "," in s:
        parts = s.split(",")
    elif " / " in s:
        parts = s.split(" / ")
    else:
        parts = [s]
    return [p.strip() for p in parts if p.strip()]


def get_use_case_options() -> Dict[str, List[str]]:
    """Get all available use cases organized by product/category."""
    try:
        sheets = load_icp_workbook()
    except ValueError:
        return {}

    use_cases = {}
    for sheet_name, df in sheets.items():
        use_case_col = _find_col(df.columns, ["use case"])
        if use_case_col:
            cases = df[use_case_col].dropna().unique().tolist()
            use_cases[sheet_name] = sorted(set(str(c).strip() for c in cases))

    return use_cases


def map_use_case_to_icp(product: str, use_case: str) -> Dict:
    """Map a use case to structured ICP filters.

    Returns:
    {
        "job_titles": ["VP HR", "Head of People", ...],
        "regions": ["US", "Europe", ...],
        "company_size": "50-200",
        "use_case": "Total Rewards",
        "economic_buyer": "...",
        "champion": "...",
        "influencer": "..."
    }
    """
    try:
        sheets = load_icp_workbook()
    except ValueError:
        return {}

    if product not in sheets:
        return {}

    df = sheets[product]
    use_case_col = _find_col(df.columns, ["use case"])
    if not use_case_col:
        return {}
    economic_buyer_col = _find_col(df.columns, ["economic buyer"])
    champion_col = _find_col(df.columns, ["champion"])
    influencer_col = _find_col(df.columns, ["influencer / user", "influencer"])
    geo_col = _find_col(df.columns, ["target geographies", "target geography"])

    # Filter to the specific use case
    rows = df[df[use_case_col].astype(str).str.strip() == use_case.strip()]
    if rows.empty:
        return {}

    # Extract data from all matching rows
    row = rows.iloc[0]

    # Extract job titles from Economic Buyer + Champion + Influencer columns
    job_titles = []
    for col in (economic_buyer_col, champion_col, influencer_col):
        if col and pd.notna(row.get(col)):
            job_titles.extend(_split_titles(row[col]))

    # Extract regions
    regions = []
    if geo_col and pd.notna(row.get(geo_col)):
        geos = str(row[geo_col]).split(",")
        regions = [normalize_region(g.strip()) for g in geos if g.strip()]

    # Remove duplicates and normalize
    job_titles = list(dict.fromkeys(job_titles))  # de-dupe, keep first-seen order
    regions = list(set(filter(None, regions)))

    return {
        "job_titles": job_titles,
        "regions": regions or ["Global"],
        "company_size": None,  # Not in the sheet, can be set separately
        "use_case": use_case,
        "product": product,
        "economic_buyer": str(row.get(economic_buyer_col, "")).strip() if economic_buyer_col else "",
        "champion": str(row.get(champion_col, "")).strip() if champion_col else "",
        "influencer": str(row.get(influencer_col, "")).strip() if influencer_col else "",
    }


_REGION_MAP = {
    "US": "US",
    "USA": "US",
    "UNITED STATES": "US",
    "UK": "UK",
    "UNITED KINGDOM": "UK",
    "GB": "UK",
    "INDIA": "India",
    "EUROPE": "Europe",
    "EU": "Europe",
    "APAC": "APAC",
    "ASIA PACIFIC": "APAC",
    "CANADA": "Canada",
    "CA": "Canada",
    "AUSTRALIA": "Australia",
    "AU": "Australia",
    "GCC": "GCC",
    "GULF": "GCC",
    "GULF COOPERATION COUNCIL": "GCC",
    "MIDDLE EAST": "GCC",
    "ME": "GCC",
    "KSA": "KSA",
    "SAUDI ARABIA": "KSA",
    "AFRICA": "Africa",
    "PHILIPPINES": "Philippines",
    "INDONESIA": "Indonesia",
    "SEA": "SEA",
    "SOUTHEAST ASIA": "SEA",
    "SOUTH EAST ASIA": "SEA",
    "GLOBAL": "Global",
    "WORLDWIDE": "Global",
    "ALL REGIONS": "Global",
}
# Sorted longest-key-first so "MIDDLE EAST" matches before a shorter key could
# ever accidentally win on a tie (not currently possible, but keeps this safe
# if more overlapping keys are added later).
_REGION_MAP_BY_LEN = sorted(_REGION_MAP.items(), key=lambda kv: -len(kv[0]))


def normalize_region(region_str: str) -> Optional[str]:
    """Normalize a free-text geography string to one of our region labels.

    Uses whole-word matching (not raw substring containment) - a prior version
    used bare "in region" checks, which meant the 2-letter code "ID" (Indonesia)
    matched *inside* "MIDDLE EAST" (mIDdle) and silently mis-tagged it. Real
    sheet text is messy free-form ("USA (leader), Europe", "All regions (esp.
    India, ME, SEA)"), so this scans for any known token as its own word rather
    than requiring an exact full-string match.
    """
    region = region_str.strip().upper()
    if not region:
        return None

    if region in _REGION_MAP:
        return _REGION_MAP[region]

    for key, value in _REGION_MAP_BY_LEN:
        if re.search(rf"\b{re.escape(key)}\b", region):
            return value

    # Not recognized - return as-is (might be a custom/unmapped region)
    return region


def get_all_job_titles_for_product(product: str) -> List[str]:
    """Get all unique job titles mentioned in a product's use cases."""
    try:
        sheets = load_icp_workbook()
    except ValueError:
        return []

    if product not in sheets:
        return []

    df = sheets[product]
    all_titles = []

    for col in (
        _find_col(df.columns, ["economic buyer"]),
        _find_col(df.columns, ["champion"]),
        _find_col(df.columns, ["influencer / user", "influencer"]),
    ):
        if col:
            for value in df[col].dropna():
                all_titles.extend(_split_titles(value))

    return sorted(set(all_titles))


def get_all_regions_for_product(product: str) -> List[str]:
    """Get all unique regions mentioned in a product's use cases."""
    try:
        sheets = load_icp_workbook()
    except ValueError:
        return []

    if product not in sheets:
        return []

    df = sheets[product]
    all_regions = []

    if "Target Geographies" in df:
        for value in df["Target Geographies"].dropna():
            geos = [normalize_region(g.strip()) for g in str(value).split(",")]
            all_regions.extend(geos)

    return sorted(list(set(filter(None, all_regions))))


if __name__ == "__main__":
    # Test
    print("Available products:")
    options = get_use_case_options()
    for product, cases in options.items():
        print(f"\n{product}:")
        for case in cases[:3]:
            print(f"  - {case}")
            mapping = map_use_case_to_icp(product, case)
            print(f"    Titles: {', '.join(mapping.get('job_titles', [])[:2])}")
            print(f"    Regions: {', '.join(mapping.get('regions', []))}")
