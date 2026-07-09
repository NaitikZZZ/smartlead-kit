# Smartlead API Documentation

> Source: https://api.smartlead.ai/ (OpenAPI / REST)

## Base URL
```
https://server.smartlead.ai/api/v1
```

## Authentication
Smartlead uses an **API key passed as a query parameter** on every request:
```
?api_key=YOUR_API_KEY
```
Get your API key from: **Settings → API Keys** in the Smartlead dashboard.

> ⚠️ Never commit your API key. Load it from `.env` with `python-dotenv`.

---

## Merge Tag Format (IMPORTANT)

Smartlead uses **snake_case lowercase tags** — different from Saleshandy:

| Standard tag | Notes |
|---|---|
| `{{first_name}}` | Lead first name |
| `{{last_name}}` | Lead last name |
| `{{email}}` | Lead email |
| `{{company_name}}` | Company name |
| `{{phone_number}}` | Phone |
| `{{website}}` | Website |
| `{{location}}` | Location |
| `{{custom_var_1}}` … `{{custom_var_n}}` | Anything you upload in `custom_fields` |

Use these **exactly** in `subject` and `email_body`. Lead rows are uploaded with matching snake_case keys.

---

## Full Auto-Create Flow (API only, no UI clicks)

The five calls that take you from nothing to a live campaign:

```
1. POST /campaigns/create                        → get campaign_id
2. POST /campaigns/{id}/sequences                → save all email steps
3. POST /campaigns/{id}/email-accounts           → attach sending inboxes
4. POST /campaigns/{id}/schedule                 → set sending window
5. POST /campaigns/{id}/leads                    → upload prospects (max 400/request)
6. PATCH /campaigns/{id}/status  body {status:"START"}  → launch
```

---

## 📋 Campaigns

### POST `/campaigns/create`
Create an empty campaign.

**Body:**
```json
{
  "name": "Q2-2026 TiltIt Agencies Tier-1",
  "client_id": null
}
```

**Response:**
```json
{
  "ok": true,
  "id": 1337420,
  "name": "Q2-2026 TiltIt Agencies Tier-1",
  "created_at": "2026-04-13T17:00:00.000Z"
}
```

Keep `id` — every other call needs it.

---

### GET `/campaigns/`
List all campaigns.

### GET `/campaigns/{campaign_id}`
Fetch one campaign.

---

### POST `/campaigns/{campaign_id}/sequences` ⭐ AUTO-CREATE SEQUENCE
Replace/save the full sequence of email steps in one call.

**Body:**
```json
{
  "sequences": [
    {
      "seq_number": 1,
      "seq_delay_details": { "delay_in_days": 0 },
      "variant_distribution_type": "MANUALLY_EQUAL",
      "lead_distribution_percentage": 50,
      "winning_metric_property": "OPEN_RATE",
      "seq_variants": [
        {
          "subject": "Quick question, {{first_name}}",
          "email_body": "<p>Hi {{first_name}},</p><p>Saw that {{company_name}} is scaling its sales team.</p><p>Would it make sense to show you a quick demo?</p><p>Cheers,<br/>[Your Name]</p>",
          "variant_label": "A"
        },
        {
          "subject": "{{first_name}}, noticed something about {{company_name}}",
          "email_body": "<p>Hey {{first_name}},</p><p>Your team at {{company_name}} probably spends hours on manual prospecting…</p>",
          "variant_label": "B"
        }
      ]
    },
    {
      "seq_number": 2,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        {
          "subject": "Re: Quick question, {{first_name}}",
          "email_body": "<p>{{first_name}}, just bumping this up…</p>",
          "variant_label": "A"
        }
      ]
    }
  ]
}
```

**Notes:**
- `seq_number`: step order (1 = first email)
- `seq_delay_details.delay_in_days`: days since previous step (step 1 is always 0)
- `email_body`: **HTML only** — wrap paragraphs in `<p>` / `<div>`
- `seq_variants`: 1–5 A/B variants per step
- `variant_distribution_type`: `MANUALLY_EQUAL`, `AI_EQUAL`, or `AI_BEST_PERFORMING`
- Sending **replaces** the existing sequence — pass the whole thing every time

---

### POST `/campaigns/{campaign_id}/email-accounts`
Attach sending inboxes to the campaign.

**Body:**
```json
{ "email_account_ids": [12345, 67890] }
```

Get IDs from `GET /email-accounts`.

---

### POST `/campaigns/{campaign_id}/schedule`
Set sending window.

**Body:**
```json
{
  "timezone": "America/New_York",
  "days_of_the_week": [1, 2, 3, 4, 5],
  "start_hour": "09:00",
  "end_hour": "17:00",
  "min_time_btw_emails": 10,
  "max_new_leads_per_day": 50,
  "schedule_start_time": "2026-04-14T09:00:00"
}
```

