import pandas as pd
import requests
import time
import json
import os
import sys

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

API_KEY = os.environ.get("APOLLO_API_KEY", "")
BASE = "https://api.apollo.io/v1"
HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-cache"}

df = pd.read_csv("all_945_emails_for_apollo.csv")
emails = df["email"].tolist()

results = []
not_found = []
found_count = 0

# Resume support: check if partial results exist
START_FROM = 0
resume_file = "apollo_found_partial.csv"
resume_nf_file = "apollo_not_found_partial.csv"
if os.path.exists(resume_file):
    df_prev = pd.read_csv(resume_file)
    results = df_prev.to_dict("records")
    found_count = len(results)
    if os.path.exists(resume_nf_file):
        df_prev_nf = pd.read_csv(resume_nf_file)
        not_found = df_prev_nf.to_dict("records")
    START_FROM = found_count + len(not_found)
    print(f"Resuming from #{START_FROM} (found: {found_count}, not found: {len(not_found)})")

print(f"Apollo lookup: {len(emails)} total, starting from #{START_FROM}")
print(f"Rate: 1 req/sec (slower to avoid 429s)")
print()

for i, email in enumerate(emails):
    if i < START_FROM:
        continue
    try:
        resp = requests.post(
            f"{BASE}/contacts/search",
            headers=HEADERS,
            json={
                "api_key": API_KEY,
                "q_keywords": email,
                "per_page": 1,
                "page": 1
            },
            timeout=15
        )

        if resp.status_code == 429:
            print(f"  [{i+1}] Rate limited, saving partial + sleeping 120s...")
            pd.DataFrame(results).to_csv(resume_file, index=False)
            pd.DataFrame(not_found).to_csv(resume_nf_file, index=False)
            time.sleep(120)
            resp = requests.post(
                f"{BASE}/contacts/search",
                headers=HEADERS,
                json={
                    "api_key": API_KEY,
                    "q_keywords": email,
                    "per_page": 1,
                    "page": 1
                },
                timeout=15
            )
            if resp.status_code == 429:
                print(f"  [{i+1}] Still rate limited, sleeping 180s more...")
                time.sleep(180)
                resp = requests.post(
                    f"{BASE}/contacts/search",
                    headers=HEADERS,
                    json={
                        "api_key": API_KEY,
                        "q_keywords": email,
                        "per_page": 1,
                        "page": 1
                    },
                    timeout=15
                )

        data = resp.json()
        contacts = data.get("contacts", [])

        if contacts and len(contacts) > 0:
            c = contacts[0]
            # Check if email actually matches (keyword search can be fuzzy)
            contact_emails = [ce.get("email","").lower() for ce in c.get("contact_emails", [])]
            if email.lower() in contact_emails or c.get("email","").lower() == email.lower():
                phones = c.get("phone_numbers", [])
                phone = phones[0].get("sanitized_number","") if phones else ""
                job_change = c.get("contact_job_change_event")

                results.append({
                    "email": email,
                    "segment": df.iloc[i]["segment"],
                    "apollo_id": c.get("id",""),
                    "first_name": c.get("first_name",""),
                    "last_name": c.get("last_name",""),
                    "title": c.get("title",""),
                    "headline": c.get("headline",""),
                    "linkedin_url": c.get("linkedin_url",""),
                    "organization_name": c.get("organization_name",""),
                    "email_status": c.get("email_true_status",""),
                    "phone": phone,
                    "sanitized_phone": c.get("sanitized_phone",""),
                    "city": c.get("city",""),
                    "state": c.get("state",""),
                    "country": c.get("country",""),
                    "job_changed": "YES" if job_change else "NO",
                    "new_company": job_change.get("new_organization_name","") if job_change else "",
                    "new_title": job_change.get("title","") if job_change else "",
                    "new_email": c.get("email","") if job_change and c.get("email","").lower() != email.lower() else "",
                    "source": "apollo_existing",
                    "label_ids": json.dumps(c.get("label_ids", []))
                })
                found_count += 1
            else:
                not_found.append({"email": email, "segment": df.iloc[i]["segment"], "source": "not_in_apollo"})
        else:
            not_found.append({"email": email, "segment": df.iloc[i]["segment"], "source": "not_in_apollo"})

    except Exception as e:
        print(f"  [{i+1}] Error for {email}: {e}")
        not_found.append({"email": email, "segment": df.iloc[i]["segment"], "source": "error"})

    if (i+1) % 50 == 0:
        print(f"  [{i+1}/{len(emails)}] Found: {found_count} | Not found: {len(not_found)}")

    # Save partial every 100
    if (i+1) % 100 == 0:
        pd.DataFrame(results).to_csv(resume_file, index=False)
        pd.DataFrame(not_found).to_csv(resume_nf_file, index=False)

    # Rate limit: 1 req/sec to avoid 429s
    time.sleep(1.0)

print()
print(f"=== DONE ===")
print(f"Found in Apollo: {found_count}")
print(f"Not found: {len(not_found)}")

# Save results
df_found = pd.DataFrame(results)
df_found.to_csv("apollo_found.csv", index=False)
print(f"Saved apollo_found.csv ({len(df_found)} rows)")

df_missing = pd.DataFrame(not_found)
df_missing.to_csv("apollo_not_found.csv", index=False)
print(f"Saved apollo_not_found.csv ({len(df_missing)} rows)")

# Summary by segment
if len(df_found) > 0:
    print()
    print("=== FOUND BY SEGMENT ===")
    print(df_found["segment"].value_counts().to_string())
    print()
    print("=== DATA COMPLETENESS (found leads) ===")
    print(f"Has LinkedIn URL: {(df_found['linkedin_url'].notna() & (df_found['linkedin_url'] != '')).sum()}/{len(df_found)}")
    print(f"Has phone: {(df_found['phone'].notna() & (df_found['phone'] != '')).sum()}/{len(df_found)}")
    print(f"Has first name: {(df_found['first_name'].notna() & (df_found['first_name'] != '')).sum()}/{len(df_found)}")
    print(f"Email verified: {(df_found['email_status'] == 'Verified').sum()}/{len(df_found)}")
    print(f"Job changed: {(df_found['job_changed'] == 'YES').sum()}/{len(df_found)}")

if len(df_missing) > 0:
    print()
    print("=== NOT FOUND BY SEGMENT ===")
    print(df_missing["segment"].value_counts().to_string())
