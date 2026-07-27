"""Step 10: Copy Agent - post-import email/LinkedIn copy generation.

Runs after the HubSpot import succeeds (best-effort: a failure here never
sinks the import, matching the HeyReach push in heyreach.py). Generates one
5-step email + LinkedIn sequence for the whole just-imported contact list -
no segmentation (that step was cut; every enriched contact gets the same
sequence)."""
from __future__ import annotations

import json

import pandas as pd
from anthropic import Anthropic

from .. import config

MODEL = "claude-opus-4-1"
_SAMPLE_SIZE = 10  # a few real leads for context, not sent to shape any bucketing


def is_configured() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _lead_brief(row: dict) -> dict:
    return {
        "first_name": row.get("first_name"),
        "company": row.get("organization_name") or row.get("company_name") or row.get("search_company"),
        "title": row.get("title"),
    }


def generate_copy(lead_count: int, sample_leads: list[dict]) -> dict:
    """One 5-step email + LinkedIn sequence for the whole contact list."""
    client = Anthropic()
    prompt = f"""Generate a 5-step email sequence for this list of {lead_count} enriched leads.

Sample leads (for context/tone, not an exhaustive list):
{json.dumps(sample_leads, indent=2, default=str)}

Requirements:
- 5 steps with delays (0, 3, 5, 7, 10 days)
- 2 subject line A/B variants per step
- Email body in HTML (wrap paragraphs in <p> tags)
- Smartlead merge tags: {{{{first_name}}}}, {{{{company_name}}}}, {{{{email}}}}
- 4 sentences max per email, each under 15 words
- No banned phrases (e.g. "I hope you're doing well", "Let me introduce myself")
- Include a LinkedIn cadence (profile visits, likes, connects, DMs)

Return ONLY JSON, no markdown:
{{
  "email_sequences": [{{"step": 1, "delay_days": 0, "subject_a": "...", "subject_b": "...", "body_a": "<p>...</p>", "body_b": "<p>...</p>"}}, ...],
  "linkedin_sequences": [{{"step": 1, "action": "Profile visit", "message": null}}, ...]
}}"""
    response = client.messages.create(model=MODEL, max_tokens=2500, messages=[{"role": "user", "content": prompt}])
    text = response.content[0].text
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


def run(df: pd.DataFrame) -> dict:
    """Best-effort - never raises into the caller. Returns a status dict."""
    if not is_configured():
        return {"status": "not_configured", "message": "ANTHROPIC_API_KEY not set - Copy Agent skipped."}
    if df.empty or "email" not in df.columns:
        return {"status": "no_leads", "message": "No enriched contacts to generate copy for."}

    rows = [r for r in df.to_dict("records") if str(r.get("email") or "").strip().lower() not in ("", "nan", "none")]
    if not rows:
        return {"status": "no_leads", "message": "No leads with an email to generate copy for."}

    try:
        sample = [_lead_brief(r) for r in rows[:_SAMPLE_SIZE]]
        copy = generate_copy(len(rows), sample)
        return {"status": "done", "lead_count": len(rows), "copy": copy}
    except Exception as e:
        return {"status": "error", "message": f"Copy Agent failed: {e}"}


def build_markdown(campaign_title: str, result: dict) -> str:
    if result["status"] != "done":
        return f"# Copy Agent - {campaign_title}\n\n{result.get('message', result['status'])}\n"

    lines = [f"# Copy Agent - {campaign_title}", f"\n{result['lead_count']} lead(s)", ""]
    seq = result["copy"]
    for email in seq.get("email_sequences", []):
        lines.append(f"\n## Step {email['step']} (delay {email['delay_days']}d)")
        lines.append(f"**Subject A:** {email['subject_a']}")
        lines.append(f"**Subject B:** {email['subject_b']}")
        lines.append(f"\n**Body A:**\n{email['body_a']}")
        lines.append(f"\n**Body B:**\n{email['body_b']}")
    li = seq.get("linkedin_sequences", [])
    if li:
        lines.append("\n**LinkedIn cadence:**")
        for step in li:
            lines.append(f"- Step {step['step']}: {step['action']}" + (f" - {step['message']}" if step.get("message") else ""))
    return "\n".join(lines)
