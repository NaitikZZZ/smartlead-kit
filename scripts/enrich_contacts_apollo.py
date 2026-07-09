"""
Enrich named contacts via Apollo People Match, with a standing domain-match
safety check - not an optional/ad-hoc step.

Why the domain-match check exists:
Apollo's people/match endpoint will happily return a "verified" email for a
person even when that email belongs to a different organization than the
domain you queried with (e.g. a side gig, a previous employer, a shared
personal domain). Trusting "verified" alone let a wrong-company email through
during manual testing (querying google.com for a contact returned a verified
email at a UK livery company's member domain instead). This script always
checks the returned email's domain against the company domain you supplied
and buckets anything that disagrees into 'MISMATCH' instead of accepting it.

Note: this check has false positives too - some companies genuinely send
email from a different domain than their marketing site (e.g. product.io
vs product.com). Mismatches are for manual review, not automatic rejection
of the company/domain resolution itself.

Usage:
    python3 enrich_contacts_apollo.py <input_csv> <first_name_col> <last_name_col> <domain_col> <output_csv>

Rows with an empty/missing domain are skipped (nothing to query Apollo with)
and marked 'Skipped - no domain' rather than silently omitted.

If the input CSV has an 'apollo_id' column (e.g. from
search_company_contacts_apollo.py), enrichment uses that id directly instead
of fuzzy first/last name matching - more precise, since the id came straight
from Apollo's own search rather than a name we're hoping matches.
"""
import os
import csv
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
APOLLO_KEY = os.environ.get('APOLLO_API_KEY')
ALIASES_PATH = os.path.join(os.path.dirname(__file__), '..', 'reference', 'domain_aliases.csv')


def load_domain_aliases():
    """Company domains that legitimately send email from a different domain
    than their primary one - rebrands (Anthem -> Elevance Health), M&A
    (Sykes absorbed into Foundever), or a real operating domain that differs
    from the marketing site (HGS uses hgs.cx, not hgs.com). Built up from
    confirmed cases found during real runs - see reference/domain_aliases.csv.
    Bidirectional: either domain can appear as the "target" we searched for."""
    pairs = set()
    if os.path.exists(ALIASES_PATH):
        with open(ALIASES_PATH, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                pairs.add((row['primary_domain'].lower(), row['alias_domain'].lower()))
                pairs.add((row['alias_domain'].lower(), row['primary_domain'].lower()))
    return pairs


DOMAIN_ALIASES = load_domain_aliases()


def domain_root(domain):
    """Crude second-level-domain extractor that handles compound ccTLDs
    (co.uk, com.ph, com.au) well enough to catch 'deloitte.co.uk' and
    'deloitte.com' as the same root - large professional-services networks
    (Deloitte, EY, KPMG, PwC) run legally separate national member firms,
    each on their own country domain, which isn't a data error."""
    parts = domain.lower().split('.')
    if len(parts) <= 2:
        return parts[0]
    if parts[-2] in ('co', 'com', 'org', 'net', 'gov') and len(parts[-1]) == 2:
        return parts[-3] if len(parts) >= 3 else parts[0]
    return parts[-2]


def enrich(session, first, last, domain, apollo_id=None):
    payload = {'id': apollo_id, 'reveal_personal_emails': True} if apollo_id else \
        {'first_name': first, 'last_name': last, 'domain': domain, 'reveal_personal_emails': True}
    try:
        r = session.post(
            'https://api.apollo.io/api/v1/people/match',
            headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'x-api-key': APOLLO_KEY},
            json=payload,
            timeout=(5, 15),
        )
        return r.json().get('person') or {}
    except Exception:
        return {}


def domain_match_check(email, target_domain):
    """Returns (accepted_email, note). Never trusts an email whose domain
    disagrees with the company domain we queried against - unless it's a
    known alias (reference/domain_aliases.csv) or the same brand root under
    a different country TLD (deloitte.co.uk vs deloitte.com)."""
    if not email:
        return '', 'No email found'
    email_domain = email.split('@')[-1].lower()
    target = str(target_domain).lower().replace('www.', '')
    if email_domain == target or email_domain.endswith('.' + target) or target.endswith('.' + email_domain):
        return email, 'OK'
    if (email_domain, target) in DOMAIN_ALIASES:
        return email, f'OK (known alias: {email_domain} = {target})'
    if domain_root(email_domain) == domain_root(target) and len(domain_root(target)) >= 4:
        return email, f'OK (same brand, country variant: {email_domain} vs {target})'
    return '', f'MISMATCH - email domain {email_domain} != {target} (needs manual review, may be a legitimate multi-domain company)'


def main():
    input_csv, first_col, last_col, domain_col, output_csv = sys.argv[1:6]
    df = pd.read_csv(input_csv)
    has_id_col = 'apollo_id' in df.columns

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    results = []
    for i, row in df.iterrows():
        domain = row.get(domain_col)
        apollo_id = row.get('apollo_id') if has_id_col else None
        apollo_id = None if (apollo_id is None or (isinstance(apollo_id, float) and pd.isna(apollo_id))) else apollo_id
        label = row[first_col] if not pd.isna(row.get(first_col, float('nan'))) else (apollo_id or '?')
        if pd.isna(domain) or not str(domain).strip():
            results.append({'email': '', 'email_status': '', 'linkedin_apollo': '', 'apollo_title': '', 'note': 'Skipped - no domain'})
            print(f"{i+1}/{len(df)} SKIP {label} (no domain)", flush=True)
            continue

        p = enrich(session, row.get(first_col), row.get(last_col), domain, apollo_id)
        raw_email = p.get('email', '') or ''
        email, note = domain_match_check(raw_email, domain)
        results.append({
            'real_first_name': p.get('first_name', ''),
            'real_last_name': p.get('last_name', ''),
            'email': email,
            'email_status': p.get('email_status', ''),
            'linkedin_apollo': p.get('linkedin_url', ''),
            'apollo_title': p.get('title', ''),
            'note': note,
        })
        print(f"{i+1}/{len(df)} {label} -> {note}", flush=True)
        time.sleep(0.3)

    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(results)], axis=1)
    out.to_csv(output_csv, index=False)

    ok = sum(1 for r in results if r['note'] == 'OK')
    mismatch = sum(1 for r in results if r['note'].startswith('MISMATCH'))
    no_email = sum(1 for r in results if r['note'] == 'No email found')
    skipped = sum(1 for r in results if r['note'] == 'Skipped - no domain')
    print(f"\n{len(results)} contacts: {ok} OK, {mismatch} domain mismatch (manual review), "
          f"{no_email} no email found, {skipped} skipped (no domain).")


if __name__ == '__main__':
    main()
