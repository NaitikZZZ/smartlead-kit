# Copy Agent (Step 10) — Standalone Quick Start

Run **only the copy agent** on enriched leads without running the full pipeline.

## ⚡ Quick Usage

### From CLI

```bash
cd wrapper/backend

# Basic: Run on enriched CSV
python run_copy_agent_only.py --csv leads.csv

# With custom output directory
python run_copy_agent_only.py --csv leads.csv --output-dir ./my_output

# Override persona detection (Empuls angle, Healthcare vertical)
python run_copy_agent_only.py --csv leads.csv --product Empuls --vertical Healthcare

# With campaign title
python run_copy_agent_only.py --csv leads.csv --title "Q2-2026 Empuls Healthcare"
```

### From Python

```python
from run_copy_agent_only import run_copy_agent_on_csv

result = run_copy_agent_on_csv(
    csv_path="leads.csv",
    output_dir="./output",
    campaign_title="My Campaign",
    product_hint="Empuls",
    vertical_hint="Healthcare"
)

print(result["status"])  # "done"
print(result["persona_detected"])  # Auto-detected persona
```

---

## 📊 Input CSV Requirements

Your CSV **must have**:
- `email` column (required, used to filter valid rows)

**Recommended columns** (for better persona detection):
- `title` — Job title (e.g., "VP HR", "Director of People")
- `organization_name` or `company_name` — Company name for context
- `employee_count` — Company size (for sizing category)
- `industry` — Industry/vertical (e.g., "Healthcare", "Financial Services")

**Everything else** is preserved and available as merge tag context.

### Example CSV

```csv
email,first_name,last_name,title,organization_name,employee_count,industry,country
jane@acme.com,Jane,Smith,VP HR,Acme Corp,2500,Healthcare,USA
john@acme.com,John,Doe,Director of People Ops,Acme Corp,2500,Healthcare,USA
```

---

## 📤 Output Files

Three files are written to `--output-dir`:

### 1. `10_copy_agent.json`
Raw JSON with all 5 email steps + 5 LinkedIn steps. Ready to post to Smartlead or HeyReach APIs.

```json
{
  "email_sequences": [
    {
      "step": 1,
      "delay_days": 0,
      "subject_a": "{{first_name}}, quick question about recognition at {{company_name}}",
      "subject_b": "How {{company_name}}'s peers automated employee R&R",
      "body_a": "<p>Most People teams...</p>",
      "body_b": "<p>Following up...</p>"
    },
    ... (4 more steps)
  ],
  "linkedin_sequences": [
    {
      "step": 1,
      "action": "Profile visit",
      "message": null
    },
    ... (4 more steps)
  ]
}
```

### 2. `10_COPY_AGENT.md`
Human-readable markdown with detected persona + all sequences (both A/B variants).

```markdown
# Copy Agent - My Campaign

**Detected Persona:** VP HR | Enterprise (1K-5K) | Healthcare
**Product Angle:** Empuls - Employee Recognition

42 lead(s)

## Step 1 (day 0)
**Subject A:** {{first_name}}, quick question about recognition at {{company_name}}
**Subject B:** How {{company_name}}'s peers automated employee R&R

**Body A:**
<p>Most People teams...</p>

**Body B:**
<p>Following up...</p>

...

**LinkedIn Cadence:**
- Day 1: Profile visit
- Day 1: Like recent post
- Day 4: Connection request
- Day 7: Direct message
- Day 11: Breakup message
```

### 3. `persona_detected.json`
What the agent auto-detected from your leads.

```json
{
  "seniority": "VP/Director",
  "persona_type": "VP HR",
  "primary_product": "Empuls",
  "use_case": "Employee Recognition",
  "vertical": "Healthcare",
  "size_category": "Enterprise (1K-5K)",
  "company_size": 2500
}
```

---

## 🎯 Persona Detection

The copy agent **automatically detects**:

### Seniority (from title keywords)
- **C-Suite:** CHRO, "Chief People", VP People (top-level only)
- **VP/Director:** VP HR, Director HR, Head of HR, Head of People
- **Manager/IC:** HR Ops, HR Manager, People Ops, HR Coordinator

### Primary Product (from title + industry)
- **Empuls:** HR-focused titles (default)
- **Plum:** Marketing, Growth, Rewards, Gifting
- **Compass:** Sales, RevOps, Commission, Incentive
- **Loyalife:** Customer Success, Loyalty, CX titles

