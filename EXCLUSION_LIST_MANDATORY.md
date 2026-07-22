# Exclusion List Policy: HubSpot DNU List (28280)

## Overview
When you choose to run the **Exclusion Check**, this system MUST use the HubSpot "ABM EXCLSIONS - DNU" list (ID: **28280**).

**Direct Link:** https://app-na2.hubspot.com/contacts/6512810/objectLists/28280/filters

This list contains ~120k existing clients and accounts to avoid outreach to.

---

## When It Applies

✅ **When you choose "Yes" to the exclusion question** → This list is mandatory (no alternatives)

❌ **When you skip exclusion** → Not used at all

---

## Why This List When Used

1. **Single Source of Truth:** When doing exclusion, everyone uses the same list
2. **Real-time Data:** Cache is refreshed live on every run (not stale)
3. **Compliance Ready:** Ensure you're not emailing existing customers
4. **Team Alignment:** No local/outdated exclusion lists

---

## Configuration

### How It Works
The exclusion list is **always live** (fetched fresh every run):
- **List ID:** `HUBSPOT_EXCLUSION_LIST_ID=28280` (hardcoded default in `config.py`)
- **Refresh:** Always rebuilt from HubSpot when exclusion is enabled
- **Speed:** First run of a session fetches ~120k contacts (~25-30 min). Cache is kept for the session.

### Local Development
```bash
# Exclusion is automatic when you choose it in the UI
# List 28280 is hardcoded and cannot be overridden
```

### Production (Render)
Environment variable in render.yaml:
```yaml
envVars:
  - key: HUBSPOT_EXCLUSION_LIST_ID
    value: "28280"
```

### Do NOT Override
Do not set `HUBSPOT_EXCLUSION_LIST_ID` to a different value:
```bash
# ❌ This will break the system
export HUBSPOT_EXCLUSION_LIST_ID=<other-id>
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

### Check if Exclusion is Working
The exclusion check runs automatically when you enable it in the UI. You'll see:
- List of excluded contacts (with reasons)
- Count of excluded vs. OK to reach out
- Direct link to the HubSpot list: https://app-na2.hubspot.com/contacts/6512810/objectLists/28280/filters

### Cache Location (for reference)
```bash
ls -lh wrapper/backend/cache/exclusion_domains_28280.json
```

The cache file is rebuilt fresh each time exclusion is used, ensuring live data.

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
- **"What if I need to exclude someone else?"** Add them to the DNU list in HubSpot. The next exclusion check will pick them up (always fresh).
- **"Will this slow down my runs?"** First exclusion check is ~25-30 min (fetching 120k contacts). Subsequent checks in the same session are faster (cached).
- **"Is the list always current?"** Yes. Every exclusion check fetches fresh data from HubSpot, so you always get live updates.

---

## Changelog

- **2026-07-21:** Mandatory configuration documented. Hard requirement: all runs use list ID 28280.
