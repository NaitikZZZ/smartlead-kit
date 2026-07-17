"""
Disprz ABM campaign (HubSpot Project 0-970 / 809013892828) - Lusha-only
prospecting + enrichment for the 20 exclusion-cleared target accounts.

For each company: search Lusha prospecting for CHRO-type titles (primary)
plus the sheet's listed secondary persona (e.g. Head L&D, HR Director), take
up to 2 distinct contacts, then reveal email + phone for all selected
contacts in one batched enrich call.

Usage:
    python3 lusha_prospect_disprz.py <input_csv> <output_csv>
Input CSV must have: Company, Domain, Industry, Region, Primary Use Case,
Target Personas, Priority, Xoxoday Opportunity columns.
"""
import os
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
LUSHA_KEY = os.environ.get('LUSHA_API_KEY')

CHRO_TITLES = ['CHRO', 'Chief Human Resources Officer', 'Chief HR Officer', 'Chief People Officer']

# Broader HR/Rewards-adjacent titles, always searched alongside CHRO for every
# company in this campaign (added per user request to widen the net beyond
# just the top HR seat, since Xoxoday's Rewards/Recognition/Engagement pitch
# maps directly to these roles).
ADDITIONAL_TITLES = [
    'VP of HR', 'Director of HR', 'Head of Employee Experience', 'Head of Employee Engagement',
    'Head of Rewards', 'Head of Recognition', 'Head of Total Rewards', 'Head of Compensation',
    'Head of Benefits', 'Director People Operations', 'Manager People Operations',
    'HR Business Partner', 'Head of Culture', 'Head of Engagement', 'Head of Talent Management',
]

PERSONA_SYNONYMS = {
    'head l&d': ['Head of L&D', 'Head of Learning and Development', 'Head of Learning & Development'],
    'hr director': ['HR Director', 'Director of Human Resources'],
    'learning leader': ['Learning Leader', 'Head of Learning', 'Chief Learning Officer', 'VP Learning and Development'],
    'hr leader': ['HR Leader', 'Head of HR', 'VP Human Resources', 'VP HR'],
}


def title_filters_for(personas_str):
    titles = set(CHRO_TITLES) | set(ADDITIONAL_TITLES)
    for p in str(personas_str).split(';'):
        p = p.strip().lower()
        if p and p != 'chro':
            titles.update(PERSONA_SYNONYMS.get(p, [p]))
    return sorted(titles)


def search_company(session, domain, personas):
    body = {
        'pagination': {'page': 0, 'size': 10},
        'filters': {
            'contacts': {'include': {'jobTitles': title_filters_for(personas)}},
            'companies': {'include': {'domains': [domain]}},
        },
    }
    r = session.post('https://api.lusha.com/v3/contacts/prospecting',
                      headers={'Content-Type': 'application/json', 'api_key': LUSHA_KEY},
                      json=body, timeout=20)
    d = r.json()
    if r.status_code != 200:
        return [], d.get('message', str(d))
    return d.get('results', []), None


def pick_contacts(results, max_n=4):
    def is_chro(res):
        title = (res.get('jobTitle') or {}).get('title', '').lower()
        return 'chro' in title or 'chief human resources' in title or 'chief people officer' in title or 'chief hr officer' in title
    ranked = sorted(results, key=lambda r: not is_chro(r))
    return ranked[:max_n]


def normalize_name(name):
    if not name:
        return ''
    return str(name).strip().split()[0] if ' ' in str(name).strip() else str(name).strip()


def main():
    input_csv, output_csv = sys.argv[1:3]
    df = pd.read_csv(input_csv)

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    all_rows = []
    contact_id_to_row = {}
    search_credits = 0

    for i, row in df.iterrows():
        company, domain, personas = row['Company'], row['Domain'], row['Target Personas']
        results, err = search_company(session, domain, personas)
        if err:
            print(f"{i+1}/{len(df)} {company} -> SEARCH ERROR: {err}", flush=True)
            all_rows.append({**row.to_dict(), 'lusha_note': f'Search error: {err}'})
            time.sleep(0.3)
            continue

        picked = pick_contacts(results)
        if not picked:
            print(f"{i+1}/{len(df)} {company} -> no contacts found", flush=True)
            all_rows.append({**row.to_dict(), 'lusha_note': 'No CHRO/HR-head contact found in Lusha'})
            time.sleep(0.3)
            continue

        for c in picked:
            base = {
                **row.to_dict(),
                'first_name': normalize_name(c.get('firstName')),
                'last_name': (c.get('lastName') or '').strip(),
                'job_title': (c.get('jobTitle') or {}).get('title', ''),
                'seniority': (c.get('jobTitle') or {}).get('seniority', ''),
                'linkedin_url': (c.get('socialLinks') or {}).get('linkedin', ''),
                'lusha_contact_id': c.get('id'),
                'company_domain': (c.get('company') or {}).get('domain', domain),
                'lusha_note': 'Found - pending enrich',
            }
            contact_id_to_row[c.get('id')] = len(all_rows)
            all_rows.append(base)
        search_credits += 1
        print(f"{i+1}/{len(df)} {company} -> {len(picked)} contact(s): "
              f"{', '.join((c.get('firstName') or '') + ' ' + (c.get('lastName') or '') for c in picked)}", flush=True)
        time.sleep(0.3)

    ids = list(contact_id_to_row.keys())
    enrich_credits = 0
    if ids:
        for batch_start in range(0, len(ids), 100):
            batch = ids[batch_start:batch_start + 100]
            r = session.post('https://api.lusha.com/v3/contacts/enrich',
                              headers={'Content-Type': 'application/json', 'api_key': LUSHA_KEY},
                              json={'ids': batch, 'reveal': ['emails', 'phones']}, timeout=30)
            d = r.json()
            enrich_credits += d.get('billing', {}).get('creditsCharged', 0)
            for res in d.get('results', []):
                cid = res.get('id')
                row_idx = contact_id_to_row.get(cid)
                if row_idx is None:
                    continue
                emails = res.get('emails') or []
                phones = res.get('phones') or []
                all_rows[row_idx]['email'] = emails[0].get('email') if emails else ''
                all_rows[row_idx]['phone'] = phones[0].get('number') if phones else ''
                all_rows[row_idx]['lusha_note'] = 'OK' if emails or phones else 'Found but reveal returned nothing'

    out = pd.DataFrame(all_rows)
    out['full_name'] = (out.get('first_name', '').fillna('') + ' ' + out.get('last_name', '').fillna('')).str.strip()
    out.to_csv(output_csv, index=False)

    found = sum(1 for r in all_rows if r.get('lusha_note') == 'OK')
    print(f"\n{len(df)} companies processed -> {len(ids)} contacts identified, {found} enriched with email/phone.")
    print(f"Lusha credits: {search_credits} (search) + {enrich_credits} (enrich) = {search_credits + enrich_credits} total")


if __name__ == '__main__':
    main()
