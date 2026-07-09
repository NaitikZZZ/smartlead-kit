import os, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/indonesia_full_merged.csv')
missing = df[df['last_name'] == 'Not available (Apollo could not confirm)']
print(f"Retrying {len(missing)} rows with missing names", flush=True)

session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

results = {}
for i, (idx, row) in enumerate(missing.iterrows()):
    pid = row['apollo_id']
    for attempt in range(3):
        try:
            r = session.post('https://api.apollo.io/api/v1/people/match',
                headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
                json={'id': pid}, timeout=(8, 20))
            p = r.json().get('person') or {}
            fn, ln = p.get('first_name',''), p.get('last_name','')
            if fn or ln:
                results[pid] = (fn, ln)
                break
        except Exception:
            time.sleep(1)
    if (i+1) % 20 == 0:
        print(f"{i+1}/{len(missing)}", flush=True)
    time.sleep(0.2)

recovered = 0
for idx, row in missing.iterrows():
    pid = row['apollo_id']
    if pid in results:
        df.at[idx, 'first_name'], df.at[idx, 'last_name'] = results[pid]
        recovered += 1

df.to_csv('outputs/indonesia_full_merged.csv', index=False)
print(f"DONE - recovered {recovered}/{len(missing)}")
