"""
One-off comparison: for a sample of contacts, check what Lusha returns for
phone number vs what Apollo already found (or didn't). Not a permanent
pipeline step - just answers "which tool is actually better for mobile
numbers on this kind of list."

Usage:
    python3 lusha_phone_compare.py <input_csv> <output_csv>
Input CSV needs: first_name, last_name, Domain, Phone Number (Apollo's, may be blank), apollo_group
"""
import os
import sys
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
LUSHA_KEY = os.environ.get('LUSHA_API_KEY')


def lusha_phone_lookup(session, first, last, domain):
    try:
        r = session.post(
            'https://api.lusha.com/v3/contacts/search-and-enrich',
            headers={'Content-Type': 'application/json', 'api_key': LUSHA_KEY},
            json={'contacts': [{'firstName': first, 'lastName': last, 'companyDomain': domain}], 'reveal': ['phones']},
            timeout=(8, 20),
        )
        d = r.json()
        result = (d.get('results') or [{}])[0]
        credits = d.get('billing', {}).get('creditsCharged', 0)
        if result.get('error'):
            return None, credits
        phones = result.get('phones') or []
        return (phones[0].get('number') if phones else None), credits
    except Exception:
        return None, 0


def main():
    input_csv, output_csv = sys.argv[1:3]
    df = pd.read_csv(input_csv, dtype={'Phone Number': str})

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    lusha_phones, total_credits = [], 0
    for i, row in df.iterrows():
        phone, credits = lusha_phone_lookup(session, row['first_name'], row['last_name'], row['Domain'])
        total_credits += credits
        lusha_phones.append(phone or '')
        print(f"{i+1}/{len(df)} [{row['apollo_group']}] {row['first_name']} {row['last_name']} "
              f"| Apollo: {row.get('Phone Number','') or '-'} | Lusha: {phone or '-'}", flush=True)
        time.sleep(0.3)

    df['Lusha Phone'] = lusha_phones
    df.to_csv(output_csv, index=False)

    found_group = df[df['apollo_group'] == 'found']
    notfound_group = df[df['apollo_group'] == 'not_found']
    agree = (found_group['Phone Number'].str.replace(r'\D', '', regex=True) ==
             found_group['Lusha Phone'].str.replace(r'\D', '', regex=True)) & (found_group['Lusha Phone'] != '')
    print(f"\n--- Where Apollo already found a number ({len(found_group)}) ---")
    print(f"Lusha agreed: {agree.sum()} | Lusha found something different: {((found_group['Lusha Phone']!='') & ~agree).sum()} | Lusha found nothing: {(found_group['Lusha Phone']=='').sum()}")
    print(f"\n--- Where Apollo found nothing ({len(notfound_group)}) ---")
    print(f"Lusha found a number anyway: {(notfound_group['Lusha Phone']!='').sum()} | Lusha also found nothing: {(notfound_group['Lusha Phone']=='').sum()}")
    print(f"\nTotal Lusha credits spent on this comparison: {total_credits}")


if __name__ == '__main__':
    main()
