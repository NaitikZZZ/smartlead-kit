"""
Second waterfall step for contacts Apollo couldn't find an email for.
Lusha search-and-enrich (email only, not phone, to control cost) -> any hit
gets independently validated via ZeroBounce before acceptance, and run
through the same domain-match safety check used for Apollo (reused from
enrich_contacts_apollo.py) so a Lusha-side wrong-company email doesn't slip
through either.

Cost: Lusha charges per revealed datapoint (confirmed ~1 credit for an email
find; 0 credits on NOT_FOUND). ZeroBounce validation is a separate per-check
cost on top of any Lusha credits spent.

Usage:
    python3 lusha_waterfall_enrich.py <input_csv> <output_csv>
Input CSV must have: first_name, last_name, Domain, Company columns.
"""
import os
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from enrich_contacts_apollo import domain_match_check

load_dotenv()
LUSHA_KEY = os.environ.get('LUSHA_API_KEY')
ZEROBOUNCE_KEY = os.environ.get('ZEROBOUNCE_API_KEY')


def lusha_lookup(session, first, last, domain):
    try:
        r = session.post(
            'https://api.lusha.com/v3/contacts/search-and-enrich',
            headers={'Content-Type': 'application/json', 'api_key': LUSHA_KEY},
            json={'contacts': [{'firstName': first, 'lastName': last, 'companyDomain': domain}], 'reveal': ['emails']},
            timeout=(8, 20),
        )
        d = r.json()
        result = (d.get('results') or [{}])[0]
        credits = d.get('billing', {}).get('creditsCharged', 0)
        if result.get('error'):
            return None, credits
        emails = result.get('emails') or []
        return (emails[0].get('email') if emails else None), credits
    except Exception:
        return None, 0


def zerobounce_validate(session, email):
    try:
        r = session.get('https://api.zerobounce.net/v2/validate', params={'api_key': ZEROBOUNCE_KEY, 'email': email}, timeout=15)
        return r.json().get('status', 'unknown')
    except Exception:
        return 'unknown'


def main():
    input_csv, output_csv = sys.argv[1:3]
    df = pd.read_csv(input_csv)

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    results = []
    lusha_credits_total = 0
    for i, row in df.iterrows():
        first, last, domain = row.get('first_name'), row.get('last_name'), row.get('Domain')
        if pd.isna(last) or not str(last).strip() or 'Not available' in str(last):
            results.append({'lusha_email': '', 'zerobounce_status': '', 'lusha_note': 'Skipped - no usable last name'})
            print(f"{i+1}/{len(df)} SKIP {row.get('Company')} (no usable name)", flush=True)
            continue

        email, credits = lusha_lookup(session, first, last, domain)
        lusha_credits_total += credits
        if not email:
            results.append({'lusha_email': '', 'zerobounce_status': '', 'lusha_note': 'Not found in Lusha'})
            print(f"{i+1}/{len(df)} {first} {last} -> not found in Lusha", flush=True)
            time.sleep(0.3)
            continue

        accepted, domain_note = domain_match_check(email, domain)
        if not accepted:
            results.append({'lusha_email': '', 'zerobounce_status': '', 'lusha_note': f'Lusha found {email} but {domain_note}'})
            print(f"{i+1}/{len(df)} {first} {last} -> found but {domain_note}", flush=True)
            time.sleep(0.3)
            continue

        zb_status = zerobounce_validate(session, email)
        if zb_status == 'valid':
            results.append({'lusha_email': email, 'zerobounce_status': zb_status, 'lusha_note': 'OK'})
            print(f"{i+1}/{len(df)} {first} {last} -> {email} (ZeroBounce: {zb_status})", flush=True)
        else:
            results.append({'lusha_email': '', 'zerobounce_status': zb_status, 'lusha_note': f'Lusha found {email} but ZeroBounce says {zb_status}'})
            print(f"{i+1}/{len(df)} {first} {last} -> found but ZeroBounce rejected ({zb_status})", flush=True)
        time.sleep(0.3)

    out = pd.concat([df.reset_index(drop=True), pd.DataFrame(results)], axis=1)
    out.to_csv(output_csv, index=False)

    ok = sum(1 for r in results if r['lusha_note'] == 'OK')
    print(f"\n{len(results)} contacts: {ok} emails found via Lusha + ZeroBounce-validated. "
          f"Lusha credits used: {lusha_credits_total}")


if __name__ == '__main__':
    main()
