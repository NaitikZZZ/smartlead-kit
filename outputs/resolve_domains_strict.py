import os, json, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/uk_eur_normalized.csv')
companies = df['Cleaned Company Name'].unique().tolist()

def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=0)
session.mount('https://', adapter)

results = {}
for i, name in enumerate(companies):
    query_name = name.split('/')[0].split('&')[0].strip()
    best = None
    accounts = []
    for attempt in range(2):
        try:
            r = session.post('https://api.apollo.io/api/v1/mixed_companies/search',
                headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
                json={'q_organization_name': query_name, 'page':1, 'per_page':10}, timeout=(5,10))
            data = r.json()
            accounts = data.get('accounts', []) + data.get('organizations', [])
            break
        except Exception as e:
            accounts = []
            last_err = str(e)
    qn = norm(query_name)
    for a in accounts:
        an = norm(a.get('name',''))
        if an == qn and a.get('primary_domain'):
            best = a
            break
    if best:
        results[name] = {
            'domain': best.get('primary_domain',''),
            'linkedin': best.get('linkedin_url',''),
            'matched_name': best.get('name',''),
            'source': 'Apollo-exact'
        }
    else:
        cands = [{'name':a.get('name'),'domain':a.get('primary_domain'),'linkedin':a.get('linkedin_url')} for a in accounts[:3]]
        results[name] = {'domain':'', 'linkedin':'', 'matched_name':'', 'source':'Unresolved', 'candidates': cands}
    print(f"{i+1}/{len(companies)} {name} -> {results[name]['source']}", flush=True)
    time.sleep(0.2)

resolved = sum(1 for v in results.values() if v['source']=='Apollo-exact')
print(f"Resolved via exact Apollo match: {resolved}/{len(companies)}")

with open('outputs/domain_resolution_strict.json','w') as f:
    json.dump(results, f, indent=2)
