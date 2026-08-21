"""Assembles the deliverable files for a run:
  01_accounts_processed.csv   - normalized + domain-resolved + exclusion-checked account list
  02_enriched_contacts.csv    - full Apollo enrichment (OK-to-reach-out accounts only)
  03_hubspot_import_ready.csv - verified-email subset, mapped to HubSpot properties + campaign_title
  SUMMARY.md                  - human-readable run summary: what happened and why
"""
from __future__ import annotations
import re
import math
from pathlib import Path

import pandas as pd

try:
    from datetime import datetime, UTC
except ImportError:  # Python <3.11 has no datetime.UTC
    from datetime import datetime, timezone
    UTC = timezone.utc

from .. import vercel_blob

SENIORITY_MAP = {"c_suite": "C suite", "vp": "VP", "head": "Head", "director": "Director", "manager": "Manager"}


def write_file(run_dir: Path, filename: str, content: bytes | str, content_type: str | None = None) -> str:
    """Writes a run output file to local disk (still needed same-request, e.g.
    github_pr.py reads these paths directly) AND, when Vercel Blob is
    configured, uploads it too - keyed deterministically as
    runs/{run_id}/{filename}, so a LATER, separate request (the file download
    route, or run_confirmed_import reading hubspot_ready.json back) can fetch
    it by run_id + filename alone, without needing to persist a reference
    anywhere. Always returns str(run_dir / filename) - unchanged from before
    Blob existed - since that's all any caller has ever needed for display
    (only the filename is ever shown/used, via Path(p).name)."""
    path = run_dir / filename
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)
    if vercel_blob.is_configured():
        vercel_blob.put(f"runs/{run_dir.name}/{filename}", content, content_type=content_type)
    return str(path)


def read_file(run_dir: Path, filename: str) -> bytes:
    """Reads back a file written by write_file() - from Blob when configured
    (even if this process never wrote it locally, e.g. a different serverless
    invocation handled the original run step), otherwise from local disk."""
    if vercel_blob.is_configured():
        return vercel_blob.get(vercel_blob.url_for(f"runs/{run_dir.name}/{filename}"))
    return (run_dir / filename).read_bytes()


def file_exists(run_dir: Path, filename: str) -> bool:
    if vercel_blob.is_configured():
        return vercel_blob.exists(f"runs/{run_dir.name}/{filename}")
    return (run_dir / filename).exists()


def bucket_employees(n):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return None
    n = int(n)
    if n <= 50:
        return "0 - 50"
    if n <= 200:
        return "51 - 200"
    if n <= 500:
        return "201 - 500"
    if n <= 1000:
        return "501 - 1000"
    if n <= 5000:
        return "1001 - 5000"
    if n <= 10000:
        return "5001 - 10000"
    return "10000+"


def strip_url_prefix(domain):
    if not domain or (isinstance(domain, float) and math.isnan(domain)):
        return domain
    return re.sub(r"^https?://(www\.)?", "", str(domain)).rstrip("/")


# Contact property "demographics" (label "Demographics (Geography)") is a
# locked enumeration on the live Xoxoday portal - confirmed via a read-only
# properties lookup, exactly 9 allowed values (shown as label -> value below).
# Sending anything else 400s the whole batch, same failure mode as the
# duplicate-email bug. Country names are matched case-insensitively; anything
# not in this table but still having SOME location signal (country/state/city)
# falls back to "Rest of the World" rather than being left blank, per the
# "mandatory if you have any location info" rule.
DEMOGRAPHICS_BY_COUNTRY = {
    "india": "India",
    "united states": "US/ Canada", "united states of america": "US/ Canada", "usa": "US/ Canada", "us": "US/ Canada",
    "canada": "US/ Canada",
    "united kingdom": "Europe Region", "uk": "Europe Region", "great britain": "Europe Region",
    "germany": "Europe Region", "france": "Europe Region", "netherlands": "Europe Region",
    "spain": "Europe Region", "italy": "Europe Region", "ireland": "Europe Region",
    "belgium": "Europe Region", "switzerland": "Europe Region", "sweden": "Europe Region",
    "poland": "Europe Region", "portugal": "Europe Region", "austria": "Europe Region",
    "saudi arabia": "KSA + LENA",
    "united arab emirates": "GCC  and Turkey", "uae": "GCC  and Turkey", "qatar": "GCC  and Turkey",
    "kuwait": "GCC  and Turkey", "bahrain": "GCC  and Turkey", "oman": "GCC  and Turkey", "turkey": "GCC  and Turkey",
    "south africa": "Africa", "nigeria": "Africa", "kenya": "Africa", "egypt": "Africa",
    "philippines": "Rest  APAC", "indonesia": "Rest  APAC", "singapore": "Rest  APAC",
    "malaysia": "Rest  APAC", "thailand": "Rest  APAC", "vietnam": "Rest  APAC",
    "australia": "Rest  APAC", "new zealand": "Rest  APAC", "japan": "Rest  APAC",
    "china": "Rest  APAC", "hong kong": "Rest  APAC", "south korea": "Rest  APAC",
}
DEMOGRAPHICS_FALLBACK = "Rest of the World"


