"""Turns one of the 3 supported input sources into a working DataFrame plus
metadata. CSV rows are always the actual source of target-account data - the
HubSpot Project source additionally pulls campaign metadata (ICP, region,
priority) to carry through to the campaign_title convention and to the
Project association at import time, but the account rows themselves still
come from a CSV, since linked target-list files (SharePoint/Drive) usually
sit behind auth we can't fetch programmatically.
"""
from __future__ import annotations
import io
import re
import requests
import pandas as pd

from .. import config

HUBSPOT_PROJECT_PROPERTIES = [
    "hs_name", "hs_status", "hs_pipeline", "hs_pipeline_stage",
    "campaign_concept", "campaign_copy_link", "campaign_list_link",
    "preexisting_list_link_for_enrichment", "event_campaign_request_type",
    "ideal_customer_profile_icp", "region", "employee_size", "priority_explanation",
]


def read_csv_bytes(data: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {filename} as CSV (tried utf-8, latin-1)")


def extract_project_id(value: str) -> str:
    """Accept a raw record ID OR a pasted HubSpot record URL like
    https://app-na2.hubspot.com/contacts/6512810/record/0-970/816184961752/
    and return just the numeric record ID."""
    v = str(value).strip().rstrip("/")
    if v.isdigit():
        return v
    m = re.search(r"/record/[^/]+/(\d+)", v)  # .../record/<objectType>/<id>
    if m:
        return m.group(1)
    m = re.search(r"(\d{5,})/?$", v)  # trailing numeric id fallback
    if m:
        return m.group(1)
    return v


def fetch_hubspot_project(project_id: str) -> dict:
    """Read-only pull of a Project record's ABM campaign fields. Accepts a raw
    ID or a pasted record URL. Verifies it sits in the ABM Campaigns pipeline
    before returning - if it's on a do-not-use pipeline, the ID is likely wrong."""
    project_id = extract_project_id(project_id)
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    url = f"https://api.hubapi.com/crm/v3/objects/{config.HUBSPOT_PROJECT_OBJECT}/{project_id}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"properties": ",".join(HUBSPOT_PROJECT_PROPERTIES)},
        timeout=15,
    )
    if r.status_code == 404:
        raise ValueError(f"No Project record found for id {project_id}. Check the link/ID.")
    r.raise_for_status()
    data = r.json()
    props = data.get("properties", {})
    if props.get("hs_pipeline") != config.HUBSPOT_ABM_PIPELINE_ID:
        raise ValueError(
            f"Project {project_id} is not in the ABM Campaigns pipeline "
            f"(hs_pipeline={props.get('hs_pipeline')!r}). Double-check the link/record ID."
        )
    # Scan ALL project fields for links (a list is often pasted inside the
    # campaign concept, not the list field). Pick the DATA source from whatever
    # is found: a spreadsheet is the target list; a webpage may hold the list;
    # a doc is campaign copy (not data).
    links = extract_project_links(props)
    spreadsheets = [l for l in links if l["kind"] == "spreadsheet"]
    webpages = [l for l in links if l["kind"] == "webpage"]
    docs = [l for l in links if l["kind"] in ("document", "presentation")]

    if spreadsheets:
        target_list_link, list_kind = spreadsheets[0]["url"], "spreadsheet"
    elif webpages:
        target_list_link, list_kind = webpages[0]["url"], "webpage"
    else:
        target_list_link, list_kind = "", ("document" if docs else "none")
    copy_link = props.get("campaign_copy_link", "") or (docs[0]["url"] if docs else "")

    return {
        "project_id": project_id,
        "name": props.get("hs_name", ""),
        "status": props.get("hs_status", ""),
        "icp": props.get("ideal_customer_profile_icp", ""),
        "region": props.get("region", ""),
        "employee_size": props.get("employee_size", ""),
        "priority_explanation": props.get("priority_explanation", ""),
        "request_type": props.get("event_campaign_request_type", ""),
        "campaign_concept": props.get("campaign_concept", ""),
        "campaign_copy_link": copy_link,
        "campaign_list_link": props.get("campaign_list_link", ""),
        "target_list_link": target_list_link,
        "list_link_kind": list_kind,  # spreadsheet | webpage | document | none
        "links": links,               # every URL found across all fields, classified
    }


