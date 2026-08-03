"""Step 10: Copy Agent (Enhanced) - Persona-driven email/LinkedIn copy generation.

Uses ICP_PERSONAS_REFERENCE + HUMANVOICE_COPY_GUIDE to generate targeted sequences
based on detected persona, use case, and geography. Generates a single 12-step email
sequence + a mirrored LinkedIn sequence (no A/B variants) - see PRODUCT_ANGLES for
the grounded why/features/validation content each product's step 2/3/5 draws from.

Runs after HubSpot import succeeds (best-effort: never sinks the import).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import pandas as pd
from anthropic import Anthropic

from .. import config

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-8"
_SAMPLE_SIZE = 10  # real leads for tone context


# ============================================================================
# ICP PERSONA DETECTION
# ============================================================================

class PersonaDetector:
    """Detect persona, use case, and product angle from prospect data."""

    # Persona title keywords
    CHRO_KEYWORDS = {"chro", "chief people", "chief human", "vp people", "head of people", "chief talent"}
    VP_HR_KEYWORDS = {"vp hr", "vice president hr", "director hr", "head of hr", "head hr"}
    HR_OPS_KEYWORDS = {"hr ops", "hr operations", "people ops", "hr manager", "hr coordinator", "talent operations"}
    VP_SALES_KEYWORDS = {"vp sales", "vice president sales", "head of sales", "chief revenue", "cro", "sales leader"}
    VP_REVOPS_KEYWORDS = {"vp revops", "revenue operations", "sales ops", "head of ops"}
    VP_CX_KEYWORDS = {"vp customer success", "head of cx", "vp loyalty", "customer success", "cpo"}

    # Use case detection from title/company context
    RECOGNITION_KEYWORDS = {"recognition", "engagement", "retention", "peopleware", "culture"}
    COMMISSION_KEYWORDS = {"commission", "incentive comp", "spiff", "payout", "comp"}
    REWARDS_KEYWORDS = {"rewards", "loyalty", "perks", "gifting", "incentive"}
    SURVEY_KEYWORDS = {"research", "insights", "survey", "nps"}

    # Industry vertical detection
    HEALTHCARE_KEYWORDS = {"health", "hospital", "pharma", "clinic", "medical", "nursing"}
    FINANCIAL_KEYWORDS = {"bank", "insurance", "investment", "financial", "fintech"}
    TECH_KEYWORDS = {"software", "saas", "tech", "it services", "consulting"}
    RETAIL_KEYWORDS = {"retail", "ecommerce", "qsr", "hospitality", "restaurant"}

    @classmethod
    def detect_persona(cls, title: Optional[str], company_size: Optional[int], industry: Optional[str]) -> dict:
        """Detect persona from title, company size, and industry."""
        title_lower = (title or "").lower()
        industry_lower = (industry or "").lower()

        # Detect seniority level
        if cls._matches(title_lower, cls.CHRO_KEYWORDS):
            seniority = "C-Suite"
            persona_type = "CHRO/CPO"
        elif cls._matches(title_lower, cls.VP_HR_KEYWORDS):
            seniority = "VP/Director"
            persona_type = "VP HR"
        elif cls._matches(title_lower, cls.HR_OPS_KEYWORDS):
            seniority = "Director/Manager"
            persona_type = "HR Ops Lead"
        elif cls._matches(title_lower, cls.VP_SALES_KEYWORDS):
            seniority = "VP/Director"
            persona_type = "VP Sales"
        elif cls._matches(title_lower, cls.VP_REVOPS_KEYWORDS):
            seniority = "VP/Director"
            persona_type = "VP RevOps"
        elif cls._matches(title_lower, cls.VP_CX_KEYWORDS):
            seniority = "VP/Director"
            persona_type = "VP CX"
        else:
            seniority = "Unknown"
            persona_type = "Prospect"

        # Detect use case angle
        if cls._matches(title_lower, cls.COMMISSION_KEYWORDS):
            primary_product = "Compass"
            use_case = "Commission Automation"
        elif cls._matches(title_lower, cls.REWARDS_KEYWORDS):
            primary_product = "Plum"
            use_case = "Global Rewards"
        elif cls._matches(title_lower, cls.SURVEY_KEYWORDS):
            primary_product = "Plum"
            use_case = "Survey Incentives"
        else:
            primary_product = "Empuls"
            use_case = "Employee Recognition"

        # Detect vertical
        if cls._matches(industry_lower, cls.HEALTHCARE_KEYWORDS):
            vertical = "Healthcare"
        elif cls._matches(industry_lower, cls.FINANCIAL_KEYWORDS):
            vertical = "Financial Services"
        elif cls._matches(industry_lower, cls.TECH_KEYWORDS):
            vertical = "Technology"
        elif cls._matches(industry_lower, cls.RETAIL_KEYWORDS):
            vertical = "Retail/Hospitality"
        else:
            vertical = "General"

        # Estimate company size category
        if not company_size:
            size_category = "Unknown"
        elif company_size < 200:
            size_category = "Small (< 200)"
        elif company_size < 1000:
            size_category = "Mid-Market (200-1K)"
        elif company_size < 5000:
            size_category = "Enterprise (1K-5K)"
        else:
            size_category = "Large Enterprise (5K+)"

        return {
            "seniority": seniority,
            "persona_type": persona_type,
            "primary_product": primary_product,
            "use_case": use_case,
            "vertical": vertical,
            "size_category": size_category,
            "company_size": company_size,
        }

    @staticmethod
    def _matches(text: str, keywords: set) -> bool:
        """Check if any keyword in the set appears in text."""
        return any(kw in text for kw in keywords)


# ============================================================================
# HUMANVOICE PROMPT BUILDER
# ============================================================================

class HumanVoicePromptBuilder:
    """Build the HUMANVOICE ready-to-use prompt with persona context."""

    HUMANVOICE_RULES = """
