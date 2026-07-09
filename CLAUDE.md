# CLAUDE.md — Campaign Brain (Smartlead × Xoxoday edition)

---

> This file directs the agent through the full outbound campaign flow using AI + **Smartlead**, with **Xoxoday** as the reference product.
> Unlike the Saleshandy version of this kit, Smartlead exposes full API control, so the agent **creates the campaign, builds the sequence, and uploads prospects end-to-end via API** — no UI clicks required.
>
> **Reference product:** Xoxoday (xoxoday.com). Product suite the agent should understand:
> - **Empuls** — employee recognition + engagement (default angle; HR/People Ops buyers)
> - **Plum** — rewards/incentives/payouts API + 10M+ reward catalog across 175+ countries (Marketing/RevOps/CX buyers)
> - **Compass** — sales commission automation (Sales Ops/RevOps/Finance buyers)
> - **Loyalife** — customer loyalty programs (CX/Growth buyers at consumer brands)
>
> Before writing copy, ask the operator which product angle the campaign is for, then select the matching framework from `copy-frameworks.md`.

## Overview
You are building an automated cold email campaign. Follow these steps in order:
1. **Score & Tier Companies** → Identify and rank target companies
2. **Find ICPs** → Collect decision-makers at tiered companies (any source; Smartlead does not ship a lead finder)
3. **Enrich Contacts** → Get verified emails + personalization signals
4. **Generate Copy** → Write personalized cold email sequences (HTML, Smartlead merge tags)
5. **Auto-Deploy to Smartlead** → `create campaign → save sequence → attach inboxes → upload leads → launch` via API

---

## Critical Rules
1. Never display API keys in output or conversations. Load `SMARTLEAD_API_KEY` from `.env`.
2. Always authenticate with `?api_key=...` as a **query param** (Smartlead does not use bearer tokens).
3. Use **Smartlead merge tags in snake_case**: `{{first_name}}`, `{{last_name}}`, `{{company_name}}`, `{{email}}`. Custom variables come from the `custom_fields` object on each lead.
4. `email_body` must be **HTML** — wrap paragraphs in `<p>` / `<div>`. Plain-text will render poorly.
5. Lead uploads are capped at **400 per API request** — batch larger lists and sleep between batches.
6. Use Python for all scoring and data manipulation. Save all outputs to `outputs/` as CSV.
7. Read strategy docs BEFORE executing any step (`scoring-criteria.md`, `copy-frameworks.md`, `smartlead-api-docs.md`).

---

## Step 1: Score & Tier Companies

**Goal:** Build a tiered list of target companies (Tier 1/2/3).

**Instructions:**
1. Ask for the target niche/industry and ideal client profile
2. Use the scoring criteria in `scoring-criteria.md` to evaluate companies
3. Research companies using web search (company size, funding, tech stack, revenue)
4. Output a tiered list → `outputs/companies-scored.csv`

**Data sources:** Web search, Clay, Apollo, LinkedIn Sales Navigator, Crunchbase, Bright Data, company websites.

---

## Step 2: Find ICPs at Target Companies

**Goal:** Find decision-makers at tiered companies.

Smartlead does **not** have a built-in lead finder. Source contacts from:
- **Apollo / Clay / Lusha / Hunter** (verified work emails)
- **LinkedIn Sales Navigator** exports (enrich with Clay or Apollo)
- **Your existing CRM**

Filter by titles: VP Sales, Head of Growth, Director of Marketing, CEO, Founder, CRO.
Store prospects in a CSV with columns: `first_name, last_name, email, company_name, phone_number, website, location, linkedin_profile, job_title, tier, personalized_line`.

---

## Step 3: Enrich Contacts

**Goal:** Verify emails and gather personalization signals.

