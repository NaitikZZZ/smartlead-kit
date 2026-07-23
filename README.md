# 🚀 AI Cold Email Campaign Kit — **Smartlead × Xoxoday Edition**

## 🌐 Live Demo

**Access the app here:**
```
https://photos-cabin-manufacturer-allowed.trycloudflare.com
```

---

> A Claude-powered GTM starter kit that scores companies, writes personalized sequences, and **auto-creates the full campaign in Smartlead via API** — campaign, sequence steps, A/B variants, schedule, sending inboxes, and uploaded prospects, all from natural-language prompts.
>
> 📦 **Reference product: [Xoxoday](https://www.xoxoday.com/)** — the scoring rubric and email frameworks are pre-tuned for Xoxoday's suite: **Empuls** (employee R&R + engagement), **Plum** (rewards/incentives API, 10M+ catalog across 175+ countries), **Compass** (sales commission automation), and **Loyalife** (customer loyalty). Swap the product voice in `copy-frameworks.md` if you're pitching a different SKU.

> Original Saleshandy version by Manthan Patel (@LeadGenMan) — [repo](https://github.com/cupel-cloud/ai-cold-email-campaign-kit).
> This fork swaps the stack to **[Smartlead](https://www.smartlead.ai/)** because Smartlead's API lets you build the campaign and sequence programmatically — no UI pre-setup required.

---

## 🆚 What's Different From the Saleshandy Kit

| | Saleshandy kit | **Smartlead kit (this one)** |
|---|---|---|
| Create campaign | Must pre-create in UI | `POST /campaigns/create` |
| Build sequence | Must pre-create in UI, then import to step | `POST /campaigns/{id}/sequences` with full step + variant JSON |
| Add prospects | Import to a pre-built step | `POST /campaigns/{id}/leads` (up to 400/batch) |
| Launch | `POST /sequences/status` | `PATCH /campaigns/{id}/status` (`START`) |
| Merge tags | `{{First Name}}`, `{{Company}}` (Title Case) | `{{first_name}}`, `{{company_name}}` (snake_case) |
| Email body | HTML | HTML |
| Auth | `x-api-key` header | `?api_key=` query param |
| Built-in lead finder | ✅ (800M contacts) | ❌ — source from Apollo/Clay/Sales Nav |

**Bottom line:** with Smartlead the agent runs the entire deploy end-to-end via API. One prompt → live campaign.

---

## 📁 Folder Structure

```
smartlead-kit/
├── CLAUDE.md               ← Brain file. Pipeline, rules, API call order.
├── scoring-criteria.md     ← ICP scoring rubric (tiering template)
├── copy-frameworks.md      ← 3 proven email frameworks w/ Smartlead merge tags
├── smartlead-api-docs.md   ← API reference for every call the agent makes
├── .env.example            ← Copy to .env and drop your key in
├── .gitignore
└── outputs/                ← Scored CSVs, sequences, analytics reports land here
```

> 🧠 When Claude opens this project, `CLAUDE.md` is the first thing it reads. That file points it at the scoring rubric, copy frameworks, and API docs. Everything flows from there.

---

## 🔑 Setup (2 minutes)

1. Clone this folder / copy it to a new project directory.
2. Copy `.env.example` → `.env` and fill in your Smartlead API key:
   ```
   SMARTLEAD_API_KEY=sl_live_xxxxxxxxxxxxxxxxxxxx
   ```
   Get the key from Smartlead → **Settings → API Keys**.
3. Open the folder in Claude Code (or ChatGPT with file upload). Claude auto-reads `CLAUDE.md`.
4. Connect at least one sending inbox in Smartlead → **Email Accounts** (SMTP/IMAP or Gmail/Outlook OAuth). You'll need its ID for the deploy step.
5. Drop your raw company list into `outputs/companies.csv`:
   ```csv
   name,domain,industry,employee_count,funding_stage,annual_revenue,technologies
   Acme Corp,acmecorp.com,SaaS,150,Series A,5000000,HubSpot;Slack;AWS
   ```

Done. You can now type prompts at Claude.

---

## ⚡ The Pipeline

```
companies.csv
      │
      ▼
[1] SCORE      → reads scoring-criteria.md → companies-scored.csv
      │
      ▼
[2] SOURCE     → Apollo / Clay / Sales Nav → prospects.csv (with verified emails)
      │
      ▼
[3] WRITE      → reads copy-frameworks.md → email-sequences.md (HTML, Smartlead tags)
      │
      ▼
[4] AUTO-DEPLOY (API)
      ├── POST /campaigns/create
      ├── POST /campaigns/{id}/sequences          ← sequence + A/B variants
      ├── POST /campaigns/{id}/email-accounts     ← attach sending inboxes
      ├── POST /campaigns/{id}/schedule           ← sending window
      ├── POST /campaigns/{id}/leads (≤400/batch) ← upload prospects
      └── PATCH /campaigns/{id}/status {status:"START"}
      │
      ▼
[5] ANALYZE    → GET /campaigns/{id}/analytics → campaign-report.md
```

---

## 💬 Prompts to Run Each Step

Paste these directly into Claude after opening the project folder:

| Step | Prompt |
|---|---|
| **Score** | "Score the companies in `outputs/companies.csv` against our ICP criteria and save tiered results to `outputs/companies-scored.csv`." |
| **Source** | "For every Tier 1 and Tier 2 company, draft an Apollo/Clay search that would find our target personas. Save the query specs to `outputs/sourcing-plan.md`." |
| **Write** | "Using Framework 1 from `copy-frameworks.md`, write a 4-step HTML sequence with A/B variants on step 1. Use Smartlead snake_case merge tags. Save to `outputs/email-sequences.md`." |
| **Deploy** | "Create a new Smartlead campaign called 'Q2-2026 Empuls — Tier 1 CHROs', push the sequence from `outputs/email-sequences.md`, attach email accounts \\[LIST OR 'all active inboxes'\\], upload all Tier 1 prospects from `outputs/prospects.csv`, and start the campaign." |
| **Analyze** | "Pull the last 7 days of analytics for campaign \\<id\\> from Smartlead and summarize opens, replies, bounces, and top-performing variants in `outputs/campaign-report.md`." |
| **Optimize** | "Based on the analytics, which subject lines and step variants should we keep, kill, or A/B more aggressively next batch?" |

---

## 📧 Copy Frameworks (Smartlead-formatted)

Three battle-tested frameworks ship with the kit (`copy-frameworks.md`):

1. **Direct Value Prop** — Tier 1, highly personalized
2. **Problem-Agitate-Solve (PAS)** — Tier 2, semi-personalized
3. **Social Proof / Agency Angle** — Tier 2–3, template + FOMO

All templates already use Smartlead's `{{first_name}}`, `{{company_name}}`, and `custom_fields` tags. Each step converts 1:1 into an `email_body` HTML string on `POST /campaigns/{id}/sequences`.

---

## 🔌 Smartlead API Cheat Sheet

Base URL: `https://server.smartlead.ai/api/v1`
Auth: append `?api_key=$SMARTLEAD_API_KEY` to every request.

| Purpose | Method + Path |
|---|---|
| Create campaign | `POST /campaigns/create` |
| Save sequence | `POST /campaigns/{id}/sequences` |
| Attach inboxes | `POST /campaigns/{id}/email-accounts` |
| Set schedule | `POST /campaigns/{id}/schedule` |
| Tune settings | `PATCH /campaigns/{id}/settings` |
| Upload leads (≤400) | `POST /campaigns/{id}/leads` |
| Start / pause / stop | `PATCH /campaigns/{id}/status` |
| List inboxes | `GET /email-accounts/` |
| Campaign analytics | `GET /campaigns/{id}/analytics` |
| Webhooks (replies etc.) | `POST /webhooks` |

Full payload shapes: **`smartlead-api-docs.md`**.

---

## 🧪 Quick Smoke Test (curl)

```bash
# List your campaigns — confirms your API key works
curl "https://server.smartlead.ai/api/v1/campaigns/?api_key=$SMARTLEAD_API_KEY"

# Create a throwaway campaign
curl -X POST "https://server.smartlead.ai/api/v1/campaigns/create?api_key=$SMARTLEAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test — delete me","client_id":null}'
```

If both return JSON with `"ok": true`, you're wired up. Hand it to Claude from there.

---

## 💡 Pro Tips

1. **Always verify emails before upload.** Smartlead doesn't verify at import — bad emails tank your sender reputation. Use NeverBounce/ZeroBounce/Clay waterfall first.
2. **Start with 50 prospects, not 500.** Validate ICP scoring and copy before scaling.
3. **Respect the 400-lead batch cap.** Chunk large lists and sleep ~300 ms between calls.
4. **Warm up your inboxes for 2+ weeks** via Smartlead's built-in warmup before going cold.
5. **Use custom variables for personalization.** Upload a `personalized_line` per lead and merge with `{{personalized_line}}` in step 1.
6. **Keep emails under 100 words.** Short emails get more replies.
7. **Send 30–50/day per inbox.** Rotate multiple inboxes to scale throughput without hurting deliverability.
8. **Set `stop_lead_settings: "REPLY_TO_AN_EMAIL"`** so follow-ups auto-pause on reply.
9. **Register a webhook on `EMAIL_REPLY`** to pipe positive replies into Slack or your CRM.
10. **Pull analytics weekly** and feed winning subject lines back into `copy-frameworks.md`.

---

## ❓ FAQ

**Do I need to know how to code?**
No. Claude writes and runs the Python / curl calls. You edit the markdown docs to steer it.

**Why Smartlead vs. Saleshandy?**
Smartlead's API lets the agent create campaigns + sequences programmatically. The Saleshandy kit requires pre-creating sequences in the UI. If you want Claude to spin up entire campaigns from scratch, Smartlead wins.

**Can Smartlead source prospects?**
No built-in lead finder. Pair it with Apollo, Clay, Hunter, or LinkedIn Sales Navigator exports.

**How do I handle deliverability?**
Use proper SPF/DKIM/DMARC on your sending domains, run Smartlead's warmup for 2+ weeks, and rotate multiple inboxes. Tools like [Maildoso](https://maildoso.com/) or [Mailforge](https://mailforge.ai/) can provision pre-warmed inbox infrastructure.

**How many emails per day?**
Start 30–50/day per inbox. Scale to 200–500/day total across rotated inboxes.

---

## 📜 License & Credit

Forked from the excellent [ai-cold-email-campaign-kit](https://github.com/cupel-cloud/ai-cold-email-campaign-kit) by Manthan Patel. This edition retools the integration for Smartlead and adds API-driven auto-creation of campaigns, sequences, and prospect uploads.

Original copy frameworks and scoring rubric concept © Manthan Patel. Smartlead integration layer is free to adapt.

---

> 🚀 **You now have the Smartlead edition.** Open Claude, load your companies, and type your first prompt. Campaign live in minutes, not hours.
