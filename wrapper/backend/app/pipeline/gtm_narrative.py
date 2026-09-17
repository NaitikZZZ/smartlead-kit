"""Best-effort qualitative GTM account profile - value proposition, problem
solved, benefits, ICP industry/persona, distribution model, named partners,
workforce composition, loyalty/gamification fit, a rep-facing GTM summary,
and product-to-pitch. This is the in-pipeline port of the standalone
scripts/gtm_research_fields.py (see that file for the original build notes
and prompt-design reasoning) - duplicated rather than imported because
wrapper/backend deploys standalone to Vercel and can't reach outside its own
directory, same reason gtm_enrichment.py duplicates apollo_gtm_columns.py's
matching logic instead of importing it.

Runs automatically for every account, right after gtm_enrichment.enrich() in
runner.py - never blocks the run on failure (same best-effort contract as
gtm_enrichment.py and web_completeness.py).

Backend precedence per company:
  1. Local Claude Code CLI ($CLAUDE_CODE_EXECPATH) - free, user's own subscription.
  2. Direct Anthropic API (config.ANTHROPIC_API_KEY) - paid, the same
     fallback web_completeness.py already uses.
Never calls Apollo's paid AI Research field, or any other paid Apollo
endpoint - the only Apollo/HubSpot involvement is reading whatever's already
on the row (industry, employee count, competitor/partner/dream-account
columns gtm_enrichment.py just computed) and handing it to Claude as
grounding context, same technique gtm_research_fields.py already used for
partner_tech_match.

Caching: one Redis key per company domain (cache:gtm_narrative:<domain>), no
TTL - like the competitor-list and company-domain caches elsewhere in this
app, these are slow-changing facts refreshed manually, not on a timer. A
cache hit costs nothing: no Apollo, no Claude, no web search. If Redis isn't
configured, research still runs but nothing persists across runs (best-effort,
matches this pipeline's usual resilience contract).

Cost safeguard: if more than config.GTM_NARRATIVE_CONFIRM_THRESHOLD companies
on a sheet aren't already cached, the run pauses (via runner.ask()) and
confirms before spending a live Claude+web-search call on each one - same UX
pattern as the "no company column" / "scrape truncated" confirmations
elsewhere in runner.py.

=== AWS Bedrock was evaluated and rejected (2026-09-17) - do not re-add ===
A Bedrock backend (bearer-token auth via a dedicated GTM_ENRICHMENT_BEDROCK_
API_KEY, raw `requests` call to bedrock-runtime's InvokeModel) was built and
live-tested end to end. Auth worked fine once the key was correctly
formatted. But the actual research call fails hard and permanently: Bedrock's
InvokeModel validates `tools[].type` against a fixed allow-list
(`bash_20250124`, `custom`, `text_editor_20250124/20250429/20250728`) that
does not include `web_search_20250305` - confirmed via a real 400 response
naming exactly that allow-list. Anthropic's web-search tool is executed by
Anthropic's own backend infrastructure; Bedrock-hosted inference doesn't
proxy to it. This is a hard platform limitation, not a version/config
mistake - don't re-attempt this without a fundamentally different approach
(e.g. implementing search yourself as a Bedrock `custom` tool against a
separate search API, a materially bigger build the user explicitly deferred
2026-09-17). The GTM_ENRICHMENT_BEDROCK_API_KEY/MODEL_ID/AWS_REGION config
vars were removed along with this code - see git history if reviving this.
"""
from __future__ import annotations
import json
import os
import re
import subprocess

from .._lazy import pd

from .. import config, redis_cache
from . import web_completeness
from .gtm_enrichment import normalize_domain

NEW_COLUMNS = [
    "gtm_value_proposition", "gtm_problem_solved", "gtm_product_benefits",
    "gtm_icp_industry", "gtm_icp_persona", "gtm_distribution_model",
    "gtm_named_partners", "gtm_workforce_composition",
    "gtm_loyalty_gamification_fit", "gtm_summary", "gtm_product_to_pitch",
]

MODEL = "claude-sonnet-4-5"
CLI_TIMEOUT = 180
_CACHE_PREFIX = "cache:gtm_narrative:"

# Same static Xoxoday product framework as scripts/gtm_research_fields.py -
# own material, safe to embed directly rather than treat as something to
# "research".
PRODUCT_FRAMEWORK = """Xoxoday sells four products:
- Plum: rewards/incentives payout API, 10M+ reward catalog across 175+ countries. Fits any team running rewards/incentive programs (marketing, HR, sales ops, CX, research) - self-serve, API-first, strong for multi-country or consumer/channel-facing use cases.
- Empuls: employee recognition, rewards and engagement for HR/People teams at 200+ FTE companies - sales-led.
- Compass: sales commission and incentive automation for Sales Ops/RevOps/Finance teams with a distributed or channel sales force.
- Loyalife: enterprise customer or channel loyalty programs for consumer or B2B2C brands with repeat-purchase customers - sales-led, longer cycle."""