1. Run emails through a verifier (NeverBounce, ZeroBounce, MillionVerifier, or Clay's waterfall). **Smartlead does not verify at import** — bad emails count against your sender reputation.
2. Gather personalization signals per lead: recent LinkedIn posts, hiring signals, tech stack, recent funding, podcast appearances.
3. Drop signals into a `personalized_line` column — it will become `{{personalized_line}}` in the sequence via `custom_fields`.

---

## Step 4: Generate Email Copy

**Goal:** Write personalized email sequences for each tier.

1. Select frameworks from `copy-frameworks.md` based on tier:
   - **Tier 1:** Highly personalized, direct value prop or case study
   - **Tier 2:** Semi-personalized, problem-agitate-solve
   - **Tier 3:** Template-based, social proof
2. Use **Smartlead merge tags** (snake_case): `{{first_name}}`, `{{company_name}}`, `{{custom_var_1}}` etc.
3. Generate 3–4 step sequences (initial + follow-ups).
4. Create A/B variants for the subject line and opening line (Smartlead supports up to 5 variants per step).
5. Output to `outputs/email-sequences.md` as HTML snippets ready for the API call.

---

## Step 5: Auto-Deploy to Smartlead (End-to-End API)

**Goal:** Go from CSV + copy doc → live campaign with one script run.

The agent runs these calls in order. `smartlead-api-docs.md` has full payload shapes.

### 5a. Create the campaign
```
POST /campaigns/create
{ "name": "Q2-2026 <Niche> <Tier>", "client_id": null }
```
Capture `id` from the response.

### 5b. Save the sequence
```
POST /campaigns/{id}/sequences
{
  "sequences": [
    {
      "seq_number": 1,
      "seq_delay_details": { "delay_in_days": 0 },
      "variant_distribution_type": "MANUALLY_EQUAL",
      "seq_variants": [
        { "subject": "...", "email_body": "<p>...</p>", "variant_label": "A" },
        { "subject": "...", "email_body": "<p>...</p>", "variant_label": "B" }
      ]
    },
    { "seq_number": 2, "seq_delay_details": { "delay_in_days": 3 }, "seq_variants": [ ... ] }
  ]
}
```

### 5c. Attach sending inboxes
```
GET  /email-accounts/                           → pick IDs
POST /campaigns/{id}/email-accounts
{ "email_account_ids": [12345, 67890] }
```

### 5d. Set the schedule
```
POST /campaigns/{id}/schedule
{
  "timezone": "America/New_York",
  "days_of_the_week": [1,2,3,4,5],
  "start_hour": "09:00",
  "end_hour": "17:00",
  "min_time_btw_emails": 10,
  "max_new_leads_per_day": 50
}
```

### 5e. Upload prospects (batches of ≤ 400)
```
POST /campaigns/{id}/leads
{
  "lead_list": [
    {
      "first_name": "Jon",
      "last_name": "Smith",
      "email": "jon@acme.com",
      "company_name": "Acme",
      "website": "https://acme.com",
      "custom_fields": {
        "job_title": "VP Sales",
        "personalized_line": "loved your talk at SaaStr",
        "tier": "1"
      }
    }
  ],
  "settings": { "ignore_duplicate_leads_in_other_campaign": false }
}
```

### 5f. Launch
```
PATCH /campaigns/{id}/status
{ "status": "START" }
```

---

## Strategy Documents
- `scoring-criteria.md` → ICP scoring rubric (read before scoring)
- `copy-frameworks.md` → Email copy rules (read before writing sequences)
- `smartlead-api-docs.md` → API reference (read before API calls)

## Pipeline Order
1. Score companies → `outputs/companies-scored.csv`
2. Source + enrich decision-makers → `outputs/prospects.csv`
3. Generate copy → `outputs/email-sequences.md`
4. Auto-deploy campaign via API → live in Smartlead 🚀
5. Pull analytics → `outputs/campaign-report.md`

## Environment
- API key lives in `.env` as `SMARTLEAD_API_KEY` — load with `python-dotenv`
- Always authenticate via `?api_key=` query param
- All Python scripts should include error handling (retry on 429, log 422 validation errors)
- Log every action with timestamp to `outputs/pipeline-log.md`

## Merge Tag Reference (Smartlead)
- Standard: `{{first_name}}`, `{{last_name}}`, `{{email}}`, `{{company_name}}`, `{{phone_number}}`, `{{website}}`, `{{location}}`
- Custom: any key inside a lead's `custom_fields` object, e.g. `{{job_title}}`, `{{personalized_line}}`, `{{tier}}`
- Tags are **case-sensitive** — match the casing you uploaded

## Anti-patterns to avoid
- ❌ Using Saleshandy-style `{{First Name}}` — it will render as literal text in Smartlead
- ❌ Plain-text `email_body` — breaks rendering
- ❌ Uploading > 400 leads in one request — will 422
- ❌ Hardcoding `email_account_ids` — fetch them dynamically per environment
- ❌ Starting a campaign before attaching at least one email account — it will sit idle