def demographics_for(country, state, city) -> str | None:
    if not (country or state or city):
        return None  # no location signal at all - nothing to derive, leave blank
    if country:
        match = DEMOGRAPHICS_BY_COUNTRY.get(str(country).strip().lower())
        if match:
            return match
    return DEMOGRAPHICS_FALLBACK


def build_hubspot_import_file(enriched_df: pd.DataFrame, campaign_title: str) -> pd.DataFrame:
    """Mirrors the mapping validated against the live Xoxoday HubSpot portal
    this session - only fields with a confirmed HubSpot property. The raw
    domain goes to "website" (free text), NOT "company_domain" (confirmed via
    a read-only properties lookup: that's a locked picklist with 8 unrelated
    fixed values on this portal - sending an arbitrary domain there 400s)."""
    verified = enriched_df[enriched_df.get("email_status") == "verified"].copy() if "email_status" in enriched_df.columns else enriched_df.copy()

    def clean(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    rows = []
    for _, row in verified.iterrows():
        country, state, city = clean(row.get("country")), clean(row.get("state")), clean(row.get("city"))
        domain = clean(row.get("company_domain")) or strip_url_prefix(clean(row.get("Domain")))
        rows.append({
            "firstname": clean(row.get("first_name")),
            "lastname": clean(row.get("last_name")),
            "email": clean(row.get("email")),
            "jobtitle": clean(row.get("title")),
            "phone": clean(row.get("Phone Number")),
            "hs_linkedin_url": clean(row.get("linkedin_url")),
            "company": clean(row.get("organization_name") or row.get("search_company")),
            "company_linkedin_url": clean(row.get("organization_linkedin_url")),
            "website": domain,
            "industry": clean(row.get("organization_industry")),
            "numemployees": bucket_employees(row.get("organization_estimated_num_employees")),
            "annualrevenue": clean(row.get("organization_annual_revenue")),
            "total_funding": clean(row.get("organization_total_funding")),
            "technologies": clean(row.get("technologies")),
            "seniority_level": SENIORITY_MAP.get(row.get("seniority")),
            "country": country,
            "state": state,
            "address": clean(row.get("formatted_address")),
            "city": city,
            "demographics": demographics_for(country, state, city),
            "department___job_function__apollo_": clean(row.get("departments")),
            "campaign_title": campaign_title,
        })
    if not rows:
        # pd.DataFrame([]) has zero columns, not just zero rows - build_channel_files'
        # email_df["email"] filter then KeyErrors instead of yielding an empty file.
        return pd.DataFrame(columns=[
            "firstname", "lastname", "email", "jobtitle", "phone", "hs_linkedin_url", "company",
            "company_linkedin_url", "website", "industry", "numemployees", "annualrevenue", "total_funding",
            "technologies", "seniority_level", "country", "state", "address", "city", "demographics",
            "department___job_function__apollo_", "campaign_title",
        ])
    return pd.DataFrame(rows)


def _clean_cell(v):
    # Handle pandas Series (extract scalar value)
    if isinstance(v, pd.Series):
        return None if v.empty else _clean_cell(v.iloc[0]) if len(v) > 0 else None

    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _company_of(row):
    return _clean_cell(row.get("organization_name") or row.get("search_company"))


# Shared by both linkedin_upload.csv and calling_upload.csv - every channel
# file carries the SAME full set of whatever was found, matching everything
# build_hubspot_import_file fills for the email file (name/title/seniority,
# company + firmographics, every contact channel, location, campaign) - not
# just its own primary field. A HeyReach automation branching on "is there an
# email" (or a dialer script wanting a LinkedIn URL to hand the SDR) needs
# the other channels' data present on the same row, not stripped out.
# Row-INCLUSION still differs per file (see build_channel_files); only the
# column set is unified and matched to the HubSpot file's breadth.
_CHANNEL_COLUMNS = [
    "first_name", "last_name", "job_title", "seniority", "departments",
    "company_name", "company_domain", "organization_linkedin_url", "organization_industry",
    "employee_count", "annual_revenue", "total_funding", "technologies",
    "email", "linkedin_url", "phone",
    "city", "state", "country", "address", "demographics",
    "campaign_title",
]


def _channel_record(row, campaign_title: str) -> dict:
    country = _clean_cell(row.get("country"))
    state = _clean_cell(row.get("state"))
    city = _clean_cell(row.get("city"))
    return {
        "first_name": _clean_cell(row.get("first_name")),
        "last_name": _clean_cell(row.get("last_name")),
        "job_title": _clean_cell(row.get("title")),
        "seniority": _clean_cell(row.get("seniority")),
        "departments": _clean_cell(row.get("departments")),
        "company_name": _company_of(row),
        "company_domain": _clean_cell(row.get("company_domain")) or strip_url_prefix(_clean_cell(row.get("Domain"))),
        "organization_linkedin_url": _clean_cell(row.get("organization_linkedin_url")),
        "organization_industry": _clean_cell(row.get("organization_industry")),
        "employee_count": bucket_employees(row.get("organization_estimated_num_employees")),
        "annual_revenue": _clean_cell(row.get("organization_annual_revenue")),
        "total_funding": _clean_cell(row.get("organization_total_funding")),
        "technologies": _clean_cell(row.get("technologies")),
        "email": _clean_cell(row.get("email")),
        "linkedin_url": _clean_cell(row.get("linkedin_url")),
        "phone": _clean_cell(row.get("Phone Number")) or _clean_cell(row.get("mobile_phone")),
        "city": city,
        "state": state,
        "country": country,
        "address": _clean_cell(row.get("formatted_address")),
        "demographics": demographics_for(country, state, city),
        "campaign_title": campaign_title,
    }


def build_channel_files(enriched_df: pd.DataFrame, campaign_title: str) -> dict[str, pd.DataFrame]:
    """Splits the enriched contacts into three channel-specific upload files:

      email_upload.csv    - verified-email contacts only (HubSpot-ready shape).
                            Guarantees no blank-email rows ever reach HubSpot,
                            since HubSpot's contact upsert is keyed by email.
      linkedin_upload.csv  - contacts that have a LinkedIn URL (HeyReach import).
      calling_upload.csv   - contacts that have a phone number (dialer/SDR list).

    A contact can legitimately land in more than one file - that's expected,
    each channel gets whoever it can actually reach on that channel. Every
    row in linkedin/calling carries the same full column set (_CHANNEL_COLUMNS)
    regardless of which file it's in, so e.g. calling_upload.csv still has
    linkedin_url and email whenever they're known, not just phone.
    """
    if enriched_df is None or enriched_df.empty:
        empty = pd.DataFrame()
        return {"email": empty, "linkedin": empty, "calling": empty}

    # Email file reuses the validated HubSpot mapping (verified email only).
    email_df = build_hubspot_import_file(enriched_df, campaign_title)
    email_df = email_df[email_df["email"].apply(lambda v: bool(_clean_cell(v)))].copy()

    linkedin_rows, calling_rows = [], []
    for _, row in enriched_df.iterrows():
        li = _clean_cell(row.get("linkedin_url"))
        phone = _clean_cell(row.get("Phone Number")) or _clean_cell(row.get("mobile_phone"))
        if li is None and phone is None:
            continue

        record = _channel_record(row, campaign_title)
        if li is not None:
            linkedin_rows.append(record)
        if phone is not None:
            calling_rows.append(record)

    return {
        "email": email_df,
        "linkedin": pd.DataFrame(linkedin_rows, columns=_CHANNEL_COLUMNS),
        "calling": pd.DataFrame(calling_rows, columns=_CHANNEL_COLUMNS),
    }


def _pct(n, total):
    return f"{(n / total * 100):.1f}%" if total else "-"


def build_summary_markdown(campaign_title: str, stats: dict, accounts_processed: pd.DataFrame, import_result: dict | None = None) -> str:
    lines = [
        f"# Run summary: {campaign_title}",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    norm = stats.get("normalization", {})
    if norm.get("notes"):
        lines += ["## Normalization", ""] + [f"- {n}" for n in norm["notes"]] + [""]

    completeness = stats.get("completeness", {})
    lines.append("## Completeness check")
    if completeness.get("skipped"):
        lines.append(f"- Skipped: {completeness.get('reason', 'n/a')}")
    else:
        lines.append(f"- Filled {completeness.get('filled', 0)} gap(s) across fields: {', '.join(completeness.get('fields_tracked', []))}")
        if completeness.get("errors"):
            lines.append(f"- {len(completeness['errors'])} lookup error(s) (not fatal, those rows just stayed blank)")
    if completeness.get("second_pass") and not completeness["second_pass"].get("skipped"):
        lines.append(f"- Second pass (pre-Apollo): filled {completeness['second_pass'].get('filled', 0)} more")
    lines.append("")

    exclusion = stats.get("exclusion", {})
    lines.append("## Exclusion check")
    if exclusion.get("skipped"):
        lines.append(f"- Skipped by user - all {exclusion.get('total', '?')} account(s) treated as OK to reach out")
    else:
        total = exclusion.get("total", 0)
        excluded = exclusion.get("excluded", 0)
        if exclusion.get("dnu_list_id"):
            lines.append(f"- Source: HubSpot DNU list `{exclusion['dnu_list_id']}` ({exclusion.get('dnu_domains', '?')} do-not-use domains)")
        lines.append(f"- {total} checked -> **{excluded} excluded** ({_pct(excluded, total)}), {exclusion.get('ok_to_reach_out', 0)} OK to reach out")
        excluded_rows = exclusion.get("excluded_rows") or []
        if excluded_rows:
            lines.append("")
            lines.append("| Company | Domain | Why excluded |")
            lines.append("|---|---|---|")
            for r in excluded_rows:
                reason = str(r.get("reason", "")).replace("|", "/")
                lines.append(f"| {r.get('company', '')} | {r.get('domain', '')} | {reason} |")
            if excluded > len(excluded_rows):
                lines.append(f"\n_(+{excluded - len(excluded_rows)} more excluded, not listed)_")
    lines.append("")

    search = stats.get("apollo_search", {})
    enrich = stats.get("apollo_enrich", {})
    phone = stats.get("apollo_phone", {})
    lines.append("## Enrichment")
    if search.get("skipped") and enrich.get("skipped"):
        reason = search.get("reason") or enrich.get("reason") or "skipped by user"
        lines.append(f"- Skipped: {reason}")
    else:
        if not search.get("skipped"):
            lines.append(f"- Searched {search.get('companies_searched', 0)} account(s), found {search.get('candidates_found', 0)} candidate(s)")
            if search.get("zero_match_companies"):
                lines.append(f"- **{len(search['zero_match_companies'])} account(s) had zero Apollo matches**: {', '.join(search['zero_match_companies'])}")
        contacts_enriched = enrich.get("contacts_enriched") or enrich.get("total", 0)
        has_email = enrich.get("has_email", 0)
        lines.append(f"- {contacts_enriched} contact(s) processed, {has_email} with a verified email ({_pct(has_email, contacts_enriched)})")
        if not phone.get("skipped"):
            phone_total = phone.get("total", contacts_enriched)
            lines.append(f"- {phone.get('phones_found', 0)} with a phone number ({_pct(phone.get('phones_found', 0), phone_total)})")
    lines.append("")

    cost = stats.get("cost")
    if cost and cost.get("breakdown"):
        agg = {}
        for b in cost["breakdown"]:
            a = agg.setdefault(b["operation"], {"credits": 0, "usd": 0.0})
            a["credits"] += b["credits"]
            a["usd"] = round(a["usd"] + b["usd"], 2)
        label = {"domain_resolution": "Domain resolution", "email_reveal": "Email reveal", "mobile_phone": "Phone (calling)"}
        lines.append("## Apollo cost")
        for op in ("domain_resolution", "email_reveal", "mobile_phone"):
            if op in agg:
                lines.append(f"- {label[op]}: {agg[op]['credits']} credits (${agg[op]['usd']:.2f})")
        lines.append(f"- **Total: {cost.get('credits', 0)} credits (${cost.get('usd', 0):.2f})**")
        lines.append("")

    channels = stats.get("channel_counts")
    if channels:
        lines.append("## Channel files")
        lines.append(f"- Email (HubSpot-ready, verified email only): {channels.get('email', 0)}")
        lines.append(f"- LinkedIn (HeyReach import): {channels.get('linkedin', 0)}")
        lines.append(f"- Calling (dialer list): {channels.get('calling', 0)}")
        lines.append("")

    lines.append("## HubSpot")
    lines.append(f"- {stats.get('hubspot_ready_count', 0)} contact(s) ready for import (verified email only)")
    if import_result:
        lines.append(f"- Imported: {import_result['total']} total ({import_result['new']} new, {import_result['updated']} updated)")
        if import_result.get("list"):
            lines.append(f"- Added to list: {import_result['list']['list_url']}")
        for kind, assoc in import_result.get("associations", {}).items():
            lines.append(f"- Associated with {kind} `{assoc['record_id']}`: {assoc['associated']} contact(s)")
        hr = import_result.get("heyreach") or {}
        if hr.get("status") == "pushed":
            lines.append(f"- HeyReach list `{hr.get('list_name')}` (id {hr.get('list_id')}): {hr.get('pushed', 0)} LinkedIn lead(s) pushed")
        elif hr.get("status") not in (None, "skipped"):
            lines.append(f"- HeyReach: {hr.get('message', hr.get('status'))}")
    else:
        lines.append("- Not yet imported")
    lines.append("")

    return "\n".join(lines)


def write_outputs(run_dir: Path, accounts_processed: pd.DataFrame, enriched: pd.DataFrame, campaign_title: str, stats: dict):
    run_dir.mkdir(parents=True, exist_ok=True)

    refs = {
        "01_accounts_processed.csv": write_file(run_dir, "01_accounts_processed.csv", accounts_processed.to_csv(index=False), "text/csv"),
        "02_enriched_contacts.csv": write_file(run_dir, "02_enriched_contacts.csv", enriched.to_csv(index=False), "text/csv"),
    }

    # Three channel-specific deliverables. The email file IS the HubSpot import.
    channels = build_channel_files(enriched, campaign_title)
    refs["email_upload.csv"] = write_file(run_dir, "email_upload.csv", channels["email"].to_csv(index=False), "text/csv")
    refs["linkedin_upload.csv"] = write_file(run_dir, "linkedin_upload.csv", channels["linkedin"].to_csv(index=False), "text/csv")
    refs["calling_upload.csv"] = write_file(run_dir, "calling_upload.csv", channels["calling"].to_csv(index=False), "text/csv")

    stats["channel_counts"] = {
        "email": int(len(channels["email"])),
        "linkedin": int(len(channels["linkedin"])),
        "calling": int(len(channels["calling"])),
    }
    refs["SUMMARY.md"] = write_file(run_dir, "SUMMARY.md", build_summary_markdown(campaign_title, stats, accounts_processed), "text/markdown")

    return refs, channels["email"]
