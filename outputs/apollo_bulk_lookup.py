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
print(f"Loaded {len(df)} leads")

results = []
not_found = []
found_count = 0
BATCH_SIZE = 10

# Resume support
resume_file = "apollo_bulk_found.csv"
resume_nf_file = "apollo_bulk_not_found.csv"
START_FROM = 0
if os.path.exists(resume_file):
    df_prev = pd.read_csv(resume_file)
    results = df_prev.to_dict("records")
    found_count = len(results)
    if os.path.exists(resume_nf_file):
        df_prev_nf = pd.read_csv(resume_nf_file)
        not_found = df_prev_nf.to_dict("records")
    START_FROM = found_count + len(not_found)
    print(f"Resuming from lead #{START_FROM}")

total_batches = (len(df) - START_FROM + BATCH_SIZE - 1) // BATCH_SIZE
print(f"Processing {len(df) - START_FROM} leads in {total_batches} batches of {BATCH_SIZE}")
print(f"Rate: 1 batch/2sec. ETA: ~{total_batches * 2 // 60} min")
print()

batch_num = 0
for start in range(START_FROM, len(df), BATCH_SIZE):
    batch = df.iloc[start:start+BATCH_SIZE]
    batch_num += 1

    details = []
    for _, row in batch.iterrows():
        email = str(row["email"]).strip()
        company = str(row.get("company", ""))
        details.append({"email": email})

    retries = 0
    while retries < 3:
        try:
            resp = requests.post(
                f"{BASE}/people/bulk_match",
                headers=HEADERS,
                json={
                    "api_key": API_KEY,
                    "details": details,
                    "reveal_personal_emails": False
                },
                timeout=30
            )

            if resp.status_code == 429:
                retries += 1
                wait = 60 * retries
                print(f"  Batch {batch_num}: Rate limited, sleeping {wait}s (retry {retries}/3)...")
                pd.DataFrame(results).to_csv(resume_file, index=False)
                pd.DataFrame(not_found).to_csv(resume_nf_file, index=False)
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                print(f"  Batch {batch_num}: HTTP {resp.status_code} - {resp.text[:100]}")
                for _, row in batch.iterrows():
                    not_found.append({"email": str(row["email"]).strip(), "segment": row["segment"], "source": f"http_{resp.status_code}"})
                break

            data = resp.json()
            matches = data.get("matches", [])

            for idx, match in enumerate(matches):
                row = batch.iloc[idx] if idx < len(batch) else None
                email = str(row["email"]).strip() if row is not None else details[idx]["email"]
                segment = row["segment"] if row is not None else ""

                if match is None:
                    not_found.append({"email": email, "segment": segment, "source": "not_in_apollo"})
                    continue

                phones = match.get("phone_numbers", [])
                phone = ""
                for p in phones:
                    sn = p.get("sanitized_number", "")
                    if sn:
                        phone = sn
                        break

                linkedin = match.get("linkedin_url", "") or ""
                job_change = match.get("contact_job_change_event")
                current_email = match.get("email", "")

                results.append({
                    "email_original": email,
                    "segment": segment,
                    "apollo_id": match.get("id", ""),
                    "first_name": match.get("first_name", ""),
                    "last_name": match.get("last_name", ""),
                    "title": match.get("title", ""),
                    "headline": match.get("headline", ""),
                    "linkedin_url": linkedin,
                    "organization_name": match.get("organization_name", ""),
                    "current_email": current_email,
                    "email_status": match.get("email_true_status", ""),
                    "phone": phone,
                    "city": match.get("city", ""),
                    "state": match.get("state", ""),
                    "country": match.get("country", ""),
                    "job_changed": "YES" if job_change else "NO",
                    "new_company": job_change.get("new_organization_name", "") if job_change else "",
                    "new_title": job_change.get("title", "") if job_change else "",
                    "old_company": job_change.get("old_organization_name", "") if job_change else "",
                    "source": "apollo_bulk_match"
                })
                found_count += 1

            break  # success, exit retry loop

        except Exception as e:
            retries += 1
            print(f"  Batch {batch_num}: Error - {e}, retry {retries}/3")
            time.sleep(10)

    if batch_num % 10 == 0:
        print(f"  [{start + len(batch)}/{len(df)}] Found: {found_count} | Not found: {len(not_found)}")
        pd.DataFrame(results).to_csv(resume_file, index=False)
        pd.DataFrame(not_found).to_csv(resume_nf_file, index=False)

    time.sleep(2)  # 1 batch per 2 sec

# Final save
print()
print(f"=== DONE ===")
print(f"Found in Apollo: {found_count}")
print(f"Not found: {len(not_found)}")

df_found = pd.DataFrame(results)
df_found.to_csv("apollo_found.csv", index=False)
print(f"Saved apollo_found.csv ({len(df_found)} rows)")

df_missing = pd.DataFrame(not_found)
df_missing.to_csv("apollo_not_found.csv", index=False)
print(f"Saved apollo_not_found.csv ({len(df_missing)} rows)")

# Cleanup partial files
for f in [resume_file, resume_nf_file]:
    if os.path.exists(f):
        os.remove(f)

if len(df_found) > 0:
    print()
    print("=== FOUND BY SEGMENT ===")
    print(df_found["segment"].value_counts().to_string())
    print()
    print("=== DATA COMPLETENESS ===")
    has_li = (df_found["linkedin_url"].notna() & (df_found["linkedin_url"] != "") & (df_found["linkedin_url"] != "None")).sum()
    has_phone = (df_found["phone"].notna() & (df_found["phone"] != "") & (df_found["phone"] != "None")).sum()
    has_name = (df_found["first_name"].notna() & (df_found["first_name"] != "") & (df_found["first_name"] != "None")).sum()
    verified = (df_found["email_status"] == "Verified").sum()
    job_changed = (df_found["job_changed"] == "YES").sum()
    print(f"Has LinkedIn URL: {has_li}/{len(df_found)} ({has_li/len(df_found)*100:.1f}%)")
    print(f"Has phone: {has_phone}/{len(df_found)} ({has_phone/len(df_found)*100:.1f}%)")
    print(f"Has first name: {has_name}/{len(df_found)} ({has_name/len(df_found)*100:.1f}%)")
    print(f"Email verified: {verified}/{len(df_found)} ({verified/len(df_found)*100:.1f}%)")
    print(f"Job changed: {job_changed}/{len(df_found)} ({job_changed/len(df_found)*100:.1f}%)")

if len(df_missing) > 0:
    print()
    print("=== NOT FOUND BY SEGMENT ===")
    print(df_missing["segment"].value_counts().to_string())