def classify_link(url: str) -> str:
    """'spreadsheet' (Excel/CSV/Google Sheet = DATA to enrich), 'document'
    (Word/Google Doc = campaign COPY, not data), 'presentation', 'none', or
    'unknown'. Handles SharePoint/OneDrive web markers (/:x:/ /:w:/ /:p:/),
    Google Docs URLs, and file extensions."""
    u = (url or "").strip().lower()
    if not u:
        return "none"
    base = u.split("?")[0].split("#")[0]
    if "docs.google.com/spreadsheets" in u or "/:x:/" in u:
        return "spreadsheet"
    if "docs.google.com/document" in u or "/:w:/" in u:
        return "document"
    if "docs.google.com/presentation" in u or "/:p:/" in u:
        return "presentation"
    if base.endswith((".xlsx", ".xls", ".csv", ".tsv")):
        return "spreadsheet"
    if base.endswith((".docx", ".doc", ".rtf", ".gdoc")):
        return "document"
    if base.endswith((".pptx", ".ppt")):
        return "presentation"
    if u.startswith("http"):
        return "webpage"
    return "unknown"


_URL_RE = re.compile(r"https?://[^\s)\]}<>\"']+")

# Project fields scanned for links, in priority order (a spreadsheet in a
# dedicated list field beats one mentioned in the concept text).
_LINK_FIELDS = [
    "preexisting_list_link_for_enrichment", "campaign_list_link",
    "campaign_concept", "priority_explanation", "campaign_copy_link",
    "ideal_customer_profile_icp",
]


def extract_project_links(props: dict) -> list[dict]:
    """Pull every URL out of all project text fields, classified and de-duped,
    so a list mentioned inside the campaign concept (not just the list field)
    is still discovered. Returns [{url, kind, field}]."""
    seen, out = set(), []
    for field in _LINK_FIELDS:
        text = props.get(field)
        if not text:
            continue
        for m in _URL_RE.findall(str(text)):
            url = m.rstrip(".,);'\"")
            if url in seen:
                continue
            seen.add(url)
            out.append({"url": url, "kind": classify_link(url), "field": field})
    return out


def is_link_autofetchable(url: str) -> bool:
    """True if we can pull the list without a login: a Google Sheet or a direct
    CSV/XLSX link. SharePoint/Drive/other links behind auth return False, so
    the UI can prompt the user to open, download, and upload it instead."""
    u = (url or "").strip().lower()
    if not u:
        return False
    if "docs.google.com/spreadsheets" in u:
        return True
    if u.split("?")[0].split("#")[0].endswith((".csv", ".xlsx", ".xls")):
        return True
    return False


def _rewrite_google_sheets_export(url: str) -> str | None:
    m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        return None
    sheet_id = m.group(1)
    gid_match = re.search(r"[?&#]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_form_link(url: str) -> pd.DataFrame:
    """Best-effort fetch of a target-list link: direct CSV/XLSX links and
    Google Sheets links work; anything requiring interactive auth (SharePoint,
    private Drive) will fail with a clear message asking for a CSV instead."""
    fetch_url = url
    if "docs.google.com/spreadsheets" in url:
        rewritten = _rewrite_google_sheets_export(url)
        if rewritten:
            fetch_url = rewritten

    try:
        r = requests.get(fetch_url, timeout=20, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(
            f"Could not fetch {url} directly ({e}). If this is a SharePoint/"
            f"Drive link behind login, download it and upload as CSV instead."
        )

    content_type = r.headers.get("content-type", "")
    if url.lower().endswith((".csv",)) or "csv" in content_type:
        return read_csv_bytes(r.content, "form_link.csv")
    if url.lower().endswith((".xlsx", ".xls")) or "spreadsheet" in content_type:
        return read_csv_bytes(r.content, "form_link.xlsx")
    # Google Sheets export with no extension still returns text/csv-ish content
    try:
        return read_csv_bytes(r.content, "form_link.csv")
    except Exception:
        raise ValueError(
            f"Fetched {url} but couldn't parse it as CSV/Excel (content-type={content_type!r}). "
            f"Download it and upload as CSV instead."
        )
