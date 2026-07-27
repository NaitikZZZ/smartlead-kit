# Copy Agent (Enhanced) — Backend Integration

The enhanced copy agent uses **HUMANVOICE_COPY_GUIDE** + **ICP_PERSONAS_REFERENCE** to generate persona-driven email and LinkedIn sequences.

## How It Works

### 1. Persona Detection

When `copy_agent.run(df)` is called, the agent **automatically detects**:
- **Seniority level** from job title: C-Suite, VP/Director, or Manager/IC
- **Primary product angle** from title + industry: Empuls, Plum, Compass, or Loyalife
- **Use case** from title keywords: Recognition, Commission, Rewards, Survey, etc.
- **Vertical** from industry field: Healthcare, Financial, Tech, Retail, etc.
- **Company size category** from employee count: Small, Mid-Market, Enterprise, Large

### 2. HUMANVOICE Prompt Generation

Using detected persona context, the agent builds a system prompt that:
- Includes HUMANVOICE tone rules (short sentences, contractions, concrete details)
- Sets proof style appropriate to seniority (G2 for C-suite, timeline for VP, friction reduction for IC)
- Includes product-specific pain point and proof keywords
- Structures the 5-email arc (pain → proof 1 → reframe → big proof → breakup)

### 3. Claude Generation

Calls Claude Opus 4.8 with:
- Sample leads (first 10) for tone context
- Persona summary and product angle
- HUMANVOICE rules + structured arc
- Returns JSON with 5 email steps (A/B variants) + 5 LinkedIn steps

### 4. Markdown Output

`build_markdown()` outputs:
- Detected persona (title, company size, vertical, use case)
- Product angle (Empuls/Plum/Compass/Loyalife)
- 5 email steps with both A and B variants
- 5 LinkedIn cadence steps (profile visit, like, connect, DM, breakup)

---

## Input (DataFrame)

The `copy_agent.run(df)` expects columns:
- `email` (required) — filters out rows without valid emails
- `title` (recommended) — for persona detection
- `organization_name` or `company_name` (recommended) — context for tone
- `employee_count` (optional) — for company size category
- `industry` (optional) — for vertical detection

---

## Output

```python
{
  "status": "done" | "not_configured" | "no_leads" | "parse_error" | "error",
  "lead_count": 42,
  "persona_detected": {
    "seniority": "VP/Director",
    "persona_type": "VP HR",
    "primary_product": "Empuls",
    "use_case": "Employee Recognition",
    "vertical": "Healthcare",
    "size_category": "Enterprise (1K-5K)",
    "company_size": 2500
  },
  "copy": {
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
}
```

---

## Persona Detection Examples

### C-Suite / CHRO
- **Input title:** "Chief People Officer", "VP People & Culture", "CHRO"
- **Detected:** seniority="C-Suite", persona_type="CHRO/CPO", primary_product="Empuls"
- **Proof style:** G2 rating, named enterprise customer, board-level outcome
- **CTA style:** Strategic narrative about retention/culture

### VP HR / Director HR
- **Input title:** "VP HR", "Director of Human Resources", "Head of People Operations"
- **Detected:** seniority="VP/Director", persona_type="VP HR", primary_product="Empuls"
- **Proof style:** Timeline (90 days), adoption jump (%), QBR proof
- **CTA style:** Easy-friction walkthrough, "show me how your peer company did it"

### HR Ops / People Operations Manager
- **Input title:** "HR Operations Lead", "People Operations Manager", "HR Systems Manager"
- **Detected:** seniority="Director/Manager", persona_type="HR Ops Lead", primary_product="Plum"
- **Proof style:** Speed (30 seconds, one-click), friction reduction, adoption stats
- **CTA style:** "No more procurement tickets", fast integration proof

### VP Sales / RevOps (Compass angle)
- **Input title:** "VP Sales Operations", "Director Revenue Operations", "Head of Sales Ops"
- **Detected:** seniority="VP/Director", persona_type="VP RevOps", primary_product="Compass"
- **Proof style:** Accuracy % (95% day one), dispute reduction, time saved per month
- **CTA style:** Commission sandbox, "see your live earnings"

