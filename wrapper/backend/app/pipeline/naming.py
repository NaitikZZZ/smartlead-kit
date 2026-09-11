"""Best-effort campaign_title suggestion per docs/campaign-naming-convention.md
(PRIORITY_TEAM_USECASE_REGION_CHANNEL_POCNAME_STARTDATE). Always a suggestion,
never final - the run pauses and shows this as an editable default so the
user can accept or override it (region/use-case/channel are frequently
ambiguous enough that guessing wrong silently would be worse than asking)."""
from __future__ import annotations
import re

from .._lazy import pd

REGION_CODES = {
    "saudi arabia": "KSA", "ksa": "KSA", "indonesia": "IDN", "united states": "US",
    "usa": "US", "uae": "GCC", "united arab emirates": "GCC", "qatar": "GCC",
    "bahrain": "GCC", "kuwait": "GCC", "oman": "GCC", "africa": "AFR", "india": "IND",
    "philippines": "PHL", "uk": "UKEU", "united kingdom": "UKEU", "europe": "UKEU",
}


def _priority_from_project_name(name: str) -> str:
    m = re.match(r"^(P[0-3])_", name or "", re.IGNORECASE)
    return m.group(1).upper() if m else "P2"


def _poc_token(project_meta: dict, default_poc: str) -> str:
    """Requestor + campaign owner first names (from the linked HubSpot
    Project), per docs/campaign-naming-convention.md's 2026-09-11 update.
    Falls back to default_poc when either name wasn't resolved (missing
    property, owner lookup failed, or no linked Project at all)."""
    requestor = (project_meta or {}).get("requestor_name")
    owner = (project_meta or {}).get("owner_name")
    if requestor and owner:
        return f"{requestor}{owner}"
    return owner or requestor or default_poc.title()


def _region_code(df: pd.DataFrame, region_col: str | None) -> str:
    if not region_col or region_col not in df.columns:
        return "ROW"
    countries = {str(c).strip().lower() for c in df[region_col].dropna().unique()}
    codes = sorted({REGION_CODES[c] for c in countries if c in REGION_CODES})
    if not codes:
        return "ROW"
    return "-".join(codes)


def suggest_campaign_title(project_meta: dict, df: pd.DataFrame, region_col: str | None, default_poc: str = "naitik") -> str:
    priority = _priority_from_project_name(project_meta.get("name", "")) if project_meta else "P2"
    region = _region_code(df, region_col)
    usecase = "CUSTOM-ENRICHMENT"
    channel = "EMAIL"
    poc = _poc_token(project_meta, default_poc)
    from datetime import datetime
    today = datetime.now()
    start_date = f"{today.day:02d}{today.strftime('%b').upper()}{str(today.year)[-2:]}"
    title = f"{priority}_ABM_{usecase}_{region}_{channel}_{poc}_{start_date}"
    project_id = (project_meta or {}).get("project_id")
    return f"{title}_{project_id}" if project_id else title
