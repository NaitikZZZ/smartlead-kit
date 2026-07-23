"""ICP Mapper - Load predefined ICPs from Excel and map to Apollo filters."""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

# Path to the ICP Excel file
ICP_FILE = Path(__file__).parent.parent.parent.parent / "reference" / "Use cases & ICP.xlsx"


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


def get_use_case_options() -> Dict[str, List[str]]:
    """Get all available use cases organized by product/category."""
    try:
        sheets = load_icp_workbook()
    except ValueError:
        return {}

    use_cases = {}
    for sheet_name, df in sheets.items():
        if "Use Case" in df.columns:
            cases = df["Use Case"].dropna().unique().tolist()
            use_cases[sheet_name] = sorted(list(set(cases)))

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

    # Filter to the specific use case
    rows = df[df["Use Case"].str.strip() == use_case.strip()]
    if rows.empty:
        return {}

    # Extract data from all matching rows
    row = rows.iloc[0]

    # Extract job titles from Economic Buyer + Champion + Influencer columns
    job_titles = []
    for col in ["Economic Buyer", "Champion", "Influencer / User"]:
        if col in row and pd.notna(row[col]):
            titles = [t.strip() for t in str(row[col]).split(",")]
            job_titles.extend(titles)

    # Extract regions
    regions = []
    if "Target Geographies" in row and pd.notna(row["Target Geographies"]):
        geos = str(row["Target Geographies"]).split(",")
        regions = [normalize_region(g.strip()) for g in geos if g.strip()]

    # Remove duplicates and normalize
    job_titles = list(set(job_titles))
    regions = list(set(filter(None, regions)))

    return {
        "job_titles": job_titles,
        "regions": regions or ["Global"],
        "company_size": None,  # Not in the sheet, can be set separately
        "use_case": use_case,
        "product": product,
        "economic_buyer": str(row.get("Economic Buyer", "")).strip() if "Economic Buyer" in row else "",
        "champion": str(row.get("Champion", "")).strip() if "Champion" in row else "",
        "influencer": str(row.get("Influencer / User", "")).strip() if "Influencer / User" in row else "",
    }


def normalize_region(region_str: str) -> Optional[str]:
    """Normalize region string to Apollo format.

    Maps various region names to standard format.
    """
    region = region_str.strip().upper()

    # Direct matches
    direct_map = {
        "US": "US",
        "USA": "US",
        "UNITED STATES": "US",
        "UK": "UK",
        "UNITED KINGDOM": "UK",
        "GB": "UK",
        "INDIA": "India",
        "IN": "India",
        "EUROPE": "Europe",
        "EU": "Europe",
        "APAC": "APAC",
        "ASIA PACIFIC": "APAC",
        "CANADA": "Canada",
        "CA": "Canada",
        "AUSTRALIA": "Australia",
        "AU": "Australia",
        "GLOBAL": "Global",
        "WORLDWIDE": "Global",
    }

    if region in direct_map:
        return direct_map[region]

    # Partial matches
    for key, value in direct_map.items():
        if key in region or region in key:
            return value

    # If not recognized, return as-is (might be custom region)
    return region if region else None


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

    for col in ["Economic Buyer", "Champion", "Influencer / User"]:
        if col in df:
            for value in df[col].dropna():
                titles = [t.strip() for t in str(value).split(",")]
                all_titles.extend(titles)

    return sorted(list(set(all_titles)))


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
