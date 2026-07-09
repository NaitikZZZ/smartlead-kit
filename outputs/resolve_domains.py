import os, json, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/uk_eur_normalized.csv')
companies = df['Cleaned Company Name'].unique().tolist()

def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())

results = {}
for i, name in enumerate(companies):
    query_name = name.split('/')[0].split('&')[0].strip()
    try:
        r = requests.post('https://api.apollo.io/api/v1/mixed_companies/search',
            headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
            json={'q_organization_name': query_name, 'page':1, 'per_page':5}, timeout=15)
        data = r.json()
        accounts = data.get('accounts', []) + data.get('organizations', [])
        best = None
        for a in accounts:
            an = norm(a.get('name',''))
            qn = norm(query_name)
            if an == qn or an in qn or qn in an:
                best = a
                break
        if not best and accounts:
            best = accounts[0]
        if best:
            results[name] = {
                'domain': best.get('primary_domain',''),
                'linkedin': best.get('linkedin_url',''),
                'matched_name': best.get('name',''),
                'source': 'Apollo'
            }
        else:
            results[name] = {'domain':'', 'linkedin':'', 'matched_name':'', 'source':'Unresolved'}
    except Exception as e:
        results[name] = {'domain':'', 'linkedin':'', 'matched_name':'', 'source':f'Error: {e}'}
    time.sleep(0.3)
    print(f"{i+1}/{len(companies)} {name} -> {results[name]['domain']} ({results[name]['source']})")

with open('outputs/domain_resolution.json','w') as f:
    json.dump(results, f, indent=2)
