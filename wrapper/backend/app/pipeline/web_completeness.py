"""Best-effort completeness fill via an LLM with web search (Anthropic).

Only fills gaps in columns that already exist on the sheet (Domain/Website,
Industry, Employee count) - never invents new columns. Skipped entirely if
ANTHROPIC_API_KEY isn't configured, or if the API call fails for any reason -
this is a nice-to-have gap-filler, not a required stage, so a failure here
should never take down the run.

Each person running this backend uses their own ANTHROPIC_API_KEY in their
own local .env (this is per-instance config, not shared/embedded) - keyless
web search (DuckDuckGo scraping, their Instant-Answer API) was evaluated and
doesn't work reliably: scraping hits an immediate bot-challenge wall, and the
Instant-Answer API has no useful coverage for company lookups.
"""
from __future__ import annotations
import json
import re

import pandas as pd

from .. import config

DOMAIN_CANDIDATES = ["domain", "website", "company domain", "website domain", "url"]
INDUSTRY_CANDIDATES = ["industry", "sector"]
EMPLOYEE_CANDIDATES = ["employee", "employees", "headcount", "company size", "employee size", "employee count"]


def _find_col(columns, candidates):
    lower_map = {c.strip().lower(): c for c in columns}
    for cand in candidates:
        for header, original in lower_map.items():
            if cand == header or cand in header:
                return original
    return None


def _is_blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def _client():
    from anthropic import Anthropic
    return Anthropic(api_key=config.require("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY))


def _lookup_company_facts(client, company_name: str, missing_fields: list[str]) -> dict:
    fields_desc = ", ".join(missing_fields)
    prompt = (
        f"Find these facts about the company \"{company_name}\" using web search: {fields_desc}. "
        f"Reply with ONLY a JSON object with keys from this exact set: "
        f"{missing_fields}. Use null for any fact you can't confidently find - never guess. "
        f"For 'domain' give the bare company domain (e.g. acme.com, no https:// or www.). "
        f"For 'employees' give a plain number (estimate is fine). For 'industry' give a short "
        f"industry label (e.g. 'Banking', 'SaaS')."
    )
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def fill_completeness_gaps(df: pd.DataFrame, company_col: str):
    """Returns (df, stats). Best-effort - never raises; on any failure it
    just returns the original df with a note explaining why nothing changed."""
    if not config.ANTHROPIC_API_KEY:
        return df, {"skipped": True, "reason": "ANTHROPIC_API_KEY not configured", "filled": 0}

    domain_col = _find_col(df.columns, DOMAIN_CANDIDATES)
    industry_col = _find_col(df.columns, INDUSTRY_CANDIDATES)
    employee_col = _find_col(df.columns, EMPLOYEE_CANDIDATES)
    field_map = {"domain": domain_col, "industry": industry_col, "employees": employee_col}
    tracked = {k: v for k, v in field_map.items() if v}

    if not tracked:
        return df, {"skipped": True, "reason": "no Domain/Industry/Employee columns present to complete", "filled": 0}

    try:
        client = _client()
    except Exception as e:
        return df, {"skipped": True, "reason": str(e), "filled": 0}

    out = df.copy()
    filled = 0
    errors = []
    for i, row in out.iterrows():
        missing = [k for k, col in tracked.items() if _is_blank(row.get(col))]
        if not missing:
            continue
        try:
            facts = _lookup_company_facts(client, str(row[company_col]), missing)
        except Exception as e:
            errors.append(f"{row[company_col]}: {e}")
            continue
        for k, v in facts.items():
            col = tracked.get(k)
            if col and v not in (None, ""):
                out.at[i, col] = v
                filled += 1

    return out, {"skipped": False, "filled": filled, "fields_tracked": list(tracked.keys()), "errors": errors[:10]}
