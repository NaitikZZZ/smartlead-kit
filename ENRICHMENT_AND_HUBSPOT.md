# Enrichment & HubSpot Import Guide

---

## LinkedIn URLs: Why 0?

If your enrichment shows **0 LinkedIn URLs**, this is **expected**. Here's why:

### Apollo's API Limitations
- Apollo's `people/match` endpoint does NOT guarantee LinkedIn URL data
- LinkedIn URLs are only returned if Apollo has them in their database
- Many profiles don't have LinkedIn data captured by Apollo (especially in developing markets)
- Apollo's free/starter tiers may have limited LinkedIn coverage

### What You Can Do
1. **Accept the limitation:** LinkedIn URLs are a bonus, not core enrichment
2. **Use HeyReach separately:** The system auto-pushes LinkedIn contacts to HeyReach (if available) - even without URLs
3. **Request full Apollo profile:** Use Apollo's web UI to manually check if contacts have LinkedIn profiles (sometimes available but not returned via API)

---

## Mandatory HubSpot Columns for Import

When you upload enriched contacts to HubSpot, these fields are **required**:

### MANDATORY (Contact Creation)
| Field | HubSpot Property | Source | Notes |
|-------|-----------------|--------|-------|
| **First Name** | `firstname` | Enrichment: first_name | Cannot be blank |
| **Last Name** | `lastname` | Enrichment: last_name | Cannot be blank |
| **Email** | `email` | Enrichment: email (verified only) | Must pass email validation, only verified emails imported |

### MANDATORY (Demographics) - Per Team
| Field | HubSpot Property | Source | Notes |
|-------|-----------------|--------|-------|
| **City** | `city` | Enrichment: city | Required field, do NOT leave blank |
| **Country** | `country` | Enrichment: country | Required field, do NOT leave blank |
| **Number of Employees** | `numemployees` | Enrichment: bucketed (0-50, 51-200, etc.) | Required field, bucketed scale |

### Enriched Optional (Campaign Context)
| Field | HubSpot Property | Source | Notes |
|-------|-----------------|--------|-------|
| Job Title | `jobtitle` | Enrichment: title | Helps segment outreach |
| Phone | `phone` | Enrichment: Phone Number | Fallback from raw CSV or Apollo |
| Company | `company` | Enrichment: organization_name | Organization name |
| Company LinkedIn | `company_linkedin_url` | Enrichment: organization_linkedin_url | LinkedIn page of company |
| Industry | `industry` | Enrichment: organization_industry | Industry vertical |
| Revenue | `annualrevenue` | Enrichment: organization_annual_revenue | Company revenue |
| Funding | `total_funding` | Enrichment: organization_total_funding | Total funding raised |
| Technologies | `technologies` | Enrichment: technologies | Tech stack (truncated to 40 tools) |
| Seniority | `seniority_level` | Enrichment: seniority | C-suite, VP, Head, Director, Manager |
| Department | `department___job_function__apollo_` | Enrichment: departments | Department/function |
| LinkedIn URL | `hs_linkedin_url` | Enrichment: linkedin_url | Person's LinkedIn (if available) |
| Address | `address` | Enrichment: formatted_address | Full address |
| State | `state` | Enrichment: state | State/Province |
| Time Zone | (not mapped) | Enrichment: time_zone | Available in export, not imported |

---

## Import Workflow

### Step 1: Enrichment
The system enriches your CSV with Apollo data:
- Searches for candidates by company + domain
- Reveals email + full-field data per person
- Reveals phone (optional, costs credits)

### Step 2: Validation
Before HubSpot import, the system:
- ✓ Filters to **verified emails only** (email_status = "verified")
- ✓ Buckets employee count (0-50, 51-200, 201-500, etc.)
- ✓ Normalizes first/last names (strips credentials/suffixes)
- ✓ Validates mandatory fields (firstname, lastname, email, city, country, numemployees)
- ✗ Drops rows with missing mandatory fields

### Step 3: Import
The system creates a HubSpot static list and imports contacts:
- Creates 1 new list per run (named by campaign title)
- Maps all enriched fields to HubSpot properties
- Associates contacts with Project/Partner/Event (if chosen)
- Returns: total imported, new vs. updated, list URL, associations

---

## Troubleshooting

### "Got 0 enriched contacts"
- Check your raw CSV has companies/domains
- Verify Apollo API key is configured and has credits
- Check if all companies returned zero Apollo candidates

### "0 verified emails"
- Apollo found candidates but couldn't reveal emails
- Check Apollo's email reveal credit balance
- Try re-running (some delays on Apollo's end)

### "Import failed: missing X field"
- Check the mandatory columns above
- City, country, numemployees cannot be blank
- Re-run enrichment to fill missing fields

### "0 LinkedIn URLs"
- **This is normal** - Apollo doesn't guarantee LinkedIn data
- LinkedIn contacts are still pushed to HeyReach if available
- Use Apollo's UI to manually verify if they exist

---

## Field Mapping Reference (for debugging)

Raw CSV → Enriched CSV → HubSpot:

| Raw Input | Enrichment | HubSpot Import |
|-----------|-----------|-----------------|
| Company Name | organization_name | company |
| Domain | company_domain | (not imported, used for matching) |
| - | first_name | firstname |
| - | last_name | lastname |
| - | email | email |
| - | title | jobtitle |
| - | Phone Number | phone |
| - | linkedin_url | hs_linkedin_url |
| - | organization_industry | industry |
| - | organization_estimated_num_employees | numemployees (bucketed) |
| - | country | country |
| - | city | city |
| - | state | state |
| - | formatted_address | address |
| - | seniority | seniority_level |
| - | departments | department___job_function__apollo_ |
| - | organization_linkedin_url | company_linkedin_url |
| - | organization_annual_revenue | annualrevenue |
| - | organization_total_funding | total_funding |
| - | technologies | technologies |

---

## Questions?

- **"How do I ensure high email delivery?"** Only verified emails are imported. Verification is done via Apollo's email reveal.
- **"Can I import blank fields?"** Mandatory fields (firstname, lastname, email, city, country, numemployees) cannot be blank. Optional fields can be.
- **"Will my contacts be duplicated in HubSpot?"** HubSpot deduplicates on email. If the email exists, it's updated; otherwise, new contact created.
- **"What happens to excluded contacts?"** Excluded contacts are filtered out before import. They don't appear in any output file.