_SIGNAL_COLUMNS = [
    ("competitor_match", "Competitor Match"), ("competitor_name", "Competitor Name"),
    ("competitor_threat", "Competitor Threat"), ("partner_tech_match", "Partner Tech Match"),
    ("partner_suggested_products", "Partner Suggested Products"),
    ("dream_account", "Is Dream Account 2026"),
]


def _cache_key(domain: str) -> str:
    return f"{_CACHE_PREFIX}{domain}"


def _load_cached(domain: str) -> dict | None:
    try:
        return redis_cache.get_json(_cache_key(domain))
    except Exception:
        return None


def _store_cache(domain: str, profile: dict) -> None:
    try:
        redis_cache.set_json(_cache_key(domain), profile)
    except Exception:
        pass  # best-effort - a failed cache write must never fail the run


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("yes", "y", "true", "1")


def _known_signals(row) -> dict:
    """Pulls whatever's already free on the row (from gtm_enrichment.py's
    columns, plus Industry/Employee if web_completeness already filled them)
    so the prompt below never asks Claude to re-derive something already on
    file - grounding, not a research shortcut."""
    signals: dict = {}
    for key, col in _SIGNAL_COLUMNS:
        if col in row.index:
            v = row.get(col)
            if v not in (None, "", "No") and not (isinstance(v, float) and pd.isna(v)):
                signals[key] = v
    industry_col = web_completeness._find_col(row.index, web_completeness.INDUSTRY_CANDIDATES)
    if industry_col and row.get(industry_col) not in (None, ""):
        signals["industry"] = row.get(industry_col)
    employee_col = web_completeness._find_col(row.index, web_completeness.EMPLOYEE_CANDIDATES)
    if employee_col and row.get(employee_col) not in (None, ""):
        signals["employee_count"] = row.get(employee_col)
    return signals


def _build_prompt(company_name: str, domain: str, signals: dict) -> str:
    lines = []
    if signals.get("partner_tech_match") and signals.get("partner_suggested_products"):
        lines.append(
            f"Xoxoday's own CRM records a real signal for this company: its technology stack includes confirmed "
            f"Xoxoday integration/channel partners ({signals['partner_tech_match']}), and Xoxoday's own GTM "
            f"playbook records that {signals['partner_suggested_products']} is the product actually pitched "
            f"through those specific partner relationships. Treat this as a strong, recorded fact - weigh it "
            f"alongside (not instead of) the sales-org/channel/workforce signals you find below."
        )
    if signals.get("competitor_match") == "Yes":
        lines.append(
            f"This company already appears on Xoxoday's competitor list as "
            f"{signals.get('competitor_name') or 'a named competitor'} "
            f"(threat: {signals.get('competitor_threat') or 'unrecorded'}) - factor this into gtm_summary."
        )
    if signals.get("dream_account"):
        lines.append("This is a flagged 2026 dream account for Xoxoday's ABM program.")
    if signals.get("industry"):
        lines.append(f"Known industry (from CRM data - don't spend web-search budget re-deriving this): {signals['industry']}.")
    if signals.get("employee_count"):
        lines.append(f"Known employee count (from CRM data - don't spend web-search budget re-deriving this): {signals['employee_count']}.")
    known_block = (
        "\n\nKnown facts already on file (weigh these alongside what you find, don't re-research them):\n"
        + "\n".join(f"- {l}" for l in lines)
    ) if lines else ""

    return f"""You are a B2B GTM research analyst. Research the company "{company_name}" \
(website: {domain}) using web search: its homepage, product/solutions pages, pricing page, \
about/company page, careers/jobs page, and its LinkedIn page.

{PRODUCT_FRAMEWORK}{known_block}

Return ONLY a JSON object with these exact keys (use "Not found" for anything you can't \
confidently determine from real sources - never invent specifics):
- "value_proposition": what the company sells and its core value proposition, 1-2 sentences.
- "problem_solved": the primary problem/pain point their product solves, 1 sentence.
- "product_benefits": top 3 concrete benefits/outcomes their product claims, comma-separated.
- "icp_industry": the industries and company sizes they primarily sell into, 1 sentence.
- "icp_persona": the job titles/functions of their target buyer, 1 sentence.
- "distribution_model": how they go to market - direct sales, self-serve/API-first, channel \
partners, dealers/resellers, marketplace, or a mix, 1-2 sentences.
- "named_partners": any specific partners, dealers, resellers, or influencer programs \
mentioned by name, comma-separated, or "None found".
- "workforce_composition": evidence of white-collar/office vs blue-collar/frontline staff, \
citing where you found it (careers page, job listings, LinkedIn, news), 1 sentence.
- "loyalty_gamification_fit": one sentence on whether this company's own end customers show \
repeat-purchase/recurring-engagement behavior a loyalty/gamification program could be built \
on, ending with exactly one word: HIGH, MEDIUM, LOW, or UNCLEAR.
- "gtm_summary": a 3-4 sentence GTM briefing paragraph for a Xoxoday rep about to reach out - \
what they sell, who they sell to, how they go to market, any workforce signal. Plain prose.
- "product_to_pitch": exactly one of Plum, Empuls, Loyalife, Compass, Multiple, or Unclear - \
the best-fit Xoxoday product(s) for THIS company as a Xoxoday customer.

Before answering product_to_pitch, you MUST explicitly check for all of these signals \
(don't skip straight to Empuls just because a company has no obvious blue-collar workforce) - \
search their careers page / job listings for evidence of each:
1. A dedicated quota-carrying sales org (titles like "Account Executive", "Regional Sales \
   Manager", "Sales Development Rep", territory/quota language, CRM mentions like Salesforce) \
   -> this is a Compass (sales commission automation) signal, not just Empuls.
2. A distributor, reseller, wholesaler, franchise, or dealer network (per-order/per-unit \
   channel sales, "distributor", "channel partner") -> this is a Plum (channel incentives) or \
   Loyalife (channel loyalty) signal.
3. A B2C or B2B2C customer base with repeat purchases (subscriptions, repeat transactions, \
   existing points/rewards program) -> this is a Loyalife signal.
4. General employee headcount/engagement need (200+ FTE, no other signal) -> Empuls.
If 2 or more signals apply, answer "Multiple" and name which products in \
gtm_summary. Only answer a single product when just one signal clearly applies.

Output the JSON object and nothing else - no markdown fences, no commentary."""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _research_via_cli(prompt: str) -> str:
    """Same mechanism as scripts/gtm_research_fields.py and
    wrapper/backend/app/pipeline/web_scrape.py's _extract_via_cli - uses the
    user's own Claude account/subscription, no API credits spent."""
    execpath = os.environ.get("CLAUDE_CODE_EXECPATH")
    proc = subprocess.run(
        [execpath, "-p", prompt, "--allowedTools", "WebFetch,WebSearch"],
        capture_output=True, text=True, timeout=CLI_TIMEOUT,
    )
    out = (proc.stdout or "").strip()
    if "Not logged in" in out or (proc.returncode != 0 and not out):
        raise ValueError(f"Claude CLI call failed (exit {proc.returncode}): {(proc.stderr or '')[:300]}")
    return out


