"""Inngest-native run engine (Phase 5) - full conversion of runner.py's
_execute() (input through HubSpot import) plus run_confirmed_import() into
ONE continuous function: input (CSV, or a HubSpot Project - either with a CSV
attached, a linked webpage list auto-scraped, or a linked list fetched
directly) -> normalize -> domain resolution (gated) -> exclusion check
(gated) -> people discovery (gated, auto-skipped if named contacts are
already present) -> email reveal & validation (existing-contact fill vs.
discovered-candidate reveal) -> mobile phone (gated) -> completeness fill
(gated) -> output files & name (campaign title ask, writes to Vercel Blob,
optional GitHub PR) -> associations (multi-select, HubSpot dropdown or
manual entry) -> preview & upload (waits indefinitely for a "confirm_import"
run/answer instead of the separate synchronous /import HTTP endpoint
runner.py uses) -> HubSpot import + HeyReach push + Copy Agent -> done.

A HubSpot Project with no linked list at all raises a clear "not supported
yet, upload a CSV" error instead of the Apollo-search-from-campaign-idea flow
(product/use-case extraction via Claude, ICP mapping, an unbounded "add more
prospects" loop) - that flow is ALSO currently broken on the legacy engine
(calls domain_resolution.resolve_domains, which doesn't exist), so nothing
regresses by not porting it; it can be built as its own slice later.

The webpage-scrape path's resume/dedup cache (web_scrape.py's
_load_scrape_cache/_save_scrape_cache) is still a local JSON file, not
migrated to Redis like the other 6 caches were in Phase 2 - on Vercel this
means the "continue from record #501" behavior silently degrades to
"start over," a known gap, not something this port introduces.

Built as a separate, parallel function alongside the still-fully-working
thread-based runner.py - routes/runs.py's dual-dispatch still exists as a
safety net, but create_run now sends every input_source to this engine. Each
stage was verified against the local Inngest Dev Server before the next was
added, per the incremental "one verified slice at a time" approach. The final
confirm-import -> HubSpot-write stretch was verified by static review only
(reaching the pause, and the code path itself) - actually firing it end-to-end
would create real HubSpot contacts/lists, which this session does not do.

Steps with real cost or non-determinism (Blob fetch, the Apollo/Clearbit
domain lookup) are wrapped in step.run(), same as pure/cheap/deterministic
pandas transforms (column guessing, normalization, dedup) run as plain code -
safe to recompute on every replay, since Inngest re-runs the whole function
body on each resume and only memoizes step.run() results.

Every run_status write is ALSO wrapped in its own step.run() (via the
_status()/_set_step() helpers below), even though a Redis write is cheap and
idempotent in isolation - confirmed live against the Dev Server that Inngest
re-invokes this function once per completed step (not once total), replaying
all bare code up to the next not-yet-done step on each invocation. A bare
run_status call sitting before a wait_for_event therefore refires on every
one of those replays and was observed to stomp the "awaiting_answer" stage a
memoized step had already set a moment earlier - stage stayed "normalizing"
forever even with a pending question live. Wrapping every write in a step
makes it fire exactly once, in true causal order, no matter how many replay
invocations occur.

The 02_domain_resolution.csv download (surfaced after People Discovery in
runner.py, purely so a user can start manual lookups while the rest of a run
continues) is the one output file still not written here - it's a nice-to-
have, not load-bearing, and can be added without touching anything else.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import json
import math
import re

import inngest
import pandas as pd
from anthropic import Anthropic

from .. import config, run_status, vercel_blob
from ..inngest_client import client
from . import (
    apollo_enrich, association_resolve, copy_agent, domain_resolution, estimates,
    github_pr, heyreach, hubspot_exclusion, hubspot_import, icp_mapper, input_sources,
    naming, normalize, outputs, web_completeness, web_scrape,
)
from .runner import COUNTRY_OPTIONS, REGION_OPTIONS, _map_existing_contact_columns


def _guess_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for cand in candidates:
        for header, original in lower_map.items():
            if cand.lower() in header:
                return original
    return None


def _blank_domain_mask(df: pd.DataFrame) -> pd.Series:
    if "Domain" not in df.columns:
        return pd.Series([True] * len(df), index=df.index)
    return df["Domain"].isna() | (df["Domain"].astype(str).str.strip() == "")


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("yes", "true", "y", "1")


_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/\s]+\.[a-z]{2,})(?:/.*)?$", re.I)


def _parse_company_names(raw: str) -> list[str]:
    """Splits a free-text company list on commas/semicolons/newlines when
    present; falls back to whitespace-splitting for pasted space-separated
    lists (e.g. a block of URLs). Any entry that looks like a URL/domain is
    reduced to its bare hostname (e.g. "https://hootsuite.com/products/x" ->
    "hootsuite.com") since that resolves far better than the raw URL through
    the Clearbit/Apollo company lookup pipeline."""
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,\n;]+", raw) if re.search(r"[,\n;]", raw) else raw.split()
    names = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = _URL_RE.match(p)
        names.append(m.group(1).lower() if m else p)
    return names


_EMPLOYEE_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:-|,|to)\s*(\d+)\s*$|^\s*(\d+)\s*\+\s*$", re.I)


def _normalize_employee_size_labels(labels: list[str]) -> list[str] | None:
    """Maps checkbox labels (e.g. "51-100") to Apollo's "min,max" range
    format via config.EMPLOYEE_SIZE_BUCKETS, and best-effort parses any
    free-text "Other" entry the user typed (e.g. "50-200", "500+") into the
    same format. Anything unparseable is dropped rather than sent to Apollo
    malformed - it would just be silently ignored there anyway."""
    bucket_map = dict(config.EMPLOYEE_SIZE_BUCKETS)
    ranges = []
    for label in labels or []:
        if label in bucket_map:
            ranges.append(bucket_map[label])
            continue
        m = _EMPLOYEE_RANGE_RE.match(label)
        if not m:
            continue
        if m.group(3):
            ranges.append(f"{m.group(3)},")
        else:
            ranges.append(f"{m.group(1)},{m.group(2)}")
    return ranges or None


def _targeting_from_wizard(wizard_targeting: dict):
    """The campaign-idea wizard lets the user confirm job titles/employee
    size/regions themselves before ever hitting Start - when that happened,
    there's nothing left to infer or re-confirm, so callers skip
    _extract_and_confirm_icp (no Claude call, no icp_confirm_form ask) and
    use this directly. Returns (persona_titles, person_locations,
    employee_ranges, exact_titles, organization_locations) - the first three
    the same shape _extract_and_confirm_icp returns; exact_titles is True
    unless the wizard's "include similar/lookalike titles" box was checked.
    organization_locations is the separate company-HQ location filter (city/
    state/country free text) for "HQ based" use cases - distinct from
    person_locations, which filters by where the contact themselves sits."""
    job_titles = [t.strip() for t in (wizard_targeting.get("job_titles") or []) if str(t).strip()]
    regions = [r.strip() for r in (wizard_targeting.get("regions") or []) if str(r).strip()]
    employee_ranges = _normalize_employee_size_labels(wizard_targeting.get("employee_sizes") or [])
    exact_titles = not bool(wizard_targeting.get("include_lookalikes"))
    org_locations = [r.strip() for r in (wizard_targeting.get("organization_locations") or []) if str(r).strip()]
    return job_titles or None, regions or None, employee_ranges, exact_titles, org_locations or None


def _company_names_from_wizard(wizard_targeting: dict) -> list[str]:
    """Same deal as _targeting_from_wizard, for the no-CSV path's target
    companies - if the wizard's review step already collected them, the
    mid-run "company names to search" ask below is skipped entirely instead
    of re-asking for something the user already gave. Routed through
    _parse_company_names so a pasted URL still gets reduced to a bare
    hostname the same way a runtime answer would."""
    names = wizard_targeting.get("company_names") or []
    return _parse_company_names("\n".join(str(n) for n in names))


def _read_csv_blob(csv_blob_pathname: str, csv_filename: str) -> pd.DataFrame:
    """Reads an uploaded CSV blob into a DataFrame.

    Deliberately NOT wrapped in step.run(): Inngest memoizes step outputs by
    serializing them, and it caps that payload ("output_too_large: Your
    function's response body exceeds the maximum size limit"). Returning a
    whole CSV as a step output blew up on a real 11.7MB Apollo export - the
    run failed at reading_input even though the upload itself succeeded.

    Skipping memoization is safe here precisely because a blob read is a pure,
    idempotent read of immutable storage: every replay re-reads the same bytes
    and rebuilds the same df, which is exactly what the memoized version did
    anyway (only csv_text was ever cached - df was always rebuilt per replay).
    The tradeoff is re-downloading per replay instead of per run."""
    blob_bytes = vercel_blob.get(vercel_blob.url_for(csv_blob_pathname))
    return input_sources.read_csv_bytes(blob_bytes, csv_filename)


def _nan_safe(o):
    """Recursively replaces non-finite floats (NaN/Infinity) with None.
    EVERY step.run() handler that returns data derived from a DataFrame (via
    to_dict("records")) MUST pass its return value through this - confirmed
    live, on a real run against real user data, that Python's json module
    happily emits bare NaN/Infinity tokens (not valid JSON), and Inngest's
    Go-based server rejects them outright: "invalid character 'N' looking
    for beginning of value" - which then wedges that run indefinitely and,
    worse, pegs the whole backend's single event loop as Inngest retries."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _nan_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_nan_safe(v) for v in o]
    return o


def _job_change_indices(df: pd.DataFrame) -> set:
    """Rows flagged as a job change (from a 'Job change' / 'Started role last N
    months' / similar column). These MUST bypass the email/phone cache since
    the person's old work data is stale for their new company."""
    col = None
    for c in df.columns:
        h = str(c).strip().lower()
        if "job change" in h or "started role" in h or "recently changed job" in h:
            col = c
            break
    if col is None:
        return set()
    idx = set()
    for i, v in df[col].items():
        s = str(v).strip().lower()
        if s and s not in ("no", "false", "0", "n", "f", "nan", "none"):
            idx.add(i)
    return idx


def _fill_missing_from_raw(enriched_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing emails and phone numbers from raw file, respecting exclusions.

    If enrichment didn't find an email/phone but raw file has it, use the raw value.
    BUT: if the contact is excluded, keep them excluded (don't add their contact data).
    """
    out = enriched_df.copy()

    raw_email_col = next((c for c in raw_df.columns if c.lower() in ["email", "email address"]), None)
    raw_phone_col = next((c for c in raw_df.columns if c.lower() in ["phone", "phone number", "mobile", "mobile number"]), None)

    if raw_email_col and raw_email_col in raw_df.columns:
        for idx, row in out.iterrows():
            if idx < len(raw_df):
                is_excluded = row.get("Exclusion Status") == "Excluded" if "Exclusion Status" in row else False
                is_empty = not row.get("email") or str(row.get("email")).strip().lower() in ["", "nan", "none"]

                if is_empty and not is_excluded:
                    raw_email = raw_df.iloc[idx].get(raw_email_col)
                    if raw_email and str(raw_email).strip() and str(raw_email).lower() != "nan":
                        out.at[idx, "email"] = raw_email

    if raw_phone_col and raw_phone_col in raw_df.columns:
        for idx, row in out.iterrows():
            if idx < len(raw_df):
                is_excluded = row.get("Exclusion Status") == "Excluded" if "Exclusion Status" in row else False
                is_empty = not row.get("mobile_phone") or str(row.get("mobile_phone")).strip().lower() in ["", "nan", "none"]

                if is_empty and not is_excluded:
                    raw_phone = raw_df.iloc[idx].get(raw_phone_col)
                    if raw_phone and str(raw_phone).strip() and str(raw_phone).lower() != "nan":
                        out.at[idx, "mobile_phone"] = raw_phone

    return out


async def _status(step: inngest.Step, key: str, run_id: str, **kwargs):
    """Wraps run_status.update() in a step.run() keyed by `key`, so it fires
    exactly once (in causal order) no matter how many replay invocations
    Inngest performs before/after it - see the module docstring."""
    async def _do():
        run_status.update(run_id, **kwargs)
        return True

    await step.run(key, _do)


async def _set_step(step: inngest.Step, key: str, run_id: str, step_key: str, title: str, status: str,
                     summary=None, seconds=None, cost=None):
    async def _do():
        run_status.set_step(run_id, step_key, title, status, summary, seconds, cost)
        return True

    await step.run(key, _do)


async def _set_stat(step: inngest.Step, key: str, run_id: str, stat_key: str, value):
    async def _do():
        run_status.set_stat(run_id, stat_key, value)
        return True

    await step.run(key, _do)


async def _accrue_cost(step: inngest.Step, key: str, run_id: str, block: dict):
    async def _do():
        run_status.accrue_cost(run_id, block)
        return True

    await step.run(key, _do)


async def _ask(step: inngest.Step, run_id: str, key: str, qtype: str, prompt: str,
                options: list[str] | None = None, default: str | None = None, context: dict | None = None):
    """Inngest-native replacement for runner.py's thread-blocking ask(): persists
    the pending question to the run_status projection, then suspends the
    function - without blocking a server - until a matching run/answer event
    arrives, correlated by run_id + key via if_exp (same pattern verified by
    inngest_functions.wait_test)."""
    await _status(step, f"ask_{key}_pending", run_id, stage="awaiting_answer", message=prompt,
                  pending_question={"key": key, "type": qtype, "prompt": prompt,
                                     "options": options, "default": default, "context": context or {}})

    event = await step.wait_for_event(
        f"wait_{key}",
        event="run/answer",
        timeout=datetime.timedelta(days=7),
        if_exp=f"async.data.run_id == '{run_id}' && async.data.key == '{key}'",
    )
    if event is None:
        raise TimeoutError(f"No answer for question '{key}' within 7 days (run {run_id})")

    await _status(step, f"ask_{key}_answered", run_id, pending_question=None)

    return event.data["value"]


_OTHER = "Other - not listed"


async def _extract_and_confirm_icp(step: inngest.Step, run_id: str, campaign_idea: str, *,
                                    extract_key: str, confirm_key: str, prompt_prefix: str = ""):
    """Turns a free-text campaign idea into confirmed (persona_titles,
    person_locations, employee_ranges), reusing runner.py's exact
    extraction-prompt shape and _ask_icp_confirm's exact context shape - the
    frontend's StepCard.tsx already fully renders "icp_confirm_form" (built
    for the legacy engine, never actually reachable there since that flow
    crashes on a missing function before ever getting this far).
    extract_key/confirm_key must be unique per call site, including per "add
    more prospects" loop iteration.

    Three fallbacks to manual title entry, matching runner.py's existing
    fallback shapes: no ICP workbook at all, Claude extracts a product/use-case
    that isn't in the workbook (runner.py hard-raises in that case - "Could
    not map: {product} -> {use_case}" - which would fire constantly for a
    real, missing product like "Global API", confirmed: the workbook only has
    3 sheets), or the user explicitly picks "Other" instead of any listed
    product/use-case (nothing to look wrong here - they just aren't locked
    into the sheet's list). All three degrade the same way instead."""

    async def _load_use_cases():
        return icp_mapper.get_use_case_options()

    use_case_options = await step.run(f"{extract_key}_load_use_cases", _load_use_cases)

    if not use_case_options:
        titles_answer = await _ask(
            step, run_id, f"{confirm_key}_manual_titles", "text",
            "ICP reference sheet not found - enter job titles to target (comma-separated):",
            default="", context={"step": "source"},
        )
        persona_titles = [t.strip() for t in str(titles_answer).split(",") if t.strip()] or None
        return persona_titles, None, None

    async def _extract():
        claude = Anthropic()
        extract_prompt = f"""Analyze this campaign idea and extract the Xoxoday product and use case.

Campaign Idea:
{campaign_idea}

Available products and use cases:
{json.dumps({p: uc[:5] for p, uc in use_case_options.items()}, indent=2)}

Return ONLY valid JSON:
{{
  "product": "Empuls use cases",
  "use_case": "Engagement & Listening",
  "reasoning": "brief explanation"
}}

If uncertain, pick the most likely match. Return ONLY JSON, no markdown."""
        try:
            resp = claude.messages.create(model="claude-opus-4-1", max_tokens=300,
                                           messages=[{"role": "user", "content": extract_prompt}])
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json\n")
            extracted = json.loads(text)
            return {"product": (extracted.get("product") or "").strip(),
                    "use_case": (extracted.get("use_case") or "").strip(), "error": None}
        except Exception as e:
            return {"product": None, "use_case": None, "error": str(e)}

    extracted = await step.run(f"{extract_key}_claude_extract", _extract)

    async def _manual_titles_fallback(reason: str):
        titles_answer = await _ask(
            step, run_id, f"{confirm_key}_manual_titles_unmapped", "text",
            f"{reason} - enter job titles to target (comma-separated):",
            default="", context={"step": "source"},
        )
        persona_titles = [t.strip() for t in str(titles_answer).split(",") if t.strip()] or None
        return persona_titles, None, None

    if extracted["error"] or not extracted["product"]:
        product_list = sorted(use_case_options.keys()) + [_OTHER]
        product = await _ask(step, run_id, f"{confirm_key}_manual_product", "choice",
                              "Which Xoxoday product?", options=product_list, context={"step": "source"})
        if product == _OTHER:
            return await _manual_titles_fallback("Product not listed")
        use_case_list = use_case_options.get(product, []) + [_OTHER]
        use_case = await _ask(step, run_id, f"{confirm_key}_manual_use_case", "choice",
                               "Which use case?", options=use_case_list,
                               context={"step": "source"})
        if use_case == _OTHER:
            return await _manual_titles_fallback("Use case not listed")
    else:
        product, use_case = extracted["product"], extracted["use_case"]

    icp_mapping = icp_mapper.map_use_case_to_icp(product, use_case)

    if not icp_mapping:
        return await _manual_titles_fallback(
            f"Couldn't map \"{product} - {use_case}\" to a known ICP (that product/use-case isn't in the "
            "reference sheet yet)"
        )

    form_answer = await _ask(
        step, run_id, confirm_key, "icp_confirm_form",
        f"{prompt_prefix}Matched \"{campaign_idea[:80]}...\" to **{product} - {use_case}** "
        f"(Economic Buyer: {icp_mapping.get('economic_buyer') or 'n/a'}, "
        f"Champion: {icp_mapping.get('champion') or 'n/a'}). Pre-filled from the ICP sheet - edit or add your own.",
        default=None,
        context={
            "step": "source",
            "icp_sheet_url": icp_mapper.ICP_SHEET_URL,
            "economic_buyer": icp_mapping.get("economic_buyer", ""),
            "champion": icp_mapping.get("champion", ""),
            "influencer": icp_mapping.get("influencer", ""),
            "fields": {
                "job_titles": {
                    "label": "Job titles (from the ICP sheet - uncheck any to exclude, or add your own)",
                    "options": icp_mapping.get("job_titles") or [],
                    "default": icp_mapping.get("job_titles") or [],
                },
                "employee_sizes": {
                    "label": "Employee size (optional - leave blank for no filter, or add your own)",
                    "options": [label for label, _ in config.EMPLOYEE_SIZE_BUCKETS],
                    "default": [],
                },
                "regions": {
                    "label": "Regions (uncheck to exclude, or add your own)",
                    "options": REGION_OPTIONS, "country_options": COUNTRY_OPTIONS,
                    "default": icp_mapping.get("regions") or [],
                },
            },
        },
    )
    form_answer = form_answer or {}
    persona_titles = form_answer.get("job_titles") or None
    person_locations = form_answer.get("regions") or None
    employee_ranges = _normalize_employee_size_labels(form_answer.get("employee_sizes") or [])
    return persona_titles, person_locations, employee_ranges


async def _add_more_prospects_loop(step: inngest.Step, run_id: str, candidates_df: pd.DataFrame,
                                    persona_titles, person_locations, employee_ranges, do_search,
                                    exact_titles: bool = True, max_iterations: int = 5,
                                    organization_locations=None):
    """Bounded version of runner.py's unbounded `while add_more:` loop (lines
    597-715 there) - Inngest step keys must be unique per run, so a real
    while loop can't work here; capped at max_iterations rounds instead.
    do_search(names, titles, locations, employee_ranges, key_suffix) is the
    same closure the caller used for the initial search, reused here for
    each iteration. organization_locations (company HQ filter) carries
    through unchanged across iterations - only the campaign-idea path can set
    it, and re-extracting ICP from a refined idea never touches it."""
    total_found = len(candidates_df)
    for i in range(1, max_iterations + 1):
        add_more = await _ask(
            step, run_id, f"apollo_add_more_prospects_{i}", "yes_no",
            f"Found {total_found} prospect(s) so far.\n\nAdd more prospects from other companies or with different filters?",
            default="no", context={"step": "source", "total_found": total_found, "iteration": i},
        )
        if not _truthy(add_more):
            break

        choice = await _ask(
            step, run_id, f"apollo_add_more_choice_{i}", "choice",
            "How would you like to add more prospects?",
            options=["Search different companies with same filters", "Search same companies with different filters"],
            context={"step": "source", "iteration": i},
        )

        if choice == "Search different companies with same filters":
            more_companies = await _ask(
                step, run_id, f"apollo_more_company_names_{i}", "text",
                "Additional company names (comma-separated, or paste one per line/space-separated - "
                "URLs are fine too):\ne.g. NewCo, AnotherCorp, TechStartup",
                default="", context={"step": "source"},
            )
            names = _parse_company_names(str(more_companies))
            if not names:
                continue
            more_df, _more_stats = await do_search(names, persona_titles, person_locations, employee_ranges,
                                                     key_suffix=f"_more_{i}", exact_titles=exact_titles,
                                                     p_org_locations=organization_locations)
            candidates_df = pd.concat([candidates_df, more_df], ignore_index=True)
        else:
            new_idea = await _ask(
                step, run_id, f"apollo_additional_campaign_idea_{i}", "text",
                "New campaign idea for same companies:\n(e.g., 'Target different departments - Finance instead of HR')",
                default="", context={"step": "source"},
            )
            if not new_idea.strip():
                continue
            new_persona_titles, new_person_locations, new_employee_ranges = await _extract_and_confirm_icp(
                step, run_id, new_idea,
                extract_key=f"icp_extract_more_{i}", confirm_key=f"icp_confirm_more_{i}",
                prompt_prefix="Refined filters - ",
            )
            persona_titles = new_persona_titles or persona_titles
            person_locations = new_person_locations or person_locations
            employee_ranges = new_employee_ranges or employee_ranges
            same_companies = candidates_df["Company"].dropna().unique().tolist()
            new_df, _new_stats = await do_search(same_companies, persona_titles, person_locations, employee_ranges,
                                                   key_suffix=f"_refilter_{i}", exact_titles=exact_titles,
                                                   p_org_locations=organization_locations)
            candidates_df = pd.concat([candidates_df, new_df], ignore_index=True)
            if "obfuscated_name" in candidates_df.columns:
                candidates_df = candidates_df.drop_duplicates(subset=["obfuscated_name", "Company"], keep="first")

        total_found = len(candidates_df)
        await _set_stat(step, f"stat_discovery_idea_more_{i}", run_id, "apollo_search",
                         {"candidates_found": total_found})

    return candidates_df, persona_titles, person_locations, employee_ranges


@client.create_function(
    fn_id="run_pipeline_slice1",
    trigger=inngest.TriggerEvent(event="run/start"),
)
async def run_pipeline_slice1(ctx: inngest.Context, step: inngest.Step) -> dict:
    """Thin wrapper so any exception - a bare raise from validation logic, or
    one already converted from a caught step.run() failure - lands as a clean
    "failed" run_status update immediately, instead of Inngest retrying a
    deterministic failure a few times first (matching runner.py's own
    top-level try/except in _execute())."""
    run_id = ctx.event.data["run_id"]
    try:
        return await _run_pipeline(ctx, step)
    except Exception as e:
        await _status(step, "status_failed", run_id, stage="failed", error=str(e), message="Failed")
        return {"run_id": run_id, "error": str(e)}


async def _run_pipeline(ctx: inngest.Context, step: inngest.Step) -> dict:
    data = ctx.event.data
    run_id = data["run_id"]
    input_source = data.get("input_source", "csv")
    csv_blob_pathname = data.get("csv_blob_pathname")
    csv_filename = data.get("csv_filename") or "input.csv"
    hubspot_project_id = data.get("hubspot_project_id")
    campaign_idea = (data.get("campaign_idea") or "").strip()
    wizard_targeting = data.get("wizard_targeting") or {}
    company_col = data.get("company_col")
    employee_col = data.get("employee_col")
    domain_col = data.get("domain_col")

    project_meta: dict = {}
    run_dir = config.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    async def _init():
        run_status.init(run_id)
        run_status.update(run_id, stage="reading_input", message="Reading input source")
        return True

    await step.run("init_status", _init)

    # ============ Input & Normalization ============
    scrape_stats = None
    if input_source == "csv":
        df = _read_csv_blob(csv_blob_pathname, csv_filename)

    elif input_source == "hubspot_project":
        await _status(step, "status_reading_project", run_id, message="Reading Project properties from HubSpot")

        async def _fetch_project():
            return _nan_safe(input_sources.fetch_hubspot_project(hubspot_project_id))

        project_meta = await step.run("fetch_hubspot_project", _fetch_project)

        if csv_blob_pathname:
            df = _read_csv_blob(csv_blob_pathname, csv_filename)
        else:
            link = project_meta.get("target_list_link")
            kind = project_meta.get("list_link_kind")
            copy = project_meta.get("campaign_copy_link")

            if not link:
                use_apollo = await _ask(
                    step, run_id, "use_apollo_search", "yes_no",
                    f"Project '{project_meta.get('name', '?')}' has no target account list linked. "
                    "Use Apollo to find prospects based on HubSpot properties (Region, Employee Size, Job Titles)? "
                    "(Or upload a CSV/Excel list manually.)",
                    default="yes", context={"step": "source"},
                )
                if not _truthy(use_apollo):
                    raise ValueError(
                        f"Project '{project_meta.get('name', '?')}' has no target-account spreadsheet linked"
                        + (f" (the record only has a campaign copy doc: {copy})" if copy else "")
                        + ". Upload the account spreadsheet (CSV/Excel) to continue."
                    )
                # Apollo-search-from-campaign-idea (product/use-case extraction via
                # Claude, ICP mapping, unbounded "add more prospects" loop) isn't
                # ported yet - it's also currently broken on the legacy engine
                # (calls domain_resolution.resolve_domains, which doesn't exist),
                # so nothing regresses by not supporting it here either.
                raise ValueError(
                    f"Project '{project_meta.get('name', '?')}' has no linked list, and Apollo search from a "
                    "campaign idea isn't supported on this engine yet. Upload the account spreadsheet "
                    "(CSV/Excel) to continue."
                )
            elif kind in ("document", "presentation"):
                raise ValueError(
                    f"The Project's linked file is a {kind} (campaign copy), not the target account list:\n{link}\n"
                    "Upload the account spreadsheet (CSV/Excel) to enrich."
                )
            elif kind == "webpage":
                await _status(step, "status_scraping_webpage", run_id,
                               message=f"Auto-extracting the list from the web page: {link[:70]}")

                async def _scrape():
                    try:
                        scraped_df, scrape_stats = web_scrape.scrape_accounts_from_url(
                            link, project_meta.get("campaign_concept", ""))
                        return _nan_safe({"records": scraped_df.to_dict("records"), "scrape_stats": scrape_stats, "error": None})
                    except Exception as e:
                        return {"records": None, "scrape_stats": None, "error": str(e)}

                scrape_result = await step.run("scrape_webpage_list", _scrape)
                if scrape_result["error"]:
                    raise ValueError(
                        f"Couldn't auto-extract the list from {link} ({scrape_result['error']}). "
                        "Open it, save the accounts as CSV/Excel, and upload them instead."
                    )
                df = pd.DataFrame(scrape_result["records"])
                scrape_stats = scrape_result["scrape_stats"]
                if df.empty:
                    if scrape_stats.get("resumed"):
                        raise ValueError(
                            f"All {scrape_stats.get('total_extracted', 0)} entries from this list were already "
                            f"extracted in previous runs - nothing new to enrich. (Delete {web_scrape.scrape_cache_location(link)} "
                            "to start the list over.)"
                        )
                    raise ValueError(
                        f"Auto-extraction found no records at {link}. "
                        "Open it, save the accounts as CSV/Excel, and upload them instead."
                    )
                await _set_stat(step, "stat_scrape", run_id, "scrape", scrape_stats)
                if scrape_stats.get("truncated"):
                    _off = scrape_stats.get("offset", 0)
                    _total = scrape_stats.get("total_extracted", scrape_stats["scraped"])
                    more_answer = await _ask(
                        step, run_id, "scrape_truncated_confirm", "yes_no",
                        f"This web list has more than {scrape_stats['max_records']} entries. This run extracted "
                        f"{scrape_stats['scraped']} (#{_off + 1}-#{_total}). Enrich these now? Re-running this "
                        f"project later continues from #{_total + 1}. (No = stop so you can upload the full list as CSV.)",
                        default="yes", context={"step": "source", "scrape": scrape_stats},
                    )
                    if not _truthy(more_answer):
                        raise ValueError(
                            f"Stopped - the web list has more than {scrape_stats['max_records']} entries. "
                            "Upload the full list as CSV to enrich all at once, or re-run to continue in batches."
                        )
            else:
                if not input_sources.is_link_autofetchable(link):
                    raise ValueError(
                        f"The Project's list is behind a login and can't be pulled automatically:\n{link}\n"
                        "Open it, download it as CSV/Excel, then upload it and start again."
                    )
                await _status(step, "status_fetching_link", run_id, message=f"Fetching the Project's linked list: {link[:70]}")

                async def _fetch_link():
                    try:
                        fetched_df = input_sources.fetch_form_link(link)
                        return _nan_safe({"records": fetched_df.to_dict("records"), "error": None})
                    except Exception as e:
                        return {"records": None, "error": str(e)}

                fetch_result = await step.run("fetch_form_link", _fetch_link)
                if fetch_result["error"]:
                    raise ValueError(
                        f"Couldn't auto-fetch the Project's linked list ({fetch_result['error']}). If it's behind "
                        "SharePoint/Drive login, download it and upload it as a CSV instead."
                    )
                df = pd.DataFrame(fetch_result["records"])

    elif input_source == "campaign_idea":
        if not campaign_idea:
            raise ValueError("campaign_idea input source requires a non-empty campaign_idea")
        if csv_blob_pathname:
            df = _read_csv_blob(csv_blob_pathname, csv_filename)
        else:
            df = None  # no company-list df yet - built entirely in the campaign_idea_no_csv block below

    else:
        raise ValueError(f"Unknown or unsupported input_source: {input_source!r}")

    campaign_idea_no_csv = (input_source == "campaign_idea" and df is None)

    persona_titles_from_idea = None
    person_locations_from_idea = None
    employee_ranges_from_idea = None
    exact_titles_from_idea = True
    organization_locations_from_idea = None

    if not campaign_idea_no_csv:
        # Some exports (seen on a real HubSpot pull) carry the same header twice -
        # df["Some Column"] then returns a DataFrame instead of a Series, and any
        # .str/.isna() call on it downstream blows up.
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]

        input_count = len(df)
        company_col = company_col or _guess_col(
            df, ["Company", "Company Name", "company", "Account Name", "Organization", "organization"])
        if not company_col:
            raise ValueError(f"Could not find a company-name column. Columns present: {list(df.columns)}")
        region_col = _guess_col(df, ["Region", "Country", "region", "country"])
        if project_meta:
            await _set_stat(step, "stat_project_meta", run_id, "project_meta", project_meta)

        if (company_col.strip().lower() not in {"company name", "company", "organization", "organisation", "account name"}
                and "Company" not in df.columns):
            df["Company"] = df[company_col]

        await _status(step, "status_normalizing", run_id, stage="normalizing", message="Normalizing names/company")
        df, norm_stats = normalize.run_normalization(df)
        resolved_company_col = "Cleaned Company Name" if "Cleaned Company Name" in df.columns else company_col

        src_summary = f"{input_count} row(s) read. Names & companies normalized."
        if scrape_stats:
            _rnote = f"resumed from #{scrape_stats.get('offset', 0) + 1}, " if scrape_stats.get("resumed") else ""
            _tnote = (f" (more remain - re-run to continue from #{scrape_stats.get('total_extracted', 0) + 1})"
                      if scrape_stats.get("truncated") else "")
            src_summary = (
                f"Auto-extracted {_rnote}{scrape_stats['scraped']} record(s) from the linked web page "
                f"({scrape_stats['method']}){_tnote} - review recommended. " + src_summary
            )
        if project_meta:
            src_summary = (
                f"Project '{project_meta.get('name', '?')}' - ICP: {project_meta.get('icp') or 'n/a'}, "
                f"region: {project_meta.get('region') or 'n/a'}. " + src_summary
            )

        await _set_step(step, "step_source_done", run_id, "source", "Input & Normalization", "done", src_summary)

        if input_source == "campaign_idea":
            # description + CSV: description drives targeting, CSV drives the
            # company list - confirm ICP now so People Discovery below can
            # skip its manual discovery_form ask and use this directly.
            if wizard_targeting:
                # User already confirmed targeting in the wizard - skip Claude
                # extraction and the icp_confirm_form re-ask entirely.
                (persona_titles_from_idea, person_locations_from_idea, employee_ranges_from_idea,
                 exact_titles_from_idea, organization_locations_from_idea) = \
                    _targeting_from_wizard(wizard_targeting)
            else:
                persona_titles_from_idea, person_locations_from_idea, employee_ranges_from_idea = \
                    await _extract_and_confirm_icp(
                        step, run_id, campaign_idea,
                        extract_key="icp_extract_with_csv", confirm_key="icp_confirm_with_csv",
                    )
                exact_titles_from_idea = True  # no wizard toggle on this path - exact-title matching by default

        # ============ Domain Resolution (gated) ============
        existing_domain_col = "Domain" if "Domain" in df.columns else _guess_col(df, ["domain", "website", "company domain"])
        if existing_domain_col and existing_domain_col != "Domain":
            df["Domain"] = df[existing_domain_col]
        if "Domain" not in df.columns:
            df["Domain"] = None
        df["Domain"] = df["Domain"].apply(lambda v: outputs.strip_url_prefix(v) if pd.notna(v) else v)

        missing_mask = _blank_domain_mask(df)
        missing_count = int(missing_mask.sum())
        already_present = len(df) - missing_count

        if missing_count == 0:
            await _set_step(step, "step_domain_auto_skipped", run_id, "domain", "Domain Resolution", "skipped",
                             f"Auto-skipped - all {already_present} row(s) already have a domain.")
            await _set_stat(step, "stat_domain_auto_skipped", run_id, "domain_resolution",
                             {"skipped": True, "already_present": already_present,
                              "reason": "every row already has a domain"})
        else:
            # count_needs_apollo checks Clearbit live (free) for every
            # uncached company first, so this estimate reflects what will
            # actually cost a credit - not just "uncached", which would
            # overstate it since Clearbit resolves a lot of these for free
            # before Apollo is ever touched.
            async def _count_needs_apollo():
                return domain_resolution.count_needs_apollo(df[missing_mask], resolved_company_col)

            uncached = await step.run("count_domains_needing_apollo", _count_needs_apollo)
            est = estimates.cost_block("domain_resolution", uncached)
            free_via_clearbit_or_cache = missing_count - uncached

            dom_answer = await _ask(
                step, run_id, "domain_resolution_needed", "yes_no",
                f"{missing_count} of {len(df)} rows need a domain. Clearbit (free) and the domain cache "
                f"already cover {free_via_clearbit_or_cache} of those; {uncached} need a paid Apollo lookup "
                f"(~{est['credits']} credits, ${est['usd']}). Resolve them?",
                default="yes", context={"step": "domain", "estimate": est, "missing": missing_count, "uncached": uncached},
            )

            if _truthy(dom_answer):
                await _status(step, "status_resolving_domains", run_id, stage="resolving_domains",
                               message=f"Resolving {missing_count} missing company domain(s) via Apollo")
                await _set_step(step, "step_domain_running", run_id, "domain", "Domain Resolution", "running")

                async def _resolve():
                    resolved_subset, domain_stats = domain_resolution.resolve_domains_for_df(
                        df[missing_mask].copy(), resolved_company_col, employee_col)
                    return _nan_safe({"records": resolved_subset.to_dict("records"), "domain_stats": domain_stats})

                result = await step.run("resolve_domains", _resolve)
                resolved_subset = pd.DataFrame(result["records"])
                domain_stats = result["domain_stats"]

                df.loc[missing_mask, "Domain"] = resolved_subset["Domain"].values
                df.loc[missing_mask, "Resolved Country"] = resolved_subset["Resolved Country"].values
                df.loc[missing_mask, "Resolved City"] = resolved_subset["Resolved City"].values

                resolved_now = missing_count - int(_blank_domain_mask(df).sum())
                domain_stats["already_present"] = already_present
                domain_stats["resolved"] = resolved_now
                source_note = (
                    f" ({domain_stats.get('from_apollo', 0)} via Apollo, {domain_stats.get('from_clearbit', 0)} via Clearbit fallback)"
                    if domain_stats.get("from_clearbit") else ""
                )
                await _set_step(step, "step_domain_done", run_id, "domain", "Domain Resolution", "done",
                                 f"Resolved {resolved_now} of {missing_count} missing domain(s){source_note}; "
                                 f"{already_present} already had one.")
                await _set_stat(step, "stat_domain_resolved", run_id, "domain_resolution", domain_stats)
            else:
                await _set_step(step, "step_domain_declined", run_id, "domain", "Domain Resolution", "skipped",
                                 f"Skipped by user - {missing_count} row(s) left without a domain.")
                await _set_stat(step, "stat_domain_declined", run_id, "domain_resolution",
                                 {"skipped": True, "already_present": already_present})

        # ============ Exclusion Check (gated) ============
        exclusion_answer = await _ask(
            step, run_id, "exclusion_needed", "yes_no",
            "Check these accounts against the HubSpot DNU list and drop existing clients?",
            default="yes",
            context={"step": "exclusion", "reference_url": config.exclusion_list_url(), "reference_label": "ABM EXCLSIONS - DNU"},
        )

        if _truthy(exclusion_answer):
            await _status(step, "status_checking_exclusions", run_id, stage="checking_exclusions",
                           message="Checking against HubSpot DNU list")
            await _set_step(step, "step_exclusion_running", run_id, "exclusion", "Exclusion Check", "running")

            exclusion_domain_col = "Domain" if "Domain" in df.columns else (domain_col or _guess_col(df, ["Domain", "Website"]))

            # Deliberately NOT wrapped in step.run(): same "output_too_large" cap
            # documented on _read_csv_blob above - returning the full DataFrame
            # (871+ rows, every original + normalized column) as a memoized step
            # output blows Inngest's response-size limit, which silently wedges
            # the run at "running" forever (the kill happens on Inngest's side,
            # never as a catchable Python exception). Safe to skip memoization:
            # this is a pure function of (df, DNU cache), so a replay just
            # recomputes the same result - the asyncio.to_thread offload below
            # still keeps the blocking Redis fetch + index build off the event
            # loop, it just isn't captured as a separate Inngest step anymore.
            df, exclusion_stats = await asyncio.to_thread(
                hubspot_exclusion.run_exclusion_check, df, exclusion_domain_col
            )
            exclusion_stats["dnu_list_url"] = config.exclusion_list_url()

            excl_name_col = resolved_company_col if resolved_company_col in df.columns else company_col
            ex_df = df[df["Exclusion Status"] == "Excluded"]
            exclusion_stats["excluded_rows"] = [
                {
                    "company": "" if pd.isna(r.get(excl_name_col)) else str(r.get(excl_name_col)),
                    "domain": "" if pd.isna(r.get("Domain")) else str(r.get("Domain")),
                    "reason": str(r.get("Exclusion Reason", "")),
                }
                for _, r in ex_df.head(500).iterrows()
            ]

            await _set_step(
                step, "step_exclusion_done", run_id, "exclusion", "Exclusion Check", "done",
                f"{exclusion_stats['excluded']} excluded, {exclusion_stats['ok_to_reach_out']} OK "
                f"(of {exclusion_stats['total']}); matched vs {exclusion_stats['dnu_record_count']} DNU records "
                f"from list {exclusion_stats['dnu_list_id']}.",
            )
            await _set_stat(step, "stat_exclusion_checked", run_id, "exclusion", exclusion_stats)
        else:
            df["Exclusion Status"] = "OK to reach out"
            df["Exclusion Reason"] = "Exclusion check skipped by user"
            exclusion_stats = {"skipped": True, "total": len(df), "excluded": 0, "ok_to_reach_out": len(df)}
            await _set_step(step, "step_exclusion_skipped", run_id, "exclusion", "Exclusion Check", "skipped",
                             f"Skipped - all {len(df)} treated as OK to reach out.")
            await _set_stat(step, "stat_exclusion_skipped", run_id, "exclusion", exclusion_stats)

        accounts_processed = df.copy()

        # ============ People Discovery (gated; auto-skip if named contacts present) ============
        ok_df = df[df["Exclusion Status"] == "OK to reach out"].copy()

        job_change_idx = _job_change_indices(ok_df)
        if job_change_idx:
            await _set_stat(step, "stat_job_changes", run_id, "job_changes", len(job_change_idx))

        email_col_existing = _guess_col(ok_df, ["email", "email address"])
        resolved_first_col = "Cleaned First Name" if "Cleaned First Name" in ok_df.columns else _guess_col(ok_df, ["first name", "firstname"])
        resolved_last_col = "Cleaned Last Name" if "Cleaned Last Name" in ok_df.columns else _guess_col(ok_df, ["last name", "lastname"])
        has_existing_contacts = (
            bool(resolved_first_col) and bool(resolved_last_col)
            and int(ok_df[resolved_first_col].notna().sum()) > 0
        )

        candidates_df = pd.DataFrame()

        if has_existing_contacts:
            named = int(ok_df[email_col_existing].notna().sum()) if email_col_existing else 0
            await _set_step(step, "step_discovery_auto_skipped", run_id, "discovery", "People Discovery", "skipped",
                             f"Sheet already has {named} named contact(s) - discovery not needed.")
            await _set_stat(step, "stat_discovery_auto_skipped", run_id, "apollo_search",
                             {"skipped": True, "reason": "sheet already had named contacts"})
        else:
            disc_answer = await _ask(
                step, run_id, "people_discovery_needed", "yes_no",
                f"No contacts in the sheet. Find decision-makers at the {len(ok_df)} account(s)? "
                "Search is free; revealing emails/phones later costs credits.",
                default="yes", context={"step": "discovery"},
            )

            if _truthy(disc_answer):
                if input_source == "campaign_idea" and persona_titles_from_idea is not None:
                    # ICP already confirmed above from the campaign idea - skip
                    # the manual discovery_form ask, use the confirmed targeting.
                    persona_titles = persona_titles_from_idea
                    person_locations = person_locations_from_idea
                    employee_ranges = employee_ranges_from_idea
                    exact_titles = exact_titles_from_idea
                    organization_locations = organization_locations_from_idea
                    # No management-level/department/exclude-titles ask on the
                    # wizard path yet - keep prior behavior (hardcoded default
                    # seniorities, no function filter, no exclusions).
                    person_seniorities = None
                    person_functions = None
                    exclude_titles = None
                    per_title_cap = 2
                else:
                    employee_ranges = None  # discovery_form doesn't collect this (out of scope, see plan)
                    icp_hint = project_meta.get("icp", "") if project_meta else ""
                    form_answer = await _ask(
                        step, run_id, "discovery_form", "discovery_form",
                        "Set up People Discovery",
                        default=None,
                        context={
                            "step": "discovery",
                            "fields": {
                                "persona_titles": {
                                    "label": "Job titles to target (comma-separated)",
                                    "placeholder": "Blank = default HR/People-leader list"
                                    + (f", or the Project ICP: {icp_hint}" if icp_hint else ""),
                                    "default": "",
                                },
                                "per_title_cap": {
                                    "label": "People per company, per job title",
                                    "default": 2, "min": 1, "max": 3,
                                },
                                "include_lookalikes": {
                                    "label": "Include similar/lookalike titles (broader match, not just the exact title)",
                                    "default": False,
                                },
                                "person_locations": {
                                    "label": "Region / country (optional - blank = Global, pick as many as you like)",
                                    "options": REGION_OPTIONS,
                                    "country_options": COUNTRY_OPTIONS,
                                    "default": [],
                                },
                                "organization_locations": {
                                    "label": "Company HQ location (optional - city, state, or country; "
                                    "semicolon-separated for more than one; for targeting companies "
                                    "headquartered somewhere specific, regardless of where the contact "
                                    "personally sits)",
                                    "placeholder": "e.g. Austin, Texas; Bengaluru, India",
                                    "default": "",
                                },
                                "icp_clusters": {
                                    "label": "ICP cluster (optional - pick canonical Xoxoday persona "
                                    "clusters to target; each expands into real Apollo-ready job title "
                                    "variants, merged with anything typed above)",
                                    "options": apollo_enrich.icp_cluster_options(),
                                    "default": [],
                                },
                                "management_level": {
                                    "label": "Management Level",
                                    "options": apollo_enrich.SENIORITY_OPTIONS,
                                    "default": apollo_enrich.DEFAULT_SENIORITIES,
                                },
                                "departments": {
                                    "label": "Departments & Job Function (optional)",
                                    "options": apollo_enrich.FUNCTION_OPTIONS,
                                    "default": [],
                                },
                                "exclude_titles": {
                                    "label": "Job titles to exclude (optional, comma-separated - Apollo "
                                    "has no native exclude filter, so this drops matching candidates "
                                    "from the results after search)",
                                    "placeholder": "e.g. intern, assistant",
                                    "default": "",
                                },
                            },
                        },
                    )
                    form_answer = form_answer or {}
                    manual_titles = [t.strip() for t in str(form_answer.get("persona_titles", "")).split(",") if t.strip()]
                    cluster_keys = form_answer.get("icp_clusters") or []
                    cluster_titles = apollo_enrich.titles_for_clusters(cluster_keys) or []
                    persona_titles = list(dict.fromkeys(manual_titles + cluster_titles)) or None
                    try:
                        per_title_cap = max(1, min(int(form_answer.get("per_title_cap") or 2), 3))
                    except (TypeError, ValueError):
                        per_title_cap = 2
                    # ICP clusters expand to deliberately broad substrings (see
                    # icp_titles.py) - exact word-set matching would miss most
                    # real titles against them, so picking a cluster forces
                    # lookalike mode regardless of the checkbox.
                    exact_titles = not _truthy(form_answer.get("include_lookalikes")) and not cluster_keys
                    raw_locations = form_answer.get("person_locations")
                    if isinstance(raw_locations, str):
                        person_locations = [r.strip() for r in raw_locations.split(",") if r.strip()] or None
                    else:
                        person_locations = [str(r).strip() for r in (raw_locations or []) if str(r).strip()] or None
                    raw_org_locations = form_answer.get("organization_locations")
                    # Split on ";"/newline, not "," - a single HQ location is
                    # often itself a "City, State" pair (see person_locations'
                    # comma-split above, which is safe there since region/
                    # country names don't normally contain internal commas).
                    organization_locations = [r.strip() for r in re.split(r"[;\n]+", str(raw_org_locations or "")) if r.strip()] or None
                    person_seniorities = [str(s).strip() for s in (form_answer.get("management_level") or []) if str(s).strip()] or None
                    person_functions = [str(s).strip() for s in (form_answer.get("departments") or []) if str(s).strip()] or None
                    exclude_titles = [t.strip() for t in str(form_answer.get("exclude_titles", "")).split(",") if t.strip()] or None

                effective_per_title_cap = per_title_cap if persona_titles else None

                await _status(step, "status_discovery_running", run_id, stage="enriching",
                               message=f"Searching Apollo at {len(ok_df)} accounts")
                await _set_step(step, "step_discovery_running", run_id, "discovery", "People Discovery", "running")

                async def _search():
                    found_df, search_stats = apollo_enrich.search_candidates(
                        ok_df, resolved_company_col, "Domain", person_locations=person_locations,
                        persona_titles=persona_titles, max_per_company=config.MAX_CONTACTS_PER_COMPANY_CAP,
                        per_title_cap=effective_per_title_cap, employee_ranges=employee_ranges,
                        exact_titles=exact_titles, organization_locations=organization_locations,
                        person_seniorities=person_seniorities, person_functions=person_functions,
                        exclude_titles=exclude_titles)
                    return _nan_safe({"records": found_df.to_dict("records"), "search_stats": search_stats})

                search_result = await step.run("search_candidates", _search)
                candidates_df = pd.DataFrame(search_result["records"])
                search_stats = search_result["search_stats"]

                cap_note = f" (up to {per_title_cap} per title per company)" if effective_per_title_cap else ""
                await _set_step(
                    step, "step_discovery_done", run_id, "discovery", "People Discovery", "done",
                    f"Searched {search_stats['companies_searched']} account(s), found "
                    f"{search_stats['candidates_found']} candidate(s){cap_note}. Search is free.",
                )
                await _set_stat(step, "stat_discovery_searched", run_id, "apollo_search", search_stats)
            else:
                await _set_step(step, "step_discovery_declined", run_id, "discovery", "People Discovery", "skipped",
                                 "Skipped by user.")
                await _set_stat(step, "stat_discovery_declined", run_id, "apollo_search", {"skipped": True})

    else:
        # ============ Campaign idea, no CSV: ICP confirm + company-names Apollo search ============
        # Replaces Input & Normalization / Domain Resolution / Exclusion Check /
        # People Discovery entirely for this path - there's no company-list df
        # until after the search below produces candidates_df.
        if wizard_targeting:
            # User already confirmed targeting in the wizard - skip Claude
            # extraction and the icp_confirm_form re-ask entirely.
            persona_titles, person_locations, employee_ranges, exact_titles, organization_locations = \
                _targeting_from_wizard(wizard_targeting)
        else:
            persona_titles, person_locations, employee_ranges = await _extract_and_confirm_icp(
                step, run_id, campaign_idea,
                extract_key="icp_extract_no_csv", confirm_key="icp_confirm_no_csv",
            )
            exact_titles = True  # no wizard toggle on this path - exact-title matching by default
            organization_locations = None  # no HQ-location ask on the manual ICP-extraction path

        await _set_step(step, "step_source_done_idea", run_id, "source", "Input & Normalization", "done",
                         f"Campaign idea captured: \"{campaign_idea[:80]}\".")

        wizard_company_names = _company_names_from_wizard(wizard_targeting) if wizard_targeting else []
        if wizard_company_names:
            # Already collected in the wizard's review step - asking again
            # would just repeat a question the user already answered.
            company_names = wizard_company_names
        else:
            companies_answer = await _ask(
                step, run_id, "apollo_company_names", "text",
                "Company names to search (comma-separated, or paste one per line/space-separated - "
                "URLs are fine too):\ne.g. Acme Corp, TechCo Inc, StartUp Labs",
                default="", context={"step": "source"},
            )
            company_names = _parse_company_names(str(companies_answer))
        if not company_names:
            raise ValueError("No company names provided for Apollo search.")

        async def _do_search(names, p_titles, p_locations, p_employee_ranges=None, key_suffix="", exact_titles=True,
                              p_org_locations=None):
            domains_df = pd.DataFrame([{"Company": c} for c in names])

            async def _resolve():
                resolved_df, dstats = domain_resolution.resolve_domains_for_df(domains_df, "Company", None)
                return _nan_safe({"records": resolved_df.to_dict("records"), "domain_stats": dstats})

            resolve_result = await step.run(f"resolve_domains_idea{key_suffix}", _resolve)
            resolved_df = pd.DataFrame(resolve_result["records"])

            if "Domain" not in resolved_df.columns or resolved_df["Domain"].isna().all():
                raise ValueError(f"Could not resolve domains for companies: {', '.join(names)}")

            async def _search():
                # per_title_cap=2 when specific titles were requested mirrors the
                # CSV/HubSpot-Project path's behavior, so exact_titles actually has
                # an effect here too (search_candidates only applies it under
                # select_candidates_per_persona) - previously this path always fell
                # through to the generic HR-tier ranking regardless of exact_titles.
                found_df, sstats = apollo_enrich.search_candidates(
                    resolved_df, "Company", "Domain", person_locations=p_locations,
                    persona_titles=p_titles, max_per_company=config.MAX_CONTACTS_PER_COMPANY_DEFAULT,
                    per_title_cap=(2 if p_titles else None), employee_ranges=p_employee_ranges,
                    exact_titles=exact_titles, organization_locations=p_org_locations)
                return _nan_safe({"records": found_df.to_dict("records"), "search_stats": sstats})

            search_result = await step.run(f"search_candidates_idea{key_suffix}", _search)
            return pd.DataFrame(search_result["records"]), search_result["search_stats"]

        candidates_df, search_stats = await _do_search(company_names, persona_titles, person_locations, employee_ranges,
                                                          exact_titles=exact_titles, p_org_locations=organization_locations)
        await _set_step(step, "step_domain_done_idea", run_id, "domain", "Domain Resolution", "done",
                         f"Resolved domains for {len(company_names)} compan{'y' if len(company_names) == 1 else 'ies'}.")
        await _set_step(
            step, "step_discovery_done_idea", run_id, "discovery", "People Discovery", "done",
            f"Searched {search_stats['companies_searched']} compan{'y' if search_stats['companies_searched'] == 1 else 'ies'}, "
            f"found {search_stats['candidates_found']} candidate(s).",
        )
        await _set_stat(step, "stat_discovery_idea", run_id, "apollo_search", search_stats)

        candidates_df, persona_titles, person_locations, employee_ranges = await _add_more_prospects_loop(
            step, run_id, candidates_df, persona_titles, person_locations, employee_ranges, _do_search,
            exact_titles=exact_titles, organization_locations=organization_locations)

        # Exclusion gate, applied to candidates - a separate small block rather
        # than sharing code with the tested exclusion block above, deliberately,
        # to avoid touching already-verified working code for a marginal dedup win.
        exclusion_answer = await _ask(
            step, run_id, "exclusion_needed_idea", "yes_no",
            "Check these candidates against the HubSpot DNU list and drop existing clients?",
            default="yes",
            context={"step": "exclusion", "reference_url": config.exclusion_list_url(), "reference_label": "ABM EXCLSIONS - DNU"},
        )
        if _truthy(exclusion_answer):
            await _set_step(step, "step_exclusion_running_idea", run_id, "exclusion", "Exclusion Check", "running")

            async def _run_exclusion_idea():
                result_df, estats = hubspot_exclusion.run_exclusion_check(candidates_df, "Domain")
                return _nan_safe({"records": result_df.to_dict("records"), "exclusion_stats": estats})

            excl_result = await step.run("run_exclusion_check_idea", _run_exclusion_idea)
            candidates_df = pd.DataFrame(excl_result["records"])
            exclusion_stats = excl_result["exclusion_stats"]
            await _set_step(step, "step_exclusion_done_idea", run_id, "exclusion", "Exclusion Check", "done",
                             f"{exclusion_stats['excluded']} excluded, {exclusion_stats['ok_to_reach_out']} OK.")
            await _set_stat(step, "stat_exclusion_checked_idea", run_id, "exclusion", exclusion_stats)
            candidates_df = candidates_df[candidates_df["Exclusion Status"] == "OK to reach out"].copy()
        else:
            candidates_df["Exclusion Status"] = "OK to reach out"
            await _set_step(step, "step_exclusion_skipped_idea", run_id, "exclusion", "Exclusion Check", "skipped",
                             "Skipped by user.")
            await _set_stat(step, "stat_exclusion_skipped_idea", run_id, "exclusion", {"skipped": True})

        # Populate every variable the rest of the pipeline (Email Reveal onward) depends on.
        company_col = "Company"
        resolved_company_col = "Company"
        region_col = None
        df = candidates_df.copy()
        accounts_processed = df.copy()
        ok_df = candidates_df.copy()
        job_change_idx = set()
        email_col_existing = None
        resolved_first_col = None
        resolved_last_col = None
        # False forces Email Reveal into the enrich_candidates(candidates_df)
        # branch below - correct, candidates_df already has that exact shape.
        has_existing_contacts = False

    # ============ Email Reveal & Validation ============
    core_df = pd.DataFrame()
    phone_cols = None            # (first_col, last_col, domain_col) for Step 6
    needs_existing_mapping = False

    if has_existing_contacts:
        # ============ ICP Filter (gated) ============
        # Runs before any Apollo spend below, so non-ICP rows never get paid
        # for - a sheet that already has names/titles/emails can still carry
        # people outside the target ICP (e.g. a raw event-attendee export).
        icp_filter_answer = await _ask(
            step, run_id, "icp_title_filter_needed", "yes_no",
            f"This sheet has {len(ok_df)} named contact(s). Remove anyone whose job title doesn't "
            "match your ICP before enriching?",
            default="yes", context={"step": "reveal"},
        )
        if _truthy(icp_filter_answer):
            if input_source == "campaign_idea" and persona_titles_from_idea:
                icp_titles = persona_titles_from_idea
                icp_exact = exact_titles_from_idea
            else:
                icp_titles_answer = await _ask(
                    step, run_id, "icp_title_filter_titles", "text",
                    "ICP job titles to keep (comma-separated) - anyone else gets removed as non-ICP:",
                    default="", context={"step": "reveal"},
                )
                icp_titles = [t.strip() for t in str(icp_titles_answer).split(",") if t.strip()]
                icp_exact = True

            title_col_for_filter = _guess_col(ok_df, ["title", "job title"])
            if not icp_titles:
                await _set_stat(step, "stat_icp_filter_no_titles", run_id, "icp_title_filter",
                                 {"skipped": True, "reason": "no ICP titles provided"})
            elif not title_col_for_filter:
                await _set_stat(step, "stat_icp_filter_no_title_col", run_id, "icp_title_filter",
                                 {"skipped": True, "reason": "no job-title column found in sheet"})
            else:
                before_count = len(ok_df)

                async def _apply_icp_filter():
                    keep_mask = ok_df[title_col_for_filter].apply(
                        lambda t: apollo_enrich.title_matches_any(str(t) if pd.notna(t) else "", icp_titles, exact=icp_exact)
                    )
                    kept_df = ok_df[keep_mask].copy()
                    return _nan_safe({"records": kept_df.to_dict("records"), "kept": len(kept_df)})

                filter_result = await step.run("apply_icp_title_filter", _apply_icp_filter)
                ok_df = pd.DataFrame(filter_result["records"])
                removed = before_count - filter_result["kept"]
                await _set_stat(step, "stat_icp_filter", run_id, "icp_title_filter",
                                 {"removed": removed, "kept": filter_result["kept"], "titles": icp_titles, "exact": icp_exact})
                await _set_step(
                    step, "step_icp_filter_done", run_id, "reveal", "Email Reveal & Validation", "running",
                    f"Removed {removed} non-ICP contact(s) by job title; {filter_result['kept']} remain.",
                )
        else:
            await _set_stat(step, "stat_icp_filter_declined", run_id, "icp_title_filter", {"skipped": True})

        await _status(step, "status_reveal_existing", run_id, stage="enriching",
                       message=f"Filling emails for {len(ok_df)} existing contact(s)")
        await _set_step(step, "step_reveal_running", run_id, "reveal", "Email Reveal & Validation", "running")

        async def _reveal_existing():
            filled_df, fill_stats = apollo_enrich.enrich_existing_contacts(
                ok_df, resolved_first_col, resolved_last_col, "Domain", email_col_existing,
                force_idx=job_change_idx)
            return _nan_safe({"records": filled_df.to_dict("records"), "fill_stats": fill_stats})

        reveal_result = await step.run("reveal_existing_contacts", _reveal_existing)
        core_df = pd.DataFrame(reveal_result["records"])
        fill_stats = reveal_result["fill_stats"]

        paid = fill_stats.get("paid_lookups", 0)
        cost = estimates.cost_block("email_reveal", paid)
        await _accrue_cost(step, "cost_reveal_existing", run_id, cost)

        usable = int(core_df["email"].apply(lambda v: bool(str(v).strip()) and str(v).lower() != "nan").sum())
        await _set_stat(step, "stat_apollo_enrich_existing", run_id, "apollo_enrich", {**fill_stats, "has_email": usable})

        jc = fill_stats.get("job_changes_refreshed", 0)
        await _set_step(
            step, "step_reveal_done_existing", run_id, "reveal", "Email Reveal & Validation", "done",
            f"{fill_stats.get('already_had_email', 0)} already had email, {fill_stats.get('from_cache', 0)} from cache (free), "
            f"{fill_stats.get('filled_new', 0)} newly revealed ({paid} paid). {usable} usable."
            + (f" {jc} job-change refresh(es)." if jc else ""),
            cost=cost,
        )
        phone_cols = (resolved_first_col, resolved_last_col, "Domain")
        needs_existing_mapping = True
    elif not candidates_df.empty:
        await _status(step, "status_reveal_candidates", run_id, stage="enriching",
                       message=f"Revealing details for {len(candidates_df)} candidate(s)")
        await _set_step(step, "step_reveal_running", run_id, "reveal", "Email Reveal & Validation", "running")

        async def _reveal_candidates():
            core, _full, enrich_stats = apollo_enrich.enrich_candidates(candidates_df)
            core = core.copy()
            core["company_domain"] = core["search_domain"].apply(outputs.strip_url_prefix)
            return _nan_safe({"records": core.to_dict("records"), "enrich_stats": enrich_stats})

        reveal_result = await step.run("reveal_candidates", _reveal_candidates)
        core_df = pd.DataFrame(reveal_result["records"])
        enrich_stats = reveal_result["enrich_stats"]

        paid = enrich_stats.get("paid_lookups", enrich_stats.get("contacts_enriched", 0))
        cost = estimates.cost_block("email_reveal", paid)
        await _accrue_cost(step, "cost_reveal_candidates", run_id, cost)
        await _set_stat(step, "stat_apollo_enrich_candidates", run_id, "apollo_enrich", enrich_stats)

        await _set_step(
            step, "step_reveal_done_candidates", run_id, "reveal", "Email Reveal & Validation", "done",
            f"{enrich_stats['contacts_enriched']} revealed ({enrich_stats.get('from_cache', 0)} from cache, {paid} paid), "
            f"{enrich_stats['has_email']} with a verified email.",
            cost=cost,
        )
        phone_cols = ("first_name", "last_name", "search_domain")
    else:
        await _set_step(step, "step_reveal_skipped", run_id, "reveal", "Email Reveal & Validation", "skipped",
                         "No contacts to reveal.")
        await _set_stat(step, "stat_apollo_enrich_skipped", run_id, "apollo_enrich",
                         {"skipped": True, "reason": "no contacts to reveal"})

    # ============ Mobile Phone (gated) ============
    if core_df.empty or phone_cols is None:
        await _set_step(step, "step_phone_skipped_none", run_id, "phone", "Mobile Phone", "skipped",
                         "No revealed contacts to look up phones for.")
        await _set_stat(step, "stat_phone_skipped_none", run_id, "apollo_phone", {"skipped": True})
    else:
        n = len(core_df)
        f_col0, l_col0, d_col0 = phone_cols
        # Job-change force only applies to the existing-contact path (its index
        # aligns with ok_df); discovered contacts have a fresh index.
        phone_force = job_change_idx if needs_existing_mapping else set()
        uncached = apollo_enrich.count_uncached_phones(core_df, f_col0, l_col0, d_col0, force_idx=phone_force)
        est = estimates.cost_block("mobile_phone", uncached)

        phone_answer = await _ask(
            step, run_id, "mobile_phone_needed", "yes_no",
            f"Reveal phone numbers for {n} contact(s)? {uncached} need a paid reveal "
            f"(~8 credits each = {est['credits']} credits, ${est['usd']}); {n - uncached} cached (free).",
            default="yes", context={"step": "phone", "estimate": est, "uncached": uncached},
        )

        if _truthy(phone_answer):
            await _status(step, "status_phone_running", run_id, message="Revealing phone numbers")
            await _set_step(step, "step_phone_running", run_id, "phone", "Mobile Phone", "running")

            async def _reveal_phones():
                phoned_df, phone_stats = apollo_enrich.enrich_phones(
                    core_df, f_col0, l_col0, d_col0, force_idx=phone_force)
                return _nan_safe({"records": phoned_df.to_dict("records"), "phone_stats": phone_stats})

            phone_result = await step.run("reveal_phones", _reveal_phones)
            core_df = pd.DataFrame(phone_result["records"])
            phone_stats = phone_result["phone_stats"]

            cost = estimates.cost_block("mobile_phone", phone_stats.get("phones_found", 0))
            await _accrue_cost(step, "cost_phone", run_id, cost)
            await _set_stat(step, "stat_phone_revealed", run_id, "apollo_phone", phone_stats)

            await _set_step(
                step, "step_phone_done", run_id, "phone", "Mobile Phone", "done",
                f"{phone_stats['phones_found']} of {phone_stats['total']} contact(s) have a phone number.",
                cost=cost,
            )
        else:
            await _set_step(step, "step_phone_declined", run_id, "phone", "Mobile Phone", "skipped",
                             "Skipped by user.")
            await _set_stat(step, "stat_phone_declined", run_id, "apollo_phone", {"skipped": True})

    # Map an existing-contact sheet onto canonical output columns AFTER the
    # optional phone step, so enrich_phones doesn't collide with the "Phone
    # Number" column the mapper would otherwise create.
    if needs_existing_mapping and not core_df.empty:
        core_df = _map_existing_contact_columns(core_df, resolved_first_col, resolved_last_col, resolved_company_col)

        # ============ Fill Missing Details (existing-contact sheets only, gated) ============
        # The discovered-candidates path already captures LinkedIn/company/
        # seniority via enrich_candidates' full Apollo response - this gap
        # only exists for a sheet that came in already named/emailed, where
        # enrich_existing_contacts only ever kept the email field.
        #
        # count_missing_details free-checks Apollo's bulk_match-by-email tier
        # live before counting a row against the paid estimate (network call,
        # so it's wrapped in step.run() like any other non-deterministic work).
        async def _count_missing_details():
            return apollo_enrich.count_missing_details(core_df)

        missing_details_count = await step.run("count_missing_details", _count_missing_details)
        if missing_details_count == 0:
            await _set_stat(step, "stat_details_no_gaps", run_id, "existing_contact_details",
                             {"skipped": True, "reason": "no missing details", "missing": 0})
        else:
            details_est = estimates.cost_block("existing_contact_details", missing_details_count)
            details_answer = await _ask(
                step, run_id, "fill_missing_details_needed", "yes_no",
                f"{missing_details_count} contact(s) are missing details like LinkedIn URL, company LinkedIn, "
                f"industry, seniority, or department (after checking Apollo's free bulk-match-by-email tier "
                f"first). Fill them via Apollo (~{details_est['credits']} credits, ${details_est['usd']})?",
                default="yes", context={"step": "reveal", "estimate": details_est, "missing": missing_details_count},
            )
            if _truthy(details_answer):
                await _status(step, "status_filling_details", run_id,
                               message=f"Filling missing details for {missing_details_count} contact(s)")

                async def _fill_details():
                    filled_df, details_stats = apollo_enrich.fill_missing_details(
                        core_df, resolved_first_col, resolved_last_col, "Domain")
                    return _nan_safe({"records": filled_df.to_dict("records"), "details_stats": details_stats})

                details_result = await step.run("fill_missing_details", _fill_details)
                core_df = pd.DataFrame(details_result["records"])
                details_stats = details_result["details_stats"]

                details_cost = estimates.cost_block("existing_contact_details", details_stats.get("paid_lookups", 0))
                await _accrue_cost(step, "cost_fill_details", run_id, details_cost)
                await _set_stat(step, "stat_details_filled", run_id, "existing_contact_details", details_stats)
                await _set_step(
                    step, "step_details_done", run_id, "reveal", "Email Reveal & Validation", "done",
                    f"Filled {details_stats.get('fields_filled', 0)} missing detail field(s) across "
                    f"{details_stats.get('free_lookups', 0)} free lookup(s) + {details_stats.get('paid_lookups', 0)} "
                    "paid lookup(s).",
                    cost=details_cost,
                )
            else:
                await _set_stat(step, "stat_details_declined", run_id, "existing_contact_details",
                                 {"skipped": True, "reason": "declined by user", "missing": missing_details_count})

    # ============ Completeness fill (deferred - only worth asking once we know the real gap count) ============
    completeness_cols = [
        c for c in (
            web_completeness._find_col(accounts_processed.columns, web_completeness.DOMAIN_CANDIDATES),
            web_completeness._find_col(accounts_processed.columns, web_completeness.INDUSTRY_CANDIDATES),
            web_completeness._find_col(accounts_processed.columns, web_completeness.EMPLOYEE_CANDIDATES),
        ) if c
    ]
    gap_count = 0
    if completeness_cols:
        gap_mask = pd.Series(False, index=accounts_processed.index)
        for c in completeness_cols:
            col = accounts_processed[c]
            gap_mask = gap_mask | col.isna() | (col.astype(str).str.strip() == "")
        gap_count = int(gap_mask.sum())

    if not config.ANTHROPIC_API_KEY:
        await _set_stat(step, "stat_completeness_no_key", run_id, "completeness",
                         {"skipped": True, "reason": "ANTHROPIC_API_KEY not configured", "gaps": gap_count})
    elif not completeness_cols or gap_count == 0:
        await _set_stat(
            step, "stat_completeness_no_gaps", run_id, "completeness",
            {"skipped": True, "reason": "no gaps found" if completeness_cols else "no Domain/Industry/Employee column present",
             "gaps": gap_count})
    else:
        fill_answer = await _ask(
            step, run_id, "completeness_fill_needed", "yes_no",
            f"{gap_count} account(s) still have gaps in {', '.join(completeness_cols)} after enrichment. "
            f"Fill them via a web-search lookup (1 Claude call per gap, "
            f"~{estimates.humanize_seconds(estimates.estimate_seconds('completeness', gap_count))})?",
            default="no", context={"step": "outputs", "gaps": gap_count, "columns": completeness_cols},
        )
        if _truthy(fill_answer):
            await _status(step, "status_completeness_running", run_id,
                           message=f"Filling {gap_count} completeness gap(s) via web search")

            async def _fill_completeness():
                filled_df, completeness_stats = web_completeness.fill_completeness_gaps(accounts_processed, resolved_company_col)
                return _nan_safe({"records": filled_df.to_dict("records"), "completeness_stats": completeness_stats})

            fill_result = await step.run("fill_completeness_gaps", _fill_completeness)
            accounts_processed = pd.DataFrame(fill_result["records"])
            await _set_stat(step, "stat_completeness_filled", run_id, "completeness", fill_result["completeness_stats"])
        else:
            await _set_stat(step, "stat_completeness_declined", run_id, "completeness",
                             {"skipped": True, "reason": "declined by user", "gaps": gap_count})

    # ============ Output Files & Name ============
    async def _suggest_title():
        return naming.suggest_campaign_title(project_meta, ok_df if not ok_df.empty else accounts_processed, region_col)

    suggested_title = await step.run("suggest_campaign_title", _suggest_title)

    campaign_title = await _ask(
        step, run_id, "campaign_title", "text",
        "Name this run (used for the campaign tag + HubSpot list). Edit if needed:",
        default=suggested_title, context={"step": "outputs"},
    )
    campaign_title = str(campaign_title).strip() or suggested_title
    # Stored so the file-download route can prefix downloaded filenames with
    # it (e.g. "P0_ABM_..._email_upload.csv" instead of a bare
    # "email_upload.csv") - otherwise a user with several runs open has no
    # way to tell which campaign a downloaded file belongs to.
    await _set_stat(step, "stat_campaign_title", run_id, "campaign_title", campaign_title)

    await _status(step, "status_assembling_outputs", run_id, stage="assembling_outputs", message="Writing output files")
    await _set_step(step, "step_outputs_running", run_id, "outputs", "Output Files & Name", "running")

    # ============ Fallback: Fill missing emails/phones from raw file (respecting exclusions) ============
    core_df = _fill_missing_from_raw(core_df, accounts_processed)

    async def _write_outputs():
        stats_snapshot = run_status.get(run_id).get("stats", {})
        file_refs, hubspot_ready_df = outputs.write_outputs(run_dir, accounts_processed, core_df, campaign_title, stats_snapshot)
        return _nan_safe({
            "file_refs": file_refs,
            "hubspot_ready_records": hubspot_ready_df.to_dict("records"),
            "channel_counts": stats_snapshot.get("channel_counts", {}),
        })

    write_result = await step.run("write_outputs", _write_outputs)
    file_paths = write_result["file_refs"]
    hubspot_ready_df = pd.DataFrame(write_result["hubspot_ready_records"])
    channel_counts = write_result["channel_counts"]

    await _set_stat(step, "stat_hubspot_ready_count", run_id, "hubspot_ready_count", len(hubspot_ready_df))
    await _set_stat(step, "stat_channel_counts", run_id, "channel_counts", channel_counts)

    # write_outputs() already wrote a first-pass SUMMARY.md before
    # hubspot_ready_count/channel_counts existed in stats - rewrite it now
    # with the complete picture, matching runner.py's own double-write.
    async def _rewrite_summary():
        stats_snapshot = run_status.get(run_id).get("stats", {})
        outputs.write_file(run_dir, "SUMMARY.md",
                            outputs.build_summary_markdown(campaign_title, stats_snapshot, accounts_processed),
                            "text/markdown")
        return True

    await step.run("rewrite_summary_with_final_stats", _rewrite_summary)

    await _set_step(
        step, "step_outputs_done", run_id, "outputs", "Output Files & Name", "done",
        f"3 channel files written - email {channel_counts.get('email', 0)}, "
        f"linkedin {channel_counts.get('linkedin', 0)}, calling {channel_counts.get('calling', 0)}.",
    )

    async def _append_output_files():
        job = run_status.get(run_id)
        existing = list(job.get("output_files", []))
        run_status.update(run_id, output_files=existing + list(file_paths.values()))
        return True

    await step.run("append_output_files", _append_output_files)

    # --- Optional PR ---
    pr_url = None
    if config.GITHUB_TOKEN and config.GITHUB_REPO:
        await _status(step, "status_opening_pr", run_id, stage="opening_pr", message="Opening PR with output files")

        async def _open_pr():
            stats_snapshot = run_status.get(run_id).get("stats", {})
            excl = stats_snapshot.get("exclusion", {})
            summary_line = (
                f"{excl.get('ok_to_reach_out', '?')} OK / {excl.get('excluded', '?')} excluded accounts. "
                f"{stats_snapshot.get('hubspot_ready_count', '?')} contacts ready for HubSpot import."
            )
            try:
                url = github_pr.open_output_pr(run_id, campaign_title, run_dir, file_paths, summary_line)
                return {"pr_url": url, "error": None}
            except Exception as e:
                return {"pr_url": None, "error": str(e)}

        pr_result = await step.run("open_output_pr", _open_pr)
        pr_url = pr_result["pr_url"]
        if pr_result["error"]:
            await _status(step, "status_pr_failed", run_id,
                           message=f"Could not open a PR automatically ({pr_result['error']}). Files are still saved locally.")

    async def _write_hubspot_ready_json():
        outputs.write_file(run_dir, "hubspot_ready.json", hubspot_ready_df.to_json(orient="records"), "application/json")
        return True

    await step.run("write_hubspot_ready_json", _write_hubspot_ready_json)

    # ============ Associations (multi-select) ============
    await _set_step(step, "step_associations_running", run_id, "associations", "Associations", "running")

    assoc_kinds_answer = await _ask(
        step, run_id, "association_types", "multi_choice",
        "Associate these contacts in HubSpot with any of these? (a static list is always created too)",
        options=["project", "partner", "event"], default="", context={"step": "associations"},
    )
    if isinstance(assoc_kinds_answer, list):
        kinds = [k for k in assoc_kinds_answer if k in ("project", "partner", "event")]
    else:
        kinds = [k.strip() for k in str(assoc_kinds_answer).split(",") if k.strip() in ("project", "partner", "event")]

    _MANUAL = "Other - enter manually"
    associations = []
    for kind in kinds:
        record_id = None

        async def _list_records():
            try:
                return association_resolve.list_records(kind)
            except Exception:
                return []

        records = await step.run(f"list_{kind}_records", _list_records)

        if records:
            option_map = {}
            options = []
            for rec in records:
                disp = rec["name"] or rec["id"]
                if disp in option_map:  # keep names unique in the dropdown
                    disp = f"{disp} ({rec['id']})"
                option_map[disp] = rec["id"]
                options.append(disp)
            options.append(_MANUAL)
            chosen = await _ask(
                step, run_id, f"{kind}_pick", "dropdown",
                f"Select the {kind} to associate these contacts with (type to filter):",
                options=options, context={"step": "associations", "kind": kind, "count": len(records)},
            )
            if chosen and chosen != _MANUAL and chosen in option_map:
                record_id = option_map[chosen]

        # Fallback: no records fetched, or the user chose "Other".
        if record_id is None:
            value = await _ask(step, run_id, f"{kind}_value", "text",
                                f"Enter the {kind} name, URL, or record ID:",
                                context={"step": "associations", "kind": kind})

            async def _resolve():
                return association_resolve.resolve(kind, str(value))

            resolved = await step.run(f"resolve_{kind}", _resolve)
            if resolved["status"] == "ambiguous":
                cands = resolved["candidates"]
                chosen_name = await _ask(
                    step, run_id, f"{kind}_disambiguate", "choice",
                    f"Multiple {kind} records matched {value!r} - which one?",
                    options=[c["name"] or c["id"] for c in cands],
                    context={"step": "associations", "candidates": cands},
                )
                match = next((c for c in cands if (c["name"] or c["id"]) == chosen_name), cands[0])
                record_id = match["id"]
            elif resolved["status"] == "not_found":
                raise ValueError(f"No {kind} record found matching {value!r}")
            else:
                record_id = resolved["record_id"]
        associations.append({"kind": kind, "record_id": record_id})

    await _set_step(
        step, "step_associations_done", run_id, "associations", "Associations", "done",
        f"Will associate with: {', '.join(kinds)}." if kinds else "No object association - a static list only.",
    )

    # ============ Preview & Upload (await explicit confirm) ============
    # No pending_question here (matches runner.py) - the frontend shows a
    # preview screen driven off stage == "awaiting_import_confirmation", not
    # a generic question prompt. run/answer with key "confirm_import" is what
    # a future cutover of routes/runs.py's /import endpoint would send instead
    # of calling run_confirmed_import() directly.
    await _set_step(step, "step_upload_awaiting_confirm", run_id, "upload", "Preview & Upload", "running",
                     "Review the preview, then confirm to write to HubSpot.")
    await _status(step, "status_awaiting_import_confirmation", run_id, stage="awaiting_import_confirmation",
                  pr_url=pr_url, message="Ready - review the preview, then confirm to import into HubSpot")

    confirm_event = await step.wait_for_event(
        "wait_confirm_import",
        event="run/answer",
        timeout=datetime.timedelta(days=7),
        if_exp=f"async.data.run_id == '{run_id}' && async.data.key == 'confirm_import'",
    )
    if confirm_event is None:
        raise TimeoutError(f"No import confirmation received within 7 days (run {run_id})")

    # ============ Confirmed import: HubSpot write + HeyReach push + Copy Agent ============
    await _status(step, "status_importing", run_id, stage="importing_to_hubspot", message="Importing to HubSpot")

    async def _do_import():
        rows = hubspot_ready_df.astype(object).where(pd.notna(hubspot_ready_df), None).to_dict(orient="records")
        return _nan_safe(hubspot_import.import_contacts_with_list(rows, campaign_title, associations))

    import_result = await step.run("hubspot_import", _do_import)

    async def _push_heyreach():
        if outputs.file_exists(run_dir, "linkedin_upload.csv"):
            try:
                li_df = pd.read_csv(io.BytesIO(outputs.read_file(run_dir, "linkedin_upload.csv")))
            except pd.errors.EmptyDataError:
                li_df = pd.DataFrame()
            if not li_df.empty:
                li_df = li_df.where(pd.notna(li_df), None)
                return _nan_safe(heyreach.push_leads(li_df.to_dict(orient="records"), campaign_title))
        return {"status": "skipped"}

    heyreach_result = await step.run("heyreach_push", _push_heyreach)
    import_result["heyreach"] = heyreach_result

    await _set_step(step, "step_copy_agent_running", run_id, "copy_agent", "Copy Agent", "running")
    await _status(step, "status_generating_copy", run_id, message="Generating campaign copy")

    async def _run_copy_agent():
        # Reuses the in-memory hubspot_ready_df instead of re-reading
        # hubspot_ready.json back from Blob (runner.py's run_confirmed_import
        # had to re-read it, being a separate function call with no access to
        # this run's local state) - same data, one less Blob round-trip.
        return _nan_safe(copy_agent.run(hubspot_ready_df))

    copy_result = await step.run("copy_agent_run", _run_copy_agent)
    import_result["copy_agent"] = {k: v for k, v in copy_result.items() if k != "copy"}

    async def _write_copy_agent_outputs():
        if copy_result["status"] == "done":
            json_path = outputs.write_file(run_dir, "10_copy_agent.json", json.dumps(copy_result, indent=2), "application/json")
            md_path = outputs.write_file(run_dir, "10_COPY_AGENT.md", copy_agent.build_markdown(campaign_title, copy_result), "text/markdown")
            return [json_path, md_path]
        return []

    copy_output_files = await step.run("write_copy_agent_outputs", _write_copy_agent_outputs)

    async def _append_copy_agent_output_files():
        job = run_status.get(run_id)
        existing = list(job.get("output_files", []))
        run_status.update(run_id, output_files=existing + copy_output_files)
        return True

    await step.run("append_copy_agent_output_files", _append_copy_agent_output_files)

    hr = heyreach_result.get("status")
    hr_note = f" HeyReach: {heyreach_result.get('pushed', 0)} pushed." if hr == "pushed" else ""
    await _set_step(step, "step_upload_done", run_id, "upload", "Preview & Upload", "done",
                     f"Imported {import_result['total']} contact(s); static list created.{hr_note}")

    if copy_result["status"] == "done":
        await _set_step(step, "step_copy_agent_done", run_id, "copy_agent", "Copy Agent", "done",
                         f"5-step email + LinkedIn copy generated for {copy_result['lead_count']} lead(s).")
    else:
        await _set_step(step, "step_copy_agent_skipped", run_id, "copy_agent", "Copy Agent", "skipped",
                         copy_result.get("message", copy_result["status"]))

    await _set_stat(step, "stat_hubspot_import", run_id, "hubspot_import", import_result)

    await _status(step, "status_final_done", run_id, stage="done", message="Imported to HubSpot",
                  hubspot_list_url=import_result["list"]["list_url"])

    return {"run_id": run_id, "rows": len(df), "candidates_found": len(candidates_df),
            "core_contacts": len(core_df), "has_existing_contacts": has_existing_contacts,
            "campaign_title": campaign_title, "hubspot_ready_count": len(hubspot_ready_df), "pr_url": pr_url}