---

## Overriding Persona Detection

Pass explicit persona hints:

```python
result = copy_agent.run(
    df,
    persona_hints={
        "primary_product": "Plum",
        "use_case": "Referral Program Rewards",
        "vertical": "Tech SaaS"
    }
)
```

This overrides auto-detection for product/use case/vertical while keeping seniority and size auto-detected.

---

## Markdown Output Format

The `build_markdown(campaign_title, result)` returns:

```markdown
# Copy Agent - Q2-2026 Empuls Healthcare

**Detected Persona:** VP HR | Enterprise (1K-5K) | Healthcare
**Product Angle:** Empuls - Employee Recognition

42 lead(s)

## Step 1 (day 0)
**Subject A:** {{first_name}}, quick question about recognition at {{company_name}}
**Subject B:** How {{company_name}}'s peers automated employee R&R

**Body A:**
<p>Most People teams at {{company_name}}'s size...</p>

**Body B:**
<p>Following up on X...</p>

## Step 2 (day 3)
...

**LinkedIn Cadence:**
- Day 1: Profile visit
- Day 1: Like recent post
- Day 4: Connection request
- Day 7: Direct message
- Day 11: Breakup message
```

---

## Integration Points

### runner.py
```python
copy_result = copy_agent.run(df)  # Line 1345
markdown = copy_agent.build_markdown(campaign_title, copy_result)  # Line 1351
```

### inngest_runner.py
```python
copy_result = await step.run("copy_agent_run", _run_copy_agent)  # Line 1054
markdown = copy_agent.build_markdown(campaign_title, copy_result)  # Line 1060
```

Both are backward compatible with the enhanced version.

---

## Persona-to-Product Mapping (Built-In)

The agent auto-selects the best product based on persona:

| Persona Title | Primary Product | Use Case |
|---|---|---|
| CHRO, VP People | Empuls | Employee Recognition |
| VP HR, HR Director | Empuls | Total Rewards Strategy |
| HR Ops, People Ops Manager | Empuls/Plum | Recognition or Gifting |
| VP Sales, VP RevOps | Compass | Commission Automation |
| VP Sales Ops, Revenue Analyst | Compass | Commission + SPIFFs |
| VP Customer Success, CX Lead | Loyalife, Plum | Loyalty or NPS Rewards |
| Marketing Ops, Growth Operations | Plum | Referral Program Rewards |
| Research Manager, Survey Admin | Plum | Survey Incentives |

Override via `persona_hints` if needed.

---

## Testing Locally

```python
from wrapper.backend.app.pipeline import copy_agent
import pandas as pd

# Test with sample data
df = pd.DataFrame({
    "email": ["jane@acme.com", "john@acme.com"],
    "first_name": ["Jane", "John"],
    "company_name": ["Acme Corp", "Acme Corp"],
    "title": ["VP HR", "Head of People"],
    "employee_count": [2500, 2500],
    "industry": ["Healthcare"]
})

result = copy_agent.run(df)
print(result["status"])  # Should be "done"
print(result["persona_detected"]["persona_type"])  # Should be "VP HR"
print(result["persona_detected"]["primary_product"])  # Should be "Empuls"

markdown = copy_agent.build_markdown("Test Campaign", result)
print(markdown)
```

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `status: "not_configured"` | `ANTHROPIC_API_KEY` not set | Add to `.env` |
| `status: "no_leads"` | All rows have empty `email` | Enrich pipeline needs to populate emails |
| `status: "parse_error"` | Claude response not valid JSON | Check Claude API logs, retry |
| Persona detection is wrong | Title doesn't contain expected keywords | Use `persona_hints` to override |
| Copy doesn't mention my product | Wrong product auto-detected from title | Pass explicit `primary_product` hint |

---

## Performance Notes

- **Time:** ~30-45 seconds (includes Claude API call with 3000 token context)
- **Cost:** ~$0.15-0.30 per run (Opus 4.8 pricing)
- **Tokens:** ~2,000-3,000 per run (input + output)

Safe to run for every campaign (best-effort: never sinks the import if it fails).