- `days_of_the_week`: `1` = Mon … `7` = Sun
- `min_time_btw_emails`: minutes between sends per inbox

---

### PATCH `/campaigns/{campaign_id}/settings`
Tune campaign behavior.

**Body:**
```json
{
  "track_settings": ["DONT_TRACK_EMAIL_OPEN"],
  "stop_lead_settings": "REPLY_TO_AN_EMAIL",
  "unsubscribe_text": "Not interested? Just reply 'no thanks'.",
  "send_as_plain_text": false,
  "follow_up_percentage": 100,
  "add_unsubscribe_tag": true
}
```

---

### PATCH `/campaigns/{campaign_id}/status` ⭐ LAUNCH
Start, pause, or stop the campaign.

**Body:**
```json
{ "status": "START" }
```
Values: `START` · `PAUSED` · `STOPPED`

---

## 👥 Leads

### POST `/campaigns/{campaign_id}/leads` ⭐ UPLOAD PROSPECTS
Upload leads directly into the campaign. **Max 400 per request** — batch larger lists.

**Body:**
```json
{
  "lead_list": [
    {
      "first_name": "Jon",
      "last_name": "Smith",
      "email": "jon@acme.com",
      "phone_number": "+15555550100",
      "company_name": "Acme",
      "website": "https://acme.com",
      "location": "San Francisco, CA",
      "custom_fields": {
        "Job Title": "VP Sales",
        "Personalized Line": "loved your talk at SaaStr",
        "Tier": "1"
      },
      "linkedin_profile": "https://www.linkedin.com/in/jonsmith",
      "company_url": "acme.com"
    }
  ],
  "settings": {
    "ignore_global_block_list": false,
    "ignore_unsubscribe_list": false,
    "ignore_community_bounce_list": false,
    "ignore_duplicate_leads_in_other_campaign": false
  }
}
```

**Response:**
```json
{
  "ok": true,
  "upload_count": 1,
  "total_leads": 1,
  "already_added_to_campaign": 0,
  "invalid_email_count": 0,
  "duplicate_count": 0,
  "block_count": 0,
  "unsubscribed_leads": 0,
  "bounce_count": 0
}
```

**Rules:**
- `email` is required
- Any key inside `custom_fields` becomes a merge tag available as `{{Job Title}}` (Smartlead preserves the key name you upload). For safety, use snake_case keys: `{"job_title": "VP Sales"}` → `{{job_title}}`
- Duplicates across campaigns are blocked by default unless you set `ignore_duplicate_leads_in_other_campaign: true`

---

### GET `/campaigns/{campaign_id}/leads`
Paginated list of leads in a campaign.

### PATCH `/campaigns/{campaign_id}/leads/{lead_id}/status`
Change lead status: `PAUSED`, `STOPPED`, `INPROGRESS`, `COMPLETED`.

### GET `/leads/by-email?email=...`
Find a lead globally by email.

---

## 📧 Email Accounts

### GET `/email-accounts/`
List all connected inboxes. Returns IDs you need for `email-accounts` on a campaign.

### POST `/email-accounts/save`
Register a new SMTP/IMAP inbox.

### PATCH `/email-accounts/{id}`
Update inbox settings (daily limit, signature, warmup, etc.).

### GET `/email-accounts/{id}/warmup-stats`
Warmup health for a single inbox.

---

## 🔔 Webhooks

### POST `/webhooks`
Create a webhook for events (`EMAIL_SENT`, `EMAIL_OPEN`, `EMAIL_REPLY`, `LEAD_CATEGORY_UPDATED`, etc.).

**Body:**
```json
{
  "name": "Reply notifier",
  "webhook_url": "https://your-webhook.com/smartlead",
  "event_types": ["EMAIL_REPLY"],
  "categories": ["Interested"]
}
```

### GET `/webhooks`  ·  PATCH `/webhooks/{id}`  ·  DELETE `/webhooks/{id}`

---

## 📊 Analytics

### GET `/campaigns/{campaign_id}/analytics`
Campaign KPIs: sent, opened, replied, bounced, unsubscribed, clicked, positive/negative reply counts.

### GET `/analytics/overview`
Workspace-wide roll-up across all campaigns.

---

## Error Handling

Smartlead returns JSON errors shaped like:
```json
{ "ok": false, "message": "Invalid API key" }
```

Common statuses:

| HTTP | Meaning |
|---|---|
| 401 | Missing / invalid `api_key` |
| 404 | Campaign or lead not found |
| 422 | Validation error (check body shape) |
| 429 | Rate limited — back off |

## Rate Limits
Smartlead enforces per-workspace rate limits. For large imports:
- Keep lead batches at **≤ 400 per request**
- Sleep ~300 ms between batches
- Retry 429s with exponential backoff
