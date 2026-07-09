import pandas as pd
import requests
import time
import os
import sys

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

API_KEY = os.environ.get("APOLLO_API_KEY", "")
BASE = "https://api.apollo.io/v1"
HEADERS = {"Content-Type": "application/json", "Cache-Control": "no-cache"}

df = pd.read_csv("apollo_all_enriched_clean.csv")
print(f"Loaded {len(df)} enriched leads for phone enrichment")
print(f"Cost: ~{len(df)} direct dial credits (you have 180K)")
print()

# Use people/bulk_match with reveal_phone_number
BATCH_SIZE = 10
results = []
no_phone = []
phone_count = 0

total_batches = (len(df) + BATCH_SIZE - 1) // BATCH_SIZE

for start in range(0, len(df), BATCH_SIZE):
    batch = df.iloc[start:start+BATCH_SIZE]
    batch_num = start // BATCH_SIZE + 1

    details = []
    for _, row in batch.iterrows():
        email = str(row.get("email_original", row.get("current_email", ""))).strip()
        apollo_id = str(row.get("apollo_id", ""))
        if apollo_id and apollo_id != "" and apollo_id != "nan":
            details.append({"id": apollo_id})
        elif email:
            details.append({"email": email})
        else:
            details.append({"email": "skip@skip.com"})

    retries = 0
    while retries < 3:
        try:
            resp = requests.post(
                f"{BASE}/people/bulk_match",
                headers=HEADERS,
                json={
                    "api_key": API_KEY,
                    "details": details,
                    "reveal_phone_number": True,
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
                print(f"  Batch {batch_num}: HTTP {resp.status_code} - {resp.text[:80]}")
                break

            data = resp.json()
            matches = data.get("matches", [])

            for idx, match in enumerate(matches):
                row_data = batch.iloc[idx] if idx < len(batch) else None
                orig_email = str(row_data["email_original"]).strip() if row_data is not None else ""

                if match is None:
                    no_phone.append(orig_email)
                    results.append({"email_original": orig_email, "phone_direct": "", "phone_mobile": "", "phone_work": ""})
                    continue

                phones = match.get("phone_numbers", [])
                phone_direct = ""
                phone_mobile = ""
                phone_work = ""

                for p in phones:
                    sn = p.get("sanitized_number", "") or ""
                    ptype = p.get("type", "")
                    if not sn:
                        continue
                    if ptype == "mobile" and not phone_mobile:
                        phone_mobile = sn
                    elif ptype in ("work_direct", "direct") and not phone_direct:
                        phone_direct = sn
                    elif ptype in ("work_hq", "other") and not phone_work:
                        phone_work = sn
                    elif not phone_direct:
                        phone_direct = sn

                best_phone = phone_mobile or phone_direct or phone_work
                if best_phone:
                    phone_count += 1
                else:
                    no_phone.append(orig_email)

                results.append({
                    "email_original": orig_email,
                    "phone_direct": phone_direct,
                    "phone_mobile": phone_mobile,
                    "phone_work": phone_work,
                    "best_phone": best_phone
                })

            break

        except Exception as e:
            retries += 1
            print(f"  Batch {batch_num}: Error - {e}, retry {retries}/3")
            time.sleep(10)

    if batch_num % 10 == 0:
        print(f"  [{start + len(batch)}/{len(df)}] Phones found: {phone_count} | No phone: {len(no_phone)}")

    time.sleep(2)

print()
print(f"=== PHONE ENRICHMENT DONE ===")
print(f"Phones found: {phone_count}/{len(df)} ({phone_count/len(df)*100:.1f}%)")
print(f"No phone: {len(no_phone)}/{len(df)}")

df_phones = pd.DataFrame(results)
df_phones.to_csv("apollo_phones.csv", index=False)
print(f"Saved apollo_phones.csv ({len(df_phones)} rows)")

# Merge phones back into enriched data
df_merged = df.merge(df_phones[["email_original", "best_phone", "phone_direct", "phone_mobile", "phone_work"]], on="email_original", how="left")
df_merged.to_csv("apollo_all_enriched_with_phones.csv", index=False)
print(f"Saved apollo_all_enriched_with_phones.csv ({len(df_merged)} rows)")

has_phone = (df_merged["best_phone"].notna() & (df_merged["best_phone"] != "") & (df_merged["best_phone"] != "None")).sum()
print(f"Final phone coverage: {has_phone}/{len(df_merged)} ({has_phone/len(df_merged)*100:.1f}%)")
