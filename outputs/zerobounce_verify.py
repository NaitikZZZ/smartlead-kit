import pandas as pd
import requests
import time
import os
import sys

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

ZB_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "")
ZB_URL = "https://api.zerobounce.net/v2/validate"

# Load all 945 emails
df = pd.read_csv("all_945_emails_for_apollo.csv")
emails = df["email"].tolist()
print(f"ZeroBounce verification for {len(emails)} emails")
print(f"Rate: 5 req/sec")
print()

results = []
valid_count = 0
invalid_count = 0
catch_all = 0
unknown = 0

for i, email in enumerate(emails):
    email = str(email).strip()

    try:
        resp = requests.get(
            ZB_URL,
            params={"api_key": ZB_KEY, "email": email, "ip_address": ""},
            timeout=15
        )

        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            sub_status = data.get("sub_status", "")
            first_name = data.get("firstname", "")
            last_name = data.get("lastname", "")
            gender = data.get("gender", "")
            free_email = data.get("free_email", "")

            results.append({
                "email": email,
                "segment": df.iloc[i]["segment"],
                "zb_status": status,
                "zb_sub_status": sub_status,
                "zb_first_name": first_name,
                "zb_last_name": last_name,
                "zb_gender": gender,
                "zb_free_email": free_email
            })

            if status == "valid":
                valid_count += 1
            elif status == "invalid":
                invalid_count += 1
            elif status == "catch-all":
                catch_all += 1
            else:
                unknown += 1
        else:
            results.append({
                "email": email,
                "segment": df.iloc[i]["segment"],
                "zb_status": f"http_{resp.status_code}",
                "zb_sub_status": "",
                "zb_first_name": "",
                "zb_last_name": "",
                "zb_gender": "",
                "zb_free_email": ""
            })
            unknown += 1

    except Exception as e:
        print(f"  [{i+1}] Error for {email}: {e}")
        results.append({
            "email": email,
            "segment": df.iloc[i]["segment"],
            "zb_status": "error",
            "zb_sub_status": str(e)[:50],
            "zb_first_name": "",
            "zb_last_name": "",
            "zb_gender": "",
            "zb_free_email": ""
        })
        unknown += 1

    if (i+1) % 100 == 0:
        print(f"  [{i+1}/{len(emails)}] Valid: {valid_count} | Invalid: {invalid_count} | Catch-all: {catch_all} | Unknown: {unknown}")
        pd.DataFrame(results).to_csv("zerobounce_partial.csv", index=False)

    time.sleep(0.2)  # 5 req/sec

print()
print(f"=== ZEROBOUNCE DONE ===")
print(f"Valid: {valid_count} ({valid_count/len(emails)*100:.1f}%)")
print(f"Invalid: {invalid_count} ({invalid_count/len(emails)*100:.1f}%)")
print(f"Catch-all: {catch_all} ({catch_all/len(emails)*100:.1f}%)")
print(f"Unknown/other: {unknown} ({unknown/len(emails)*100:.1f}%)")

df_zb = pd.DataFrame(results)
df_zb.to_csv("zerobounce_results.csv", index=False)
print(f"Saved zerobounce_results.csv ({len(df_zb)} rows)")

print()
print("=== BY SEGMENT ===")
for seg in ["C1", "C2", "C3"]:
    seg_data = df_zb[df_zb["segment"] == seg]
    v = (seg_data["zb_status"] == "valid").sum()
    inv = (seg_data["zb_status"] == "invalid").sum()
    ca = (seg_data["zb_status"] == "catch-all").sum()
    print(f"  {seg}: {len(seg_data)} total | {v} valid | {inv} invalid | {ca} catch-all")

# Cleanup
if os.path.exists("zerobounce_partial.csv"):
    os.remove("zerobounce_partial.csv")
