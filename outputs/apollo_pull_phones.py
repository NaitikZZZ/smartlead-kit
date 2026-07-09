import pandas as pd
import requests
import time
import os
import sys
import json

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

API_KEY = os.environ.get("APOLLO_API_KEY", "")
BASE = "https://api.apollo.io/v1"

df = pd.read_csv("apollo_all_enriched_clean.csv")
print(f"Pulling phones for {len(df)} enriched leads via contacts/search")
print(f"Rate: 8 req/min (safe under 600/hr limit)")
print()

results = []
phone_found = 0
RATE = 7.5  # seconds between requests = ~8/min

for i, row in df.iterrows():
    email = str(row["email_original"]).strip()

    try:
        resp = requests.post(
            f"{BASE}/contacts/search",
            json={"api_key": API_KEY, "q_keywords": email, "per_page": 1},
            timeout=15
        )

        if resp.status_code == 429:
            print(f"  [{i+1}] Rate limited! Saving partial, sleeping 300s...")
            pd.DataFrame(results).to_csv("apollo_phones_partial.csv", index=False)
            time.sleep(300)
            resp = requests.post(
                f"{BASE}/contacts/search",
                json={"api_key": API_KEY, "q_keywords": email, "per_page": 1},
                timeout=15
            )

        if resp.status_code != 200:
            results.append({"email_original": email, "best_phone": "", "phone_type": "", "all_phones": ""})
            continue

        data = resp.json()
        contacts = data.get("contacts", [])

        if not contacts:
            results.append({"email_original": email, "best_phone": "", "phone_type": "", "all_phones": ""})
            continue

        c = contacts[0]
        # Verify email match
        contact_emails = [ce.get("email", "").lower() for ce in c.get("contact_emails", [])]
        if email.lower() not in contact_emails and c.get("email", "").lower() != email.lower():
            results.append({"email_original": email, "best_phone": "", "phone_type": "", "all_phones": ""})
            continue

        phones = c.get("phone_numbers", [])
        sanitized = c.get("sanitized_phone", "")

        best_phone = ""
        phone_type = ""
        all_phones_list = []

        for p in phones:
            sn = p.get("sanitized_number", "") or ""
            pt = p.get("type", "")
            if sn:
                all_phones_list.append(f"{sn}({pt})")
                if pt == "mobile" and not best_phone:
                    best_phone = sn
                    phone_type = "mobile"
                elif pt in ("work_direct", "direct") and not best_phone:
                    best_phone = sn
                    phone_type = pt
                elif not best_phone:
                    best_phone = sn
                    phone_type = pt

        if not best_phone and sanitized:
            best_phone = sanitized
            phone_type = "sanitized_default"

        if best_phone:
            phone_found += 1

        results.append({
            "email_original": email,
            "best_phone": best_phone,
            "phone_type": phone_type,
            "all_phones": "; ".join(all_phones_list)
        })

    except Exception as e:
        print(f"  [{i+1}] Error: {e}")
        results.append({"email_original": email, "best_phone": "", "phone_type": "", "all_phones": ""})

    if (i+1) % 50 == 0:
        print(f"  [{i+1}/{len(df)}] Phones found: {phone_found}")
        pd.DataFrame(results).to_csv("apollo_phones_partial.csv", index=False)

    time.sleep(RATE)

print()
print(f"=== PHONE PULL DONE ===")
print(f"Phones found: {phone_found}/{len(df)} ({phone_found/len(df)*100:.1f}%)")

df_phones = pd.DataFrame(results)
df_phones.to_csv("apollo_phones_final.csv", index=False)
print(f"Saved apollo_phones_final.csv")

# Merge into enriched data
df_merged = df.merge(df_phones[["email_original", "best_phone", "phone_type", "all_phones"]], on="email_original", how="left")
df_merged.to_csv("apollo_enriched_with_phones.csv", index=False)
print(f"Saved apollo_enriched_with_phones.csv ({len(df_merged)} rows)")

# Cleanup
if os.path.exists("apollo_phones_partial.csv"):
    os.remove("apollo_phones_partial.csv")
