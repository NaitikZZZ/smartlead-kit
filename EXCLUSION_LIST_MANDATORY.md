# ⚠️ MANDATORY: HubSpot DNU Exclusion List

## Overview
Every team member, every run, must use the HubSpot "ABM EXCLSIONS - DNU" list (ID: **28280**) for contact exclusions.

**Direct Link:** https://app-na2.hubspot.com/contacts/6512810/objectLists/28280/filters

This list contains ~120k existing clients and accounts we must NOT reach out to.

---

## Why It's Mandatory

1. **Compliance:** Avoid emailing existing customers (breaks contracts, damages relationships)
2. **Data Quality:** Prevents duplicate outreach to known accounts
3. **Team Alignment:** Single source of truth - no one uses a local/old exclusion list
4. **Automatic:** Exclusion is enforced in every pipeline run - not optional

---

## Configuration

### Local Development
The exclusion list is **automatically** configured:
- **List ID:** `HUBSPOT_EXCLUSION_LIST_ID=28280` (hardcoded default in `config.py`)
- **Cache TTL:** 24 hours (refreshes daily at 2 AM)
- **Caching:** Domains are cached locally to avoid expensive API calls per run

### Production (Render)
Environment variable in render.yaml:
```yaml
envVars:
  - key: HUBSPOT_EXCLUSION_LIST_ID
    value: "28280"
```

### Manual Override (DO NOT USE)
Only set `HUBSPOT_EXCLUSION_LIST_ID` if you have explicit permission:
```bash
export HUBSPOT_EXCLUSION_LIST_ID=<different-id>  # NOT RECOMMENDED
```

---

## What Gets Excluded

Contacts are excluded if they match ANY of these fields from the DNU list:

1. **Email domain** (primary or work_email)
2. **Work email domain**
3. **First name + email domain combo**
4. **Last name + email domain combo**
5. **Full name (first + last)**
6. **Company name**
7. **Company domain**
8. **LinkedIn profile URL**

---

## Verification

### Check the Cache
```bash
ls -lh wrapper/backend/cache/exclusion_domains_28280.json
```

Expected output:
```
-rw-r--   1 user  staff  450K Jul 21 12:15 exclusion_domains_28280.json
```

### View Last Refresh
```bash
tail -5 /tmp/dnu_cache_refresh.log
```

### Manual Refresh
```bash
cd wrapper/backend
python -m app.pipeline.hubspot_exclusion
```

---

## For Team Members

✅ **You don't need to do anything** — it's automatic.

The system:
1. Loads the DNU list on first run (or from cache)
2. Checks every contact against it
3. Marks excluded contacts clearly in output
4. Blocks them from any enrichment/outreach

If you upload a CSV with existing clients:
- ✓ They'll be marked as "Excluded" 
- ✓ They won't get enrichment (saves credits)
- ✓ They won't appear in output channels (email, LinkedIn, calling)

---

## Contact Exclusion Rules

When a contact matches the DNU list:
- **Status:** "Excluded"
- **Reason:** Shows which field matched (domain, name, LinkedIn URL, etc.)
- **Downstream:** Not included in any output file or enrichment

Even if the CSV has their email/phone:
- ✗ They are still excluded (respects business rules)
- ✗ No enrichment APIs called for them
- ✗ No costs incurred

---

## Questions?

- **"Can I use a different list?"** No. Portal ID `6512810`, List ID `28280` only.
- **"What if I need to exclude someone else?"** Add them to the DNU list in HubSpot, wait for the 2 AM refresh (or manually refresh).
- **"Will this slow down my runs?"** No. The list is cached locally, lookup is <100ms.
- **"What if the list is stale?"** Cache refreshes daily. Manual refresh: `python -m app.pipeline.hubspot_exclusion`

---

## Changelog

- **2026-07-21:** Mandatory configuration documented. Hard requirement: all runs use list ID 28280.