### Vertical (from industry field)
- Healthcare, Financial Services, Technology, Retail/Hospitality

### Company Size (from employee_count)
- Small (< 200)
- Mid-Market (200–1K)
- Enterprise (1K–5K)
- Large Enterprise (5K+)

### Use Case (from title keywords)
- Recognition, Commission, Rewards, Survey, etc.

---

## 🔧 Overriding Detection

Use `--product` and `--vertical` flags to override auto-detection:

```bash
# Force Plum product angle (Rewards API)
python run_copy_agent_only.py --csv leads.csv --product Plum

# Force Tech vertical
python run_copy_agent_only.py --csv leads.csv --vertical Tech

# Both
python run_copy_agent_only.py --csv leads.csv --product Compass --vertical Finance
```

Or in Python:

```python
result = run_copy_agent_on_csv(
    "leads.csv",
    product_hint="Plum",
    vertical_hint="Finance"
)
```

---

## 📋 Example Workflows

### Workflow 1: Generate Copy for Existing Enriched List

```bash
# You have leads from your enrichment pipeline (already have email, title, company, etc.)
python run_copy_agent_only.py --csv my_enriched_leads.csv --output-dir ./copy_output

# Review the markdown
cat ./copy_output/10_COPY_AGENT.md

# Deploy to Smartlead
curl -X POST https://api.smartlead.io/v1/campaigns/12345/sequences \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @./copy_output/10_copy_agent.json
```

### Workflow 2: Iterate on Copy (Try Different Angles)

```bash
# Try Empuls angle first
python run_copy_agent_only.py --csv leads.csv --product Empuls --output-dir ./empuls_output

# Try Plum angle
python run_copy_agent_only.py --csv leads.csv --product Plum --output-dir ./plum_output

# Compare the two markdown files and pick the better one
diff ./empuls_output/10_COPY_AGENT.md ./plum_output/10_COPY_AGENT.md
```

### Workflow 3: Generate Copy from Cold List (Only Names + Emails)

```bash
# Even if you only have first_name, last_name, email, company
# The copy agent will still work (seniority detection might be generic)
python run_copy_agent_only.py --csv cold_list.csv \
  --product Empuls \
  --vertical Healthcare

# The persona detection will fall back to defaults, but you've guided it
# with --product and --vertical hints
```

---

## ⏱️ Performance

| Stage | Time | Cost |
|---|---|---|
| Load CSV | < 1s | Free |
| Copy generation (Claude) | 30–45s | ~$0.15 |
| Write output files | < 1s | Free |
| **Total** | **30–45s** | **~$0.15** |

**Much faster than full pipeline** (10–15 minutes with enrichment steps).

---

## 🐛 Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `CSV not found` | Wrong path | Use absolute path or relative from `wrapper/backend/` |
| `CSV must have 'email' column` | Missing email column | Rename column to `email` |
| `status: "not_configured"` | `ANTHROPIC_API_KEY` not set | Add to `wrapper/backend/.env` |
| `status: "no_leads"` | All rows have empty email | Enrich your list first or filter |
| `parse_error` | Claude response malformed | Retry (usually API timeout) |
| Persona detection is wrong | Title doesn't match keywords | Use `--product` and `--vertical` flags |
| Copy mentions wrong product | Wrong product auto-detected | Use `--product` flag to override |

---

## 🎓 Advanced: Programmatic Loop

Generate copy for multiple CSV files:

```python
from pathlib import Path
from run_copy_agent_only import run_copy_agent_on_csv

# Loop through CSVs in a directory
for csv_file in Path("./leads").glob("*.csv"):
    print(f"\nProcessing {csv_file.name}...")
    
    result = run_copy_agent_on_csv(
        csv_path=str(csv_file),
        output_dir=f"./output/{csv_file.stem}",
        campaign_title=csv_file.stem
    )
    
    if result["status"] == "done":
        print(f"✅ {result['lead_count']} leads → {result['persona_detected']['persona_type']}")
    else:
        print(f"❌ {result['status']}: {result.get('message')}")
```

---

## 📚 Reference

- **Backend integration:** See `wrapper/backend/COPY_AGENT_README.md`
- **Tone rules:** See `HUMANVOICE_COPY_GUIDE.md`
- **ICP mapping:** See `ICP_PERSONAS_REFERENCE.md`
- **Copy frameworks:** See `copy-frameworks.md`
