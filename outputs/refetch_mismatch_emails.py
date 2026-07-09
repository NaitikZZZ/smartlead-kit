import os, time, requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
key = os.environ.get('APOLLO_API_KEY')

df = pd.read_csv('outputs/indonesia_full_merged.csv')
to_fix = df[df['note'].astype(str).str.contains('NEEDS EMAIL REFETCH', na=False)]
acquire_mask = (df['Company'] == 'Acquire BPO') & (df['note'].astype(str).str.startswith('MISMATCH', na=False))
to_fix = pd.concat([to_fix, df[acquire_mask]])
print(f"Re-fetching {len(to_fix)} rows")

session = requests.Session()
session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

for idx, row in to_fix.iterrows():
    for attempt in range(3):
        try:
            r = session.post('https://api.apollo.io/api/v1/people/match',
                headers={'Content-Type':'application/json','Cache-Control':'no-cache','x-api-key':key},
                json={'id': row['apollo_id']}, timeout=(8, 20))
            p = r.json().get('person') or {}
            email = p.get('email', '')
            if email:
                df.at[idx, 'email'] = email
                df.at[idx, 'email_status'] = p.get('email_status', '')
                if idx in acquire_mask[acquire_mask].index:
                    df.at[idx, 'note'] = 'OK (domain resolution corrected: acquirebpo.com)'
                print(f"{row['Company']} -> {email}")
            break
        except Exception:
            time.sleep(1)
    time.sleep(0.2)

df.to_csv('outputs/indonesia_full_merged.csv', index=False)
print("DONE")
