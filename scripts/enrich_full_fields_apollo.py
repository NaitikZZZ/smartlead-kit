"""
Full-field Apollo enrichment - captures every field Apollo returns for a
person (dynamically, not a hardcoded subset), for when the deliverable is
"give me everything Apollo has," not just the curated email/phone columns
enrich_contacts_apollo.py produces.

Reveals email (reveal_personal_emails=True) by default. Phone is NOT
revealed here - it costs ~8x as much per hit and should be a deliberate,
separate decision (see enrich_phone_apollo.py).

Every row keeps its LinkedIn URL if Apollo has one, and its email if found,
regardless of which one was the "primary" ask - nothing gets dropped for
being the "wrong" channel.

The domain-match check (same one used elsewhere in this pipeline) still
runs, but only as an added confidence column here - it does NOT filter any
row out.

Default output is the CORE_COLUMNS set (confirmed standard as of the SEA
run) - contact identity, location, role signals, and core firmographics.
Pass --full for the complete raw Apollo dump instead (oversized tech-stack
fields still get split into a companion file either way, since some cells
run past spreadsheet cell-length limits).

Usage:
    python3 enrich_full_fields_apollo.py <input_csv> <output_csv> [--full]
Input CSV needs: apollo_id, Company, Domain columns (from search_company_contacts_apollo.py).
"""
import os
import sys
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from enrich_contacts_apollo import domain_match_check

load_dotenv()
APOLLO_KEY = os.environ.get('APOLLO_API_KEY')

# Confirmed standard default - Contact core, Location, Role signals, and
# Company firmographics. "Give me the full Apollo dump" is opt-in (--full),
# this curated set is opt-out. Updated 2026-07-08: dropped id/postal_code
# (not useful), added 'technologies' (truncated - see TECH_TRUNCATE_LIMIT).
CORE_COLUMNS = [
    # Contact core
    'first_name', 'last_name', 'name', 'linkedin_url', 'title', 'headline', 'email', 'email_status',
    # Location
    'city', 'state', 'country', 'formatted_address', 'time_zone',
    # Role signals
    'departments', 'subdepartments', 'seniority', 'functions', 'employment_history',
    # Company firmographics
    'organization_name', 'organization_website_url', 'organization_industry',
    'organization_estimated_num_employees', 'organization_annual_revenue', 'organization_total_funding',
    'organization_linkedin_url', 'technologies',
    'organization_organization_headcount_six_month_growth',
    'organization_organization_headcount_twelve_month_growth',
    'organization_organization_headcount_twenty_four_month_growth',
    # Pipeline traceability (not raw Apollo fields, but needed to know which search/company a row came from)
    'search_company', 'search_domain', 'email_domain_confidence',
]

# organization_technology_names can run to 40,000+ characters for a large
# enterprise (hundreds of detected tools) - past Excel's 32,767-char cell
# limit on its own. Truncate to the first N tools rather than excluding the
# field entirely; the full untruncated list still goes to the companion
# _extended_fields.csv via the oversized-column split below.
TECH_TRUNCATE_LIMIT = 40


def truncate_technologies(raw_json):
    if not raw_json or pd.isna(raw_json):
        return ''
    try:
        techs = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return str(raw_json)[:2000]
    if len(techs) <= TECH_TRUNCATE_LIMIT:
        return '; '.join(techs)
    return '; '.join(techs[:TECH_TRUNCATE_LIMIT]) + f' ... (+{len(techs) - TECH_TRUNCATE_LIMIT} more, see _extended_fields.csv)'


def flatten_person(p):
    """Dynamically flattens whatever Apollo returns - one level deep for
    nested dicts (prefixed), joined strings for simple lists, JSON for
    anything more complex. Doesn't assume a fixed schema."""
    flat = {}
    for k, v in p.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                key = f'{k}_{k2}'
                if isinstance(v2, (dict, list)):
                    flat[key] = json.dumps(v2, default=str)
                else:
                    flat[key] = v2
        elif isinstance(v, list):
            if v and all(isinstance(x, (str, int, float)) for x in v):
                flat[k] = '; '.join(str(x) for x in v)
            else:
                flat[k] = json.dumps(v, default=str)
        else:
            flat[k] = v
    return flat


def enrich(session, apollo_id):
    try:
        r = session.post(
            'https://api.apollo.io/api/v1/people/match',
            headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'x-api-key': APOLLO_KEY},
            json={'id': apollo_id, 'reveal_personal_emails': True},
            timeout=(8, 20),
        )
        return r.json().get('person') or {}
    except Exception:
        return {}


def main():
    args = sys.argv[1:]
    full_dump = '--full' in args
    args = [a for a in args if a != '--full']
    input_csv, output_csv = args[:2]
    df = pd.read_csv(input_csv)

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    rows = []
    for i, row in df.iterrows():
        p = enrich(session, row['apollo_id'])
        flat = flatten_person(p)
        flat['search_company'] = row.get('Company')
        flat['search_domain'] = row.get('Domain')
        email = flat.get('email', '') or ''
        if email:
            _, note = domain_match_check(email, row.get('Domain'))
            flat['email_domain_confidence'] = note
        else:
            flat['email_domain_confidence'] = 'No email found'
        rows.append(flat)
        print(f"{i+1}/{len(df)} {flat.get('name', row['apollo_id'])} -> "
              f"email: {'yes' if email else 'no'} | linkedin: {'yes' if flat.get('linkedin_url') else 'no'}", flush=True)
        time.sleep(0.3)

    out = pd.DataFrame(rows)

    if 'organization_technology_names' in out.columns:
        out['technologies'] = out['organization_technology_names'].apply(truncate_technologies)

    if not full_dump:
        keep = [c for c in CORE_COLUMNS if c in out.columns]
        missing = [c for c in CORE_COLUMNS if c not in out.columns]
        out = out[keep]
        if missing:
            print(f"\nNote: Apollo didn't return these expected columns on this pull: {', '.join(missing)}")

    # Apollo's org tech-stack fields can carry a single cell past 200,000
    # characters (confirmed on a real pull) - well past Excel's 32,767-char
    # cell limit and Google Sheets' 50,000, which makes the file fail to
    # open cleanly. Split anything that risks that into a companion file
    # instead of silently shipping a spreadsheet-breaking main file.
    CELL_LIMIT = 30000
    oversized_cols = [c for c in out.columns if out[c].astype(str).str.len().max() > CELL_LIMIT]
    if oversized_cols:
        id_cols = [c for c in ['id', 'name', 'organization_id', 'organization_name'] if c in out.columns]
        side_path = output_csv.rsplit('.', 1)[0] + '_extended_fields.csv'
        out[id_cols + oversized_cols].to_csv(side_path, index=False)
        out = out.drop(columns=oversized_cols)
        print(f"\nMoved {len(oversized_cols)} oversized column(s) to {side_path} "
              f"(spreadsheet cell-length limits): {', '.join(oversized_cols)}")

    out.to_csv(output_csv, index=False)

    has_email = out['email'].notna().sum() if 'email' in out.columns else 0
    has_linkedin = out['linkedin_url'].notna().sum() if 'linkedin_url' in out.columns else 0
    print(f"\n{len(rows)} contacts enriched, {len(out.columns)} columns captured in the main file. "
          f"{has_email} have an email, {has_linkedin} have a LinkedIn URL.")


if __name__ == '__main__':
    main()
