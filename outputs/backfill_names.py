import os, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/indonesia_full_merged.csv')
session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

names = []
for i, row in df.iterrows():
    pid = row['apollo_id']
    try:
        r = session.post('https://api.apollo.io/api/v1/people/match',
            headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
            json={'id': pid}, timeout=(5,15))
        p = r.json().get('person') or {}
        names.append({'apollo_id': pid, 'first_name': p.get('first_name',''), 'last_name': p.get('last_name','')})
    except Exception:
        names.append({'apollo_id': pid, 'first_name': '', 'last_name': ''})
    if (i+1) % 25 == 0:
        print(f"{i+1}/{len(df)}", flush=True)
    time.sleep(0.2)

pd.DataFrame(names).to_csv('outputs/indonesia_real_names.csv', index=False)
print("DONE")