Voice rules (HUMANVOICE_COPY_GUIDE standard):
- Always formal - this is not friends-and-family correspondence. Short, declarative
  sentences and no hedging is fine (still human, not stiff), but no casual social
  framing until a relationship exists.
- No brochure language, no buzzwords, no exclamation points, no em dashes.
- Assume the prospect has never heard of Xoxoday - introduce the product explicitly
  as "a global [category] company" (see product_global_framing below), don't rely on
  the name alone to carry credibility.
- NEVER name a real client/customer company. Every proof point is a real, specific
  metric (timeframe, %, cost saving, rating) paired with an ANONYMIZED reference -
  "a global [industry] company", "a leading [region] client in [industry]" - never
  the actual company name.
- Show, don't tell - cardinal rule for emails 2 onward. Prove ROI with 2-3 concrete
  data points, never adjective claims ("powerful", "seamless", "game-changing").
  Email 1 is the one exception: no stats, no ROI, no feature talk there at all -
  it is a pure relevance hook, nothing to prove yet.
- Never diminish the prospect's current approach, tool, or role (no "what you do
  doesn't get noticed" style framing) - this reads as an insult, not an insight.
- No casual meetup language ("grab coffee", "grab lunch") on a cold first touch -
  use "happy to meet in person to discuss [topic]" instead. "Same neighbourhood/city"
  framing is fine, the casual verb is the problem.
- Ground every pain point in a specific, sensory scene from this persona's day-to-day
  (not generic "employees" — the actual role and context).
- No banned phrases: "I hope you're doing well", "leverage", "seamless", "cutting-edge",
  "I'd love to pick your brain", "Just checking in", "Would you be open to a quick chat?",
  "grabbing coffee", "grabbing lunch"
- NEVER include a signature block or sign-off name ("Best, [Name]", "Thanks, [Name]",
  a standalone name line, or a company tagline) at the end of any email body. Smartlead
  auto-appends the sender's real signature - a signature in the body causes a double
  signature at send time. End each email on its last real content sentence (the
  question or CTA), nothing after it.

