"""Convert the SMB hunting dream Tech SaaS lists (Compass + Empuls)
into Smartlead-ready prospects.csv files.

Source: ~/Downloads/SMB hunting dream Accounts - Tech Saas(<Product> data).csv
Output: outputs/smb_techsaas_<product>/prospects.csv with these columns:
  first_name, last_name, email, company_name, phone_number, website,
  location, linkedin_profile, job_title, tier, personalized_line
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
KIT_ROOT = Path("/Users/naitikchavda/Event Auto push/smartlead-kit")
OUTPUT_ROOT = KIT_ROOT / "outputs"

CAMPAIGNS = [
    {
        "product": "compass",
        "src": DOWNLOADS / "SMB hunting dream Accounts - Tech Saas(Compass data).csv",
        "dst": OUTPUT_ROOT / "smb_techsaas_compass" / "prospects.csv",
    },
    {
        "product": "empuls",
        "src": DOWNLOADS / "SMB hunting dream Accounts - Tech Saas(Empuls data).csv",
        "dst": OUTPUT_ROOT / "smb_techsaas_empuls" / "prospects.csv",
    },
]

OUT_FIELDS = [
    "first_name",
    "last_name",
    "email",
    "company_name",
    "phone_number",
    "website",
    "location",
    "linkedin_profile",
    "job_title",
    "tier",
    "segment",
    "personalized_line",
]

# For Compass: emails of leads whose role is partner/channel-flavored.
# Seeded from manual audit of the 26-lead list. Update if list changes.
CHANNEL_LEAD_EMAILS = {
    "vipul.mathur@spectra.co",          # Spectranet, Sales Head Business WiFi
    "rakesh@atlys.com",                  # Atlys, Head of Sales (B2B) and Head B2B Channel Sales
    "rakesh.banga@atlys.com",            # Atlys, Head of B2B Channel Sales (alt email if present)
    "tejas.s@emudhra.com",               # Emudhra, Sales Partner
}

# Channel cue words for any future-list pattern matching fallback.
CHANNEL_TITLE_CUES = (
    "channel",
    "partner",
    "alliance",
    "reseller",
    "distributor",
)


def classify_segment(product: str, email: str, title: str) -> str:
    if product != "compass":
        return "primary"  # Empuls audience does not split here
    if email.strip().lower() in CHANNEL_LEAD_EMAILS:
        return "channel"
    t = (title or "").lower()
    if any(cue in t for cue in CHANNEL_TITLE_CUES):
        return "channel"
    return "direct"


def pick_phone(row: dict) -> str:
    for col in ("Mobile Phone", "Work Direct Phone", "Other Phone", "Company Phone"):
        v = (row.get(col) or "").strip().lstrip("'")
        if v:
            return v
    return ""


def pick_location(row: dict) -> str:
    parts = [row.get("City") or "", row.get("State") or "", row.get("Country") or ""]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def tier_from_employees(emp: str) -> str:
    try:
        n = int((emp or "0").replace(",", "").strip() or "0")
    except ValueError:
        return "3"
    if n >= 1500:
        return "1"
    if n >= 500:
        return "2"
    return "3"


def personalized_line(product: str, row: dict) -> str:
    company = (row.get("Company Name for Emails") or "").strip()
    title = (row.get("Title") or "").strip()
    industry = (row.get("Industry") or "").strip()
    headcount = (row.get("# Employees") or "").strip()

    if product == "compass":
        return (
            f"Saw you lead Sales at {company} ({headcount} FTE, {industry}). "
            "Most VP Sales in this band tell us comp is still on Sheets, curious if that maps."
        )
    return (
        f"Saw you lead People at {company} ({headcount} FTE, {industry}). "
        "Most HR teams in this band run R&R across 4 places, curious if that maps."
    )


def convert(src: Path, dst: Path, product: str) -> int:
    if not src.exists():
        print(f"[skip] missing source: {src}", file=sys.stderr)
        return 0

    dst.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_no_email = 0

    with src.open(newline="", encoding="utf-8-sig") as fin, dst.open("w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUT_FIELDS)
        writer.writeheader()

        for row in reader:
            email = (row.get("Email") or "").strip()
            if not email or "@" not in email:
                skipped_no_email += 1
                continue

            title = (row.get("Title") or "").strip()
            writer.writerow({
                "first_name": (row.get("First Name") or "").strip(),
                "last_name": (row.get("Last Name") or "").strip(),
                "email": email,
                "company_name": (row.get("Company Name for Emails") or "").strip(),
                "phone_number": pick_phone(row),
                "website": (row.get("Website") or "").strip(),
                "location": pick_location(row),
                "linkedin_profile": (row.get("Person Linkedin Url") or "").strip(),
                "job_title": title,
                "tier": tier_from_employees(row.get("# Employees") or ""),
                "segment": classify_segment(product, email, title),
                "personalized_line": personalized_line(product, row),
            })
            written += 1

    print(f"[{product}] wrote {written} rows to {dst} (skipped {skipped_no_email} rows with no email)")
    return written


def main() -> int:
    total = 0
    for c in CAMPAIGNS:
        total += convert(c["src"], c["dst"], c["product"])
    print(f"done. total prospects: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
