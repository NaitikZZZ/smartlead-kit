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


def fetch_hubspot_project(project_id: str) -> dict:
    """Read-only pull of a Project record's ABM campaign fields. Verifies it
    sits in the ABM Campaigns pipeline before returning - if it's on Tyler's
    do-not-use pipelines, that's a signal the ID is wrong."""
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    url = f"https://api.hubapi.com/crm/v3/objects/{config.HUBSPOT_PROJECT_OBJECT}/{project_id}"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"properties": ",".join(HUBSPOT_PROJECT_PROPERTIES)},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    props = data.get("properties", {})
    if props.get("hs_pipeline") != config.HUBSPOT_ABM_PIPELINE_ID:
        raise ValueError(
            f"Project {project_id} is not in the ABM Campaigns pipeline "
            f"(hs_pipeline={props.get('hs_pipeline')!r}). Double-check the record ID."
        )
    target_list_link = (
        props.get("preexisting_list_link_for_enrichment")
        or props.get("campaign_list_link")
        or props.get("campaign_copy_link")
        or ""
    )
    return {
        "project_id": project_id,
        "name": props.get("hs_name", ""),
        "icp": props.get("ideal_customer_profile_icp", ""),
        "region": props.get("region", ""),
        "employee_size": props.get("employee_size", ""),
        "campaign_concept": props.get("campaign_concept", ""),
        "target_list_link": target_list_link,
    }


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