def _research_via_api(prompt: str) -> str:
    """Same fallback web_completeness.py already uses."""
    from anthropic import Anthropic
    client = Anthropic(api_key=config.require("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY))
    response = client.messages.create(
        model=MODEL, max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text")


def research_company(company_name: str, domain: str, signals: dict) -> dict:
    prompt = _build_prompt(company_name, domain, signals)
    if os.environ.get("CLAUDE_CODE_EXECPATH"):
        text = _research_via_cli(prompt)
    elif config.ANTHROPIC_API_KEY:
        text = _research_via_api(prompt)
    else:
        raise ValueError(
            "No research backend available - need CLAUDE_CODE_EXECPATH or ANTHROPIC_API_KEY set."
        )
    data = _extract_json(text)
    return {
        "gtm_value_proposition": data.get("value_proposition", ""),
        "gtm_problem_solved": data.get("problem_solved", ""),
        "gtm_product_benefits": data.get("product_benefits", ""),
        "gtm_icp_industry": data.get("icp_industry", ""),
        "gtm_icp_persona": data.get("icp_persona", ""),
        "gtm_distribution_model": data.get("distribution_model", ""),
        "gtm_named_partners": data.get("named_partners", ""),
        "gtm_workforce_composition": data.get("workforce_composition", ""),
        "gtm_loyalty_gamification_fit": data.get("loyalty_gamification_fit", ""),
        "gtm_summary": data.get("gtm_summary", ""),
        "gtm_product_to_pitch": data.get("product_to_pitch", ""),
    }


CONFIRM_PROMPT_TEMPLATE = (
    "{uncached} companies on this sheet don't have a cached GTM profile yet - each needs a live "
    "Claude + web-search call (real cost, separate from Apollo/HubSpot). {cached} others are already "
    "cached and free. Run research on all {uncached} now? (No = use only the cached profiles, leave the rest blank.)"
)


def plan_research(df, domain_col: str = "Domain") -> dict:
    """Cache-only lookup (no research, no external calls beyond Redis) -
    lets a caller decide whether to ask for confirmation BEFORE spending
    anything, using its own ask mechanism (sync for runner.py, async
    step.wait_for_event for inngest_runner.py). Returns
    {row_domain, cached, uncached, cache_configured} - feed straight into
    run_research() once the go/no-go decision (if any) is made."""
    row_domain = {idx: normalize_domain(row.get(domain_col, "")) for idx, row in df.iterrows()}
    cache_ok = redis_cache.is_configured()
    unique_domains = sorted({d for d in row_domain.values() if d})
    cached: dict[str, dict] = {}
    uncached: list[str] = []
    for d in unique_domains:
        hit = _load_cached(d) if cache_ok else None
        if hit:
            cached[d] = hit
        else:
            uncached.append(d)
    return {"row_domain": row_domain, "cached": cached, "uncached": uncached, "cache_configured": cache_ok}


def run_research(df, plan: dict, company_col: str = "Company") -> tuple:
    """Does the actual per-company research for plan['uncached'] (empty list
    if the caller declined/skipped the confirmation) and fills in the 11
    gtm_* columns for every row plan['cached'] or freshly-researched covers.
    Returns (df, stats). Never raises - failures are per-company
    (stats['errors']), matching gtm_enrichment.enrich's contract."""
    out = df.copy()
    for c in NEW_COLUMNS:
        if c not in out.columns:
            out[c] = ""

    row_domain = plan["row_domain"]
    cached = plan["cached"]
    uncached = plan["uncached"]
    cache_ok = plan["cache_configured"]

    stats = {
        "skipped": False, "cache_configured": cache_ok,
        "total_accounts": len(out), "unique_domains": len(cached) + len(uncached),
        "cache_hits": len(cached), "needs_research": len(uncached),
        "researched": 0, "declined": False, "errors": [],
    }

    fresh: dict[str, dict] = {}
    for d in uncached:
        match_idx = next((idx for idx, dm in row_domain.items() if dm == d), None)
        if match_idx is None:
            continue
        row = out.loc[match_idx]
        company_name = row.get(company_col) if company_col in out.columns else None
        company_name = str(company_name).strip() if company_name not in (None, "") else d
        try:
            facts = research_company(company_name, d, _known_signals(row))
            fresh[d] = facts
            if cache_ok:
                _store_cache(d, facts)
            stats["researched"] += 1
        except Exception as e:
            stats["errors"].append(f"{company_name} ({d}): {e}")

    all_profiles = {**cached, **fresh}
    for idx, d in row_domain.items():
        profile = all_profiles.get(d)
        if not profile:
            continue
        for col in NEW_COLUMNS:
            if profile.get(col):
                out.at[idx, col] = profile[col]

    stats["errors"] = stats["errors"][:10]
    return out, stats


def enrich(df, domain_col: str = "Domain", company_col: str = "Company",
           run_id: str | None = None, ask_fn=None):
    """Sync convenience wrapper around plan_research()/run_research() for a
    caller with a synchronous ask() (runner.py's legacy engine). Adds the 11
    gtm_* narrative columns to df (a copy). Returns (df, stats). `run_id`/
    `ask_fn` are runner.py's job id and its `ask()` function - pass both to
    get the cost-safeguard confirmation prompt when the sheet has a lot of
    uncached companies; omit either to just run without asking (caller has
    already opted in via the enable toggle).

    inngest_runner.py (the actual live engine for CSV/campaign_idea runs)
    does NOT use this wrapper - it calls plan_research()/run_research()
    directly so the confirmation can go through its own async `_ask()`
    (step.wait_for_event), which this sync function can't call into."""
    if not config.GTM_NARRATIVE_ENRICHMENT_ENABLED:
        return df, {"skipped": True, "reason": "GTM_NARRATIVE_ENRICHMENT_ENABLED=false", "researched": 0}
    if domain_col not in df.columns:
        return df, {"skipped": True, "reason": f"no {domain_col!r} column present", "researched": 0}

    plan = plan_research(df, domain_col)
    declined = False
    if plan["uncached"] and len(plan["uncached"]) > config.GTM_NARRATIVE_CONFIRM_THRESHOLD:
        if run_id and ask_fn:
            answer = ask_fn(
                run_id, "gtm_narrative_confirm", "yes_no",
                CONFIRM_PROMPT_TEMPLATE.format(uncached=len(plan["uncached"]), cached=len(plan["cached"])),
                default="yes",
                context={"step": "gtm_narrative", "needs_research": len(plan["uncached"]), "cached": len(plan["cached"])},
            )
            if not _truthy(answer):
                declined = True
                plan["uncached"] = []
        # else: no interactive loop available to this caller - proceed, since
        # the caller already opted in by leaving the enable toggle on.

    out, stats = run_research(df, plan, company_col)
    stats["declined"] = declined
    return out, stats
