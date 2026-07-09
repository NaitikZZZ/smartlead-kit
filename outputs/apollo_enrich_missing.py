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

# Load the not-found leads
df_missing = pd.read_csv("apollo_not_found.csv")
# Load the original data for company/title context
df_all = pd.read_csv("all_945_emails_for_apollo.csv")

# Merge to get company + job_title for better matching
df_missing = df_missing.merge(df_all[["email", "company", "deal_name", "job_title"]], on="email", how="left")

print(f"Enriching {len(df_missing)} leads NOT found in Apollo bulk match")
print(f"This will consume ~{len(df_missing)} lead credits (you have 182K+)")
print(f"Rate: 1 batch/2sec, 10 per batch = {(len(df_missing)+9)//10} batches")
print()

results = []
still_missing = []
found_count = 0
BATCH_SIZE = 10

for start in range(0, len(df_missing), BATCH_SIZE):
    batch = df_missing.iloc[start:start+BATCH_SIZE]
    batch_num = start // BATCH_SIZE + 1

    details = []
    for _, row in batch.iterrows():
        email = str(row["email"]).strip()
        company = str(row.get("company", ""))
        # Extract domain from email for better matching
        domain = email.split("@")[-1] if "@" in email else ""
        entry = {"email": email}
        if domain and domain not in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com"]:
            entry["domain"] = domain
        if company and company != "nan":
            entry["organization_name"] = company
        details.append(entry)

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
                wait = 120 * retries
                print(f"  Batch {batch_num}: Rate limited, sleeping {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                print(f"  Batch {batch_num}: HTTP {resp.status_code}")
                for _, row in batch.iterrows():
                    still_missing.append({"email": str(row["email"]).strip(), "segment": row["segment"], "source": f"http_{resp.status_code}"})
                break

            data = resp.json()
            matches = data.get("matches", [])

            for idx, match in enumerate(matches):
                row = batch.iloc[idx] if idx < len(batch) else None
                email = str(row["email"]).strip() if row is not None else ""
                segment = row["segment"] if row is not None else ""

                if match is None:
                    still_missing.append({"email": email, "segment": segment, "source": "not_in_apollo_enriched"})
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
                    "current_email": match.get("email", ""),
                    "email_status": match.get("email_true_status", ""),
                    "phone": phone,
                    "city": match.get("city", ""),
                    "state": match.get("state", ""),
                    "country": match.get("country", ""),
                    "job_changed": "YES" if job_change else "NO",
                    "new_company": job_change.get("new_organization_name", "") if job_change else "",
                    "new_title": job_change.get("title", "") if job_change else "",
                    "old_company": job_change.get("old_organization_name", "") if job_change else "",
                    "source": "apollo_enrichment"
                })
                found_count += 1

            break

        except Exception as e:
            retries += 1
            print(f"  Batch {batch_num}: Error - {e}, retry {retries}/3")
            time.sleep(10)

    if batch_num % 5 == 0:
        print(f"  [{start + len(batch)}/{len(df_missing)}] Enriched: {found_count} | Still missing: {len(still_missing)}")

    time.sleep(2)

# Save enrichment results
print()
print(f"=== ENRICHMENT DONE ===")
print(f"Newly enriched: {found_count}")
print(f"Still missing (no Apollo match): {len(still_missing)}")

df_enriched = pd.DataFrame(results)
df_enriched.to_csv("apollo_enriched_new.csv", index=False)
print(f"Saved apollo_enriched_new.csv ({len(df_enriched)} rows)")

df_still = pd.DataFrame(still_missing)
df_still.to_csv("apollo_still_missing.csv", index=False)
print(f"Saved apollo_still_missing.csv ({len(df_still)} rows)")

# Now merge with the original found data for a complete picture
df_found_orig = pd.read_csv("apollo_found.csv")
print(f"\nOriginal found: {len(df_found_orig)}")
print(f"Newly enriched: {len(df_enriched)}")

if len(df_enriched) > 0:
    df_combined = pd.concat([df_found_orig, df_enriched], ignore_index=True)
else:
    df_combined = df_found_orig

df_combined.to_csv("apollo_all_enriched.csv", index=False)
print(f"Combined total: {len(df_combined)} (saved apollo_all_enriched.csv)")

# Final stats
print()
print(f"=== FINAL ENRICHMENT SUMMARY ===")
print(f"Total leads: 945")
print(f"Apollo data available: {len(df_combined)} ({len(df_combined)/945*100:.1f}%)")
print(f"No Apollo data: {len(df_still)} ({len(df_still)/945*100:.1f}%)")
print()
if len(df_combined) > 0:
    has_li = (df_combined["linkedin_url"].notna() & (df_combined["linkedin_url"] != "") & (df_combined["linkedin_url"] != "None")).sum()
    has_phone = (df_combined["phone"].notna() & (df_combined["phone"] != "") & (df_combined["phone"] != "None")).sum()
    has_name = (df_combined["first_name"].notna() & (df_combined["first_name"] != "") & (df_combined["first_name"] != "None")).sum()
    print(f"Has LinkedIn URL: {has_li}/{len(df_combined)} ({has_li/len(df_combined)*100:.1f}%)")
    print(f"Has phone: {has_phone}/{len(df_combined)} ({has_phone/len(df_combined)*100:.1f}%)")
    print(f"Has first name: {has_name}/{len(df_combined)} ({has_name/len(df_combined)*100:.1f}%)")
    print()
    print("By segment:")
    print(df_combined["segment"].value_counts().to_string())

if len(df_still) > 0:
    print()
    print("Still missing by segment:")
    print(df_still["segment"].value_counts().to_string())
