import os, json, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/uk_eur_ready.csv')

session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

def enrich(first, last, domain):
    try:
        r = session.post('https://api.apollo.io/api/v1/people/match',
            headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
            json={'first_name': first, 'last_name': last, 'domain': domain, 'reveal_personal_emails': True},
            timeout=(5, 15))
        d = r.json()
        return d.get('person') or {}
    except Exception as e:
        return {'_error': str(e)}

results = []
for i, row in df.iterrows():
    if row['Enrichment Readiness'] == 'Not Ready':
        results.append({'email':'', 'email_status':'', 'linkedin_apollo':'', 'apollo_title':'', 'note':'Skipped - Not Ready (no domain)'})
        print(f"{i+1}/{len(df)} SKIP {row['Cleaned First Name']} {row['Cleaned Last Name']}", flush=True)
        continue
    p = enrich(row['Cleaned First Name'], row['Cleaned Last Name'], row['Resolved Domain'])
    email = p.get('email', '') or ''
    email_domain = email.split('@')[-1].lower() if '@' in email else ''
    target_domain = str(row['Resolved Domain']).lower().replace('www.', '')
    domain_match = email_domain and target_domain and (email_domain == target_domain or email_domain.endswith('.' + target_domain) or target_domain.endswith('.' + email_domain))
    note = '' if not email else ('OK' if domain_match else f'MISMATCH - email domain {email_domain} != {target_domain}')
    results.append({
        'email': email if (email and domain_match) else '',
        'email_status': p.get('email_status', ''),
        'linkedin_apollo': p.get('linkedin_url', ''),
        'apollo_title': p.get('title', ''),
        'note': note if email else 'No email found'
    })
    print(f"{i+1}/{len(df)} {row['Cleaned First Name']} {row['Cleaned Last Name']} -> {results[-1]['note']}", flush=True)
    time.sleep(0.3)

out = pd.concat([df.reset_index(drop=True), pd.DataFrame(results)], axis=1)
out.to_csv('outputs/uk_eur_enriched.csv', index=False)
print("DONE")