Sequence arc - 12 emails total, each with a defined job (apply the formal/no-names/
show-don't-tell rules above to every one of them). Cadence is open-ended: never
frame any email as the last one, a breakup, or "closing the loop" - the sequence
keeps going until the prospect replies, and every email (not just #1) should read
as if it could be the first one they've gotten from you, no "as discussed,"
"following up," or sequence-position language anywhere:

1. **The ask.** State it clearly in the FIRST sentence itself: same field (and same
   location/city if known) + wanting to show/discuss a solution that solved a
   specific problem for global customers. No pitch, no stats, no ROI numbers, no
   feature talk - pure relevance hook. Still a complete, substantive email (not
   thin or short for its own sake). End on a soft, low-stakes question.
2. **Why [PRODUCT].** Use the why_product framing below verbatim as the grounding fact,
   in your own words - don't just restate it as a slogan, explain what it means for
   THIS persona's day-to-day. Offer before you ask - lead with offering to show this,
   not a request for their time. Proof/ROI data belongs from here onward, never in
   email 1.
3. **Product features.** Pick 2-3 of the key_features below most relevant to this
   persona/seniority and explain what each one solves for them concretely - not a
   bullet dump, weave them into the specific workflow this role owns.
4. **Case studies and customer testimonials.** An anonymized case-study-style
   narrative (a global/regional client in [industry] - never the real name, even
   though some of these are named on the public website) with a before/after arc and
   a real metric, framed as a testimonial-style result rather than a bare stat.
5. **Third-party validation.** Use the third_party_validation figure below - G2
   rating/review count, or the award/company-wide stat if this product has no
   product-specific number (say so plainly, e.g. "we're rated 4.7 on G2 as a
   company" rather than inventing a product-specific figure that doesn't exist).
6. **Recap.** Briefly recap the why, the features, the case study, and the
   validation from emails 2-5 in a few tight sentences - not a bullet list, a natural
   summary - then close with a clear, low-pressure CTA (15 minutes, or happy to meet
   in person to discuss).
7-12. **Recap, restated.** Same job as email 6 - recap + low-pressure CTA - but each
   one reframes the recap differently (lead with a different piece of proof, a
   different angle on the ask, or a different seniority-relevant hook) so it never
   reads as a literal copy-paste of email 6. Keep the tone even and professional
   throughout, never frustrated, never a "last touch."

LinkedIn messages must be shorter and chattier than the emails, and must not repeat
any line, stat, or phrase from the email track word-for-word. Mirror the same 12-step
arc and jobs above, just condensed per channel norms.

Vary sentence openers across the sequence — don't start every message with "Hi
{{first_name}}," followed by the same structure.
"""

    # why_product/key_features/third_party_validation are grounded in real
    # source material (reference/xoxoday_brandbook_2026.md and
    # reference/xoxoday-website/) - confirmed via a dedicated research pass,
    # NOT invented. Where no product-specific G2/Gartner figure exists (Plum,
    # Compass, Loyalife), third_party_validation falls back to the real
    # company-wide figure/award instead of a fabricated product-specific one.
    PRODUCT_ANGLES = {
        "Empuls": {
            "pain_summary": "Recognition is fragmented (Slack, spreadsheets, annual events). Doesn't scale, doesn't integrate, leaders can't prove ROI.",
            "proof_keywords": "adoption timeline, days to rollout, user adoption %, QBR proof",
            "cta_style": "soft question about timeline or adoption for their size",
            "global_framing": "a global employee experience and recognition company",
            "why_product": "An AI-powered employee engagement platform that brings recognition, rewards, surveys, benefits, and a social intranet into one place - trusted by 5,000+ companies across 150+ countries, so engagement becomes how the company works day to day, not a program run on the side.",
            "key_features": [
                "Recognition & Rewards - peer, manager, milestone, and values-based recognition with 10M+ reward options",
                "Social Intranet - company feed, groups, town halls, polls",
                "Surveys & Insights - pulse, lifecycle, 360-degree, and custom surveys with AI-recommended action plans",
                "Perks & Benefits - 10,000+ brand discounts, Lifestyle Spending Accounts, wellness/insurance/financial wellbeing benefits",
                "Sales Incentives - real-time leaderboards, contests, automated commission/SPIFF management",
                "Empuls AI - nudges, sentiment analysis, action recommendations",
                "50+ HRIS, collaboration, and SSO integrations",
            ],
            "third_party_validation": "4.6/5 on G2 (1,400+ reviews) - Best Employee Engagement Software on G2",
        },
        "Plum": {
            "pain_summary": "Manual rewards management. Gift cards from procurement (slow), single-country catalogs (limited), no real choice (low redemption).",
            "proof_keywords": "cost savings %, delivery time reduction, countries supported, integration speed",
            "cta_style": "easy yes about seeing how it works for their use case",
            "global_framing": "a global rewards and incentives company",
            "why_product": "Global rewards and payouts infrastructure built for scale - multiple languages/currencies, enterprise-grade security, no hidden markups, 24/7 global support, and a fully configurable, white-labeled marketplace so anyone can be rewarded anywhere.",
            "key_features": [
                "Reward Points - credit points to user accounts, redeemable from a global marketplace",
                "Reward Codes - alphanumeric codes redeemable instantly without login",
                "Reward Links - trackable links shareable via email, SMS, WhatsApp",
                "Rewards API - automate reward distribution into your own workflows",
                "Marketplace Integration via SSO (SAML 2.0, OIDC, SCIM)",
                "iFrame Embed - responsive rewards catalog embed for web/mobile",
                "10M+ rewards across 150+ countries, 30+ categories",
            ],
            "third_party_validation": "no Plum-specific G2/Gartner rating found - use the company-wide figure instead: 4.7 G2 rating, 5,000+ companies worldwide, 150+ countries",
        },
        "Compass": {
            "pain_summary": "Commission spreadsheets. Manual calcs, month-end disputes, reps can't see real-time earnings, finance recalculates by hand.",
            "proof_keywords": "accuracy %, dispute reduction %, time saved per month, rep adoption",
            "cta_style": "sandbox demo or 15-min walkthrough to see live earnings",
            "global_framing": "a global sales commission automation company",
            "why_product": "A no-code, scalable commission automation and analytics platform covering data management, commission automation, sales rep motivation, compensation, ROI, and AI-powered gamification.",
            "key_features": [
                "No-code, schema-agnostic data integrations - one-click, webhook, or CSV",
                "Metric library - aggregate, formula-based, and mapping-variable metrics for compensation logic",
                "Milestone, plan-based commission plans with configurable conditions",
                "Multi-stage approval workflows for plans and rewards",
                "Real-time leaderboards with configurable ranking metrics",
                "Ticketed escalation routing for plan/incentive disputes",
                "Mobile app - earnings breakdown, plan tracking, in-app redemption",
            ],
            "third_party_validation": "no Compass-specific G2/Gartner rating found - use the company-wide figure instead: 4.7 G2 rating",
        },
        "Loyalife": {
            "pain_summary": "Loyalty is generic (points + tiers). Low engagement, churn on redemption, no brand differentiation.",
            "proof_keywords": "churn reduction %, redemption rate lift, member engagement %, CLTV impact",
            "cta_style": "case study or benchmarking call",
            "global_framing": "a global customer loyalty company",
            "why_product": "Unifies programs, rewards, engagement, and member data so enterprises can launch and manage omnichannel loyalty programs without stitching together fragmented tools - built around actionable AI.",
            "key_features": [
                "Loyalty Programs - multi-brand, channel, influencer, omnichannel, coalition models",
                "Member Management - built-in CDP with 360-degree member profiles",
                "Rule Engine - earn, burn, and eligibility logic with governed conditions",
                "Member Engagement toolset - segments, tiers, campaigns, gamification, referrals",
                "Loyalty Rewards - points, cards, digital wallet, location/scan/claim-based rewards",
                "Reports & Insights - real-time and AI-powered analytics dashboard",
                "Anomaly detection and maker-checker governance for fraud prevention",
                "White-labeled mobile app and verified WhatsApp bot for redemption",
            ],
            "third_party_validation": "no Loyalife-specific G2/Gartner rating found - use the company-wide figure instead: 4.7 G2 rating. (Loyalife does have real enterprise customers - CBI, Mutual Trust Bank, Ola Energy, TBO Holidays - but per the no-real-client-names rule, still anonymize as 'a global banking/energy/travel client' rather than naming them.)",
        },
    }

    SENIORITY_ANGLES = {
        "C-Suite": "board optics, retention as strategic narrative, headcount/cost recovery, long-term ROI",
        "VP/Director": "proving ROI upward to leadership, reducing manual work, adoption and speed",
        "Director/Manager": "day-to-day friction, tool consolidation, team adoption, speed-to-execution",
    }

    @classmethod
    def build_prompt(cls, sample_leads: list[dict], persona_summary: str, product: str, seniority: str) -> str:
        """Build the HUMANVOICE ready-to-use prompt with persona context."""

        product_angle = cls.PRODUCT_ANGLES.get(product, {})
        seniority_angle = cls.SENIORITY_ANGLES.get(seniority, "ROI and adoption")

        return f"""Generate a 12-email outbound sequence + a mirrored 12-message LinkedIn sequence for:
{persona_summary}

Product: {product}
Introduce it as: {product_angle.get('global_framing', 'a global company in this category')}
Pain point: {product_angle.get('pain_summary', 'See relevant doc')}
Proof style (for this seniority): {seniority_angle}
One-line CTA style: {product_angle.get('cta_style', 'soft ask')}

why_product (ground email 2 in this, don't just restate it):
{product_angle.get('why_product', 'See relevant doc')}

key_features (email 3 picks 2-3 of these most relevant to this persona):
{json.dumps(product_angle.get('key_features', []), indent=2)}

third_party_validation (email 5 uses this real figure - never invent a number):
{product_angle.get('third_party_validation', 'No verified figure available - do not invent one, mention credibility another way')}

Sample leads (for tone/context, not exhaustive):
{json.dumps(sample_leads, indent=2, default=str)}

{cls.HUMANVOICE_RULES}

Return ONLY valid JSON, no markdown:
{{
  "email_sequences": [
    {{"step": 1, "delay_days": 0, "subject": "...", "body": "<p>...</p>"}},
    ... (steps 1 through 12)
  ],
  "linkedin_sequences": [
    {{"step": 1, "action": "Profile visit", "message": null}},
    ... (steps 1 through 12)
  ]
}}
"""

    @staticmethod
    def build_persona_summary(detected: dict) -> str:
        """Build a one-liner persona summary for the prompt."""
        return f"{detected['persona_type']} at {detected['size_category']} company, {detected['vertical']} vertical, {detected['use_case']}"


# ============================================================================
# MAIN COPY AGENT
# ============================================================================

def is_configured() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _lead_brief(row: dict) -> dict:
    """Extract brief lead info for sample context."""
    return {
        "first_name": row.get("first_name"),
        "company": row.get("organization_name") or row.get("company_name") or row.get("search_company"),
        "title": row.get("title"),
        "industry": row.get("industry"),
        "linkedin_signal": row.get("personalized_line") or None,
    }


def generate_copy(
    lead_count: int,
    sample_leads: list[dict],
    persona_detected: dict,
) -> dict:
    """Generate 5-step email + LinkedIn sequence using HUMANVOICE + persona context."""
    client = Anthropic()

    # Build persona summary and select product
    persona_summary = HumanVoicePromptBuilder.build_persona_summary(persona_detected)
    product = persona_detected.get("primary_product", "Empuls")
    seniority = persona_detected.get("seniority", "VP/Director")

    # Build prompt with HUMANVOICE rules + persona context
    prompt = HumanVoicePromptBuilder.build_prompt(sample_leads, persona_summary, product, seniority)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,  # 12 emails + 12 LinkedIn messages, up from 5+5 - 3000 would truncate
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Extract JSON from response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            logger.error(f"No JSON found in response: {text[:200]}")
            return {"status": "parse_error", "message": "Claude response not in JSON format"}

        copy = json.loads(text[json_start:json_end])
        return {
            "status": "done",
            "lead_count": lead_count,
            "persona_detected": persona_detected,
            "copy": copy,
        }
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return {"status": "parse_error", "message": str(e)}
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return {"status": "error", "message": str(e)}


def run(df: pd.DataFrame, persona_hints: Optional[dict] = None) -> dict:
    """Best-effort copy generation. Returns a status dict. Never raises into caller."""
    if not is_configured():
        return {"status": "not_configured", "message": "ANTHROPIC_API_KEY not set - Copy Agent skipped."}

    if df.empty or "email" not in df.columns:
        return {"status": "no_leads", "message": "No enriched contacts to generate copy for."}

    rows = [
        r
        for r in df.to_dict("records")
        if str(r.get("email") or "").strip().lower() not in ("", "nan", "none")
    ]
    if not rows:
        return {"status": "no_leads", "message": "No leads with an email to generate copy for."}

    try:
        # Detect persona from lead attributes
        first_lead = rows[0]
        detected = PersonaDetector.detect_persona(
            title=first_lead.get("title"),
            company_size=first_lead.get("employee_count"),
            industry=first_lead.get("industry"),
        )

        # Override with explicit hints if provided
        if persona_hints:
            detected.update(persona_hints)

        # Sample leads for tone context
        sample = [_lead_brief(r) for r in rows[:_SAMPLE_SIZE]]

        # Generate copy
        result = generate_copy(len(rows), sample, detected)
        return result

    except Exception as e:
        logger.exception(f"Copy Agent failed: {e}")
        return {"status": "error", "message": f"Copy Agent failed: {e}"}


def build_markdown(campaign_title: str, result: dict) -> str:
    """Build markdown output of copy result."""
    if result["status"] != "done":
        return f"# Copy Agent - {campaign_title}\n\n{result.get('message', result['status'])}\n"

    persona = result.get("persona_detected", {})
    lines = [
        f"# Copy Agent - {campaign_title}",
        f"\n**Detected Persona:** {persona.get('persona_type')} | {persona.get('size_category')} | {persona.get('vertical')}",
        f"**Product Angle:** {persona.get('primary_product')} - {persona.get('use_case')}",
        f"\n{result['lead_count']} lead(s)",
        "",
    ]

    seq = result["copy"]
    for email in seq.get("email_sequences", []):
        lines.append(f"\n## Step {email['step']} (day {email['delay_days']})")
        lines.append(f"**Subject:** {email['subject']}")
        lines.append(f"\n**Body:**\n{email['body']}")

    li = seq.get("linkedin_sequences", [])
    if li:
        lines.append("\n**LinkedIn Cadence:**")
        for step in li:
            action_str = f"- Day {step.get('day', step.get('step'))}: {step['action']}"
            if step.get("message"):
                action_str += f" - {step['message']}"
            lines.append(action_str)

    return "\n".join(lines)
