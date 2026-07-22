"""In-memory job store + background pipeline runner, restructured as an
interactive step flow: the background thread pauses at defined checkpoints
(ask()) and waits for a frontend answer (submit_answer()) before continuing.
Single-instance MVP - good enough for a small internal team tool; swap for a
real queue/DB if this needs to scale to concurrent multi-user load.

File uploads (Account Mapping Sheet, target-list CSV) only happen at run
creation time, not mid-flow - if exclusion turns out to be needed but no
mapping sheet was provided/configured, the run fails with a clear message to
restart with one attached, rather than trying to shoehorn a file upload into
the JSON answer mechanism.
"""
from __future__ import annotations
import threading
import time
import traceback
import uuid
from pathlib import Path

import pandas as pd

from .. import config
from ..models import RunStage
from . import (
    input_sources, normalize, domain_resolution, apollo_enrich,
    outputs, github_pr, web_completeness, naming, association_resolve,
    hubspot_lists, hubspot_import, estimates, hubspot_exclusion, heyreach, web_scrape,
)

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

# Canonical left-sidebar steps, in order. The frontend renders this whole list
# and merges in per-run status/summary/cost from stats["steps"].
STEP_DEFS = [
    ("source", "Input & Normalization"),
    ("domain", "Domain Resolution"),
    ("exclusion", "Exclusion Check"),
    ("discovery", "People Discovery"),
    ("reveal", "Email Reveal & Validation"),
    ("phone", "Mobile Phone"),
    ("outputs", "Output Files & Name"),
    ("associations", "Associations"),
    ("upload", "Preview & Upload"),
]


def _step(stats: dict, key: str, title: str, status: str, summary=None, seconds=None, cost=None):
    """Upsert a step's status/summary/time/cost into stats["steps"] (ordered).
    Tracks REAL elapsed time: stamps started_at when a step goes 'running', and
    on 'done'/'skipped' reports the measured duration (falls back to the passed
    estimate only if the step never had a running phase)."""
    steps = stats.setdefault("steps", [])
    prev = next((s for s in steps if s["key"] == key), None)
    started_at = prev.get("started_at") if prev else None
    now = time.time()
    if status == "running" and not started_at:
        started_at = now

    if seconds is not None:
        time_str = estimates.humanize_seconds(seconds)
    else:
        time_str = prev.get("time") if prev else None
    elapsed_s = prev.get("elapsed_s") if prev else None

    if status in ("done", "skipped") and started_at:
        elapsed_s = round(now - started_at, 1)
        time_str = estimates.humanize_seconds(elapsed_s)  # measured wins over estimate

    entry = {"key": key, "title": title, "status": status, "summary": summary,
             "time": time_str, "elapsed_s": elapsed_s, "cost": cost, "started_at": started_at}
    if prev is not None:
        steps[steps.index(prev)] = entry
    else:
        steps.append(entry)


def _accrue_cost(stats: dict, block: dict):
    c = stats.setdefault("cost", {"credits": 0, "usd": 0.0, "breakdown": []})
    c["credits"] += block["credits"]
    c["usd"] = round(c["usd"] + block["usd"], 2)
    c["breakdown"].append(block)


def _update(run_id: str, **kwargs):
    with _LOCK:
        job = JOBS[run_id]
        # Capture every distinct status message into a timestamped activity log
        # so the UI can show what's happening and how long each thing takes.
        if "message" in kwargs and kwargs["message"]:
            msg = kwargs["message"]
            log = job.setdefault("log", [])
            if not log or log[-1]["msg"] != msg:
                started = job.get("started_at")
                elapsed = round(time.time() - started, 1) if started else 0.0
                log.append({"elapsed_s": elapsed, "msg": msg})
        job.update(kwargs)


def _set_message(run_id: str, msg: str):
    """Update the live status message WITHOUT appending to the activity log -
    for high-frequency per-item progress (e.g. 'Resolving domains 42/300')."""
    with _LOCK:
        if run_id in JOBS:
            JOBS[run_id]["message"] = msg


def _make_progress(run_id: str, label: str):
    """Returns a progress(done, total, name) callback that streams a live
    count + ETA to the header and logs a milestone line every 20 items."""
    t0 = time.time()

    def _p(done, total, name=""):
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        _set_message(run_id, f"{label} {done}/{total} - {str(name)[:24]} - ETA {estimates.humanize_seconds(eta)}")
        if done == 1 or done % 20 == 0 or done == total:
            _update(run_id, message=f"{label}: {done}/{total} in {estimates.humanize_seconds(elapsed)}")

    return _p


def get_job(run_id: str) -> dict | None:
    with _LOCK:
        return dict(JOBS[run_id]) if run_id in JOBS else None


def ask(run_id: str, key: str, qtype: str, prompt: str, options: list[str] | None = None,
        default: str | None = None, context: dict | None = None):
    """Pauses the background thread until the frontend answers this question."""
    event = threading.Event()
    with _LOCK:
        JOBS[run_id]["_event"] = event
        JOBS[run_id]["_answer"] = None
        JOBS[run_id]["stage"] = RunStage.awaiting_answer
        JOBS[run_id]["pending_question"] = {
            "key": key, "type": qtype, "prompt": prompt,
            "options": options, "default": default, "context": context or {},
        }
        JOBS[run_id]["message"] = prompt
    event.wait()
    with _LOCK:
        answer = JOBS[run_id]["_answer"]
        JOBS[run_id]["pending_question"] = None
    return answer


def submit_answer(run_id: str, key: str, value):
    with _LOCK:
        job = JOBS.get(run_id)
        if not job:
            raise ValueError("Run not found")
        pq = job.get("pending_question")
        if not pq or pq["key"] != key:
            raise ValueError(f"No pending question with key {key!r} for this run right now")
        job["_answer"] = value
        event = job["_event"]
    event.set()


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("yes", "true", "y", "1")


def start_run(
    input_source: str,
    csv_bytes: bytes | None,
    csv_filename: str | None,
    hubspot_project_id: str | None,
    mapping_sheet_bytes: bytes | None,
    mapping_sheet_filename: str | None,
    company_col: str | None,
    domain_col: str | None,
    employee_col: str | None,
) -> str:
    run_id = uuid.uuid4().hex[:12]
    run_dir = config.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    JOBS[run_id] = {
        "run_id": run_id, "stage": RunStage.queued, "message": "Queued", "error": None,
        "stats": {}, "output_files": [], "pr_url": None, "hubspot_list_url": None,
        "pending_question": None, "started_at": time.time(), "log": [],
    }

    t = threading.Thread(
        target=_execute,
        args=(run_id, run_dir, input_source, csv_bytes, csv_filename, hubspot_project_id,
              mapping_sheet_bytes, mapping_sheet_filename, company_col, domain_col, employee_col),
        daemon=True,
    )
    t.start()
    return run_id


def _guess_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.strip().lower(): c for c in df.columns}
    # Exact match first
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    # Substring fallback - catches export-specific headers like
    # "Company Name for Emails" (Apollo) that don't exactly match "Company Name"
    for cand in candidates:
        for header, original in lower_map.items():
            if cand.lower() in header:
                return original
    return None


def _map_existing_contact_columns(df: pd.DataFrame, first_col: str, last_col: str, company_col: str) -> pd.DataFrame:
    """Maps whatever headers an already-enriched sheet uses (Apollo export
    style: 'Person Linkedin Url', '# Employees', 'Work Direct Phone', ...)
    onto the canonical column names outputs.build_hubspot_import_file expects
    (organization_*, linkedin_url, etc.) - without touching that mapping table."""
    out = df.copy()
    title_col = _guess_col(out, ["title", "job title"])
    linkedin_col = _guess_col(out, ["person linkedin url", "linkedin url", "linkedin"])
    company_li_col = _guess_col(out, ["company linkedin url"])
    industry_col = _guess_col(out, ["industry"])
    employees_col = _guess_col(out, ["# employees", "employees", "employee count"])
    revenue_col = _guess_col(out, ["annual revenue"])
    city_col = _guess_col(out, ["city"])
    state_col = _guess_col(out, ["state"])
    country_col = _guess_col(out, ["country"])
    seniority_col = _guess_col(out, ["seniority"])
    dept_col = _guess_col(out, ["departments", "department"])
    tech_col = _guess_col(out, ["technologies"])
    work_phone_col = _guess_col(out, ["work direct phone"])
    mobile_phone_col = _guess_col(out, ["mobile phone"])

    out["first_name"] = out[first_col]
    out["last_name"] = out[last_col]
    out["title"] = out[title_col] if title_col else None
    out["linkedin_url"] = out[linkedin_col] if linkedin_col else None
    out["organization_name"] = out[company_col]
    out["organization_linkedin_url"] = out[company_li_col] if company_li_col else None
    out["organization_industry"] = out[industry_col] if industry_col else None
    out["organization_estimated_num_employees"] = pd.to_numeric(out[employees_col], errors="coerce") if employees_col else None
    out["organization_annual_revenue"] = out[revenue_col] if revenue_col else None
    out["city"] = out[city_col] if city_col else None
    out["state"] = out[state_col] if state_col else None
    out["country"] = out[country_col] if country_col else None
    out["seniority"] = out[seniority_col] if seniority_col else None
    out["departments"] = out[dept_col] if dept_col else None
    out["technologies"] = out[tech_col] if tech_col else None

    if "Phone Number" not in out.columns:
        out["Phone Number"] = None
    fallback_phone_col = work_phone_col or mobile_phone_col
    if fallback_phone_col:
        blank_phone = out["Phone Number"].isna() | (out["Phone Number"].astype(str).str.strip() == "")
        out.loc[blank_phone, "Phone Number"] = out.loc[blank_phone, fallback_phone_col]

    out["search_company"] = out[company_col]
    out["search_domain"] = out["Domain"]
    out["company_domain"] = out["Domain"].apply(outputs.strip_url_prefix)
    out["email_status"] = out["email"].apply(
        lambda v: "verified" if v and str(v).strip() and str(v).lower() != "nan" else "unavailable"
    )
    return out


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


def _blank_domain_mask(df: pd.DataFrame) -> pd.Series:
    if "Domain" not in df.columns:
        return pd.Series([True] * len(df), index=df.index)
    return df["Domain"].isna() | (df["Domain"].astype(str).str.strip() == "")


def _execute(run_id, run_dir: Path, input_source, csv_bytes, csv_filename, hubspot_project_id,
             mapping_sheet_bytes, mapping_sheet_filename, company_col, domain_col, employee_col):
    try:
        stats = {}
        for k, t in STEP_DEFS:
            _step(stats, k, t, "pending")
        _update(run_id, stats=dict(stats))

        # ============ Step 1: Input & Normalization (mandatory, automatic) ============
        _update(run_id, stage=RunStage.reading_input, message="Reading input source")
        _step(stats, "source", "Input & Normalization", "running")
        project_meta = {}
        if input_source == "csv":
            df = input_sources.read_csv_bytes(csv_bytes, csv_filename or "input.csv")
        elif input_source == "hubspot_project":
            _update(run_id, message="Reading Project properties from HubSpot")
            project_meta = input_sources.fetch_hubspot_project(hubspot_project_id)
            if csv_bytes:
                df = input_sources.read_csv_bytes(csv_bytes, csv_filename or "input.csv")
            else:
                link = project_meta.get("target_list_link")
                kind = project_meta.get("list_link_kind")
                copy = project_meta.get("campaign_copy_link")
                if not link:
                    raise ValueError(
                        f"Project '{project_meta.get('name', '?')}' has no target-account spreadsheet linked"
                        + (f" (the record only has a campaign copy doc: {copy})" if copy else "")
                        + ". Upload the account spreadsheet (CSV/Excel) to continue."
                    )
                if kind in ("document", "presentation"):
                    # A doc is campaign COPY, not data - don't enrich it.
                    raise ValueError(
                        f"The Project's linked file is a {kind} (campaign copy), not the target account list:\n{link}\n"
                        "Upload the account spreadsheet (CSV/Excel) to enrich."
                    )
                if kind == "webpage":
                    # The list is referenced as a web page (often in the concept) -
                    # auto-extract it into account rows via the LLM.
                    _update(run_id, message=f"Auto-extracting the list from the web page: {link[:70]}")
                    try:
                        df, scrape_stats = web_scrape.scrape_accounts_from_url(link, project_meta.get("campaign_concept", ""))
                    except Exception as e:
                        raise ValueError(
                            f"Couldn't auto-extract the list from {link} ({e}). "
                            "Open it, save the accounts as CSV/Excel, and upload them instead."
                        )
                    if df.empty:
                        if scrape_stats.get("resumed"):
                            raise ValueError(
                                f"All {scrape_stats.get('total_extracted', 0)} entries from this list were already "
                                "extracted in previous runs - nothing new to enrich. (Delete the scrape cache in "
                                "wrapper/backend/cache/ to start the list over.)"
                            )
                        raise ValueError(
                            f"Auto-extraction found no records at {link}. "
                            "Open it, save the accounts as CSV/Excel, and upload them instead."
                        )
                    stats["scrape"] = scrape_stats
                    if scrape_stats.get("truncated"):
                        # More than one page of 500 - ask whether to enrich this batch;
                        # a later re-run continues from where this one stopped.
                        _off = scrape_stats.get("offset", 0)
                        _total = scrape_stats.get("total_extracted", scrape_stats["scraped"])
                        more_answer = ask(
                            run_id, "scrape_truncated_confirm", "yes_no",
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
                        # Behind a login (SharePoint/Drive) - don't even try (avoids a
                        # noisy 403). Give the link, tell them to download + upload.
                        raise ValueError(
                            f"The Project's list is behind a login and can't be pulled automatically:\n{link}\n"
                            "Open it, download it as CSV/Excel, then upload it and start again."
                        )
                    try:
                        _update(run_id, message=f"Fetching the Project's linked list: {link[:70]}")
                        df = input_sources.fetch_form_link(link)
                    except Exception as e:
                        raise ValueError(
                            f"Couldn't auto-fetch the Project's linked list ({e}). If it's behind "
                            "SharePoint/Drive login, download it and upload it as a CSV instead."
                        )
        else:
            raise ValueError(f"Unknown or unsupported input_source: {input_source!r}")

        input_count = len(df)
        company_col = company_col or _guess_col(df, ["Company", "Company Name", "company", "Account Name"])
        if not company_col:
            raise ValueError(f"Could not find a company-name column. Columns present: {list(df.columns)}")
        region_col = _guess_col(df, ["Region", "Country", "region", "country"])
        if project_meta:
            stats["project_meta"] = project_meta  # keep in local stats so it persists across updates
        _update(run_id, stats=dict(stats))

        # The vendored normalizer only does exact-name column matching - alias
        # whatever header we detected onto a name it recognizes so company
        # normalization (legal-suffix stripping) still runs.
        if company_col.strip().lower() not in {"company name", "company", "organization", "organisation", "account name"} and "Company" not in df.columns:
            df["Company"] = df[company_col]

        _update(run_id, stage=RunStage.normalizing, message="Normalizing names/company")
        df, norm_stats = normalize.run_normalization(df)
        stats["normalization"] = norm_stats
        resolved_company_col = "Cleaned Company Name" if "Cleaned Company Name" in df.columns else company_col

        # The all-rows LLM web-search completeness pass used to run here
        # automatically - it fired one Claude+web_search call per row with a
        # blank Industry/Employee/Domain, uncached, every run (the main hidden
        # delay). Firmographics come from the sheet + Apollo enrichment anyway,
        # so it's off by default. A targeted domain-only fallback still runs
        # after domain resolution for the few rows Apollo can't place.
        stats["completeness"] = {"skipped": True, "reason": "auto completeness disabled for speed"}

        src_summary = f"{input_count} row(s) read. Names & companies normalized."
        if stats.get("scrape"):
            _sc = stats["scrape"]
            _rnote = f"resumed from #{_sc.get('offset', 0) + 1}, " if _sc.get("resumed") else ""
            _tnote = f" (more remain - re-run to continue from #{_sc.get('total_extracted', 0) + 1})" if _sc.get("truncated") else ""
            src_summary = (
                f"Auto-extracted {_rnote}{_sc['scraped']} record(s) from the linked web page "
                f"({_sc['method']}){_tnote} - review recommended. " + src_summary
            )
        if project_meta:
            src_summary = (
                f"Project '{project_meta.get('name', '?')}' - ICP: {project_meta.get('icp') or 'n/a'}, "
                f"region: {project_meta.get('region') or 'n/a'}. " + src_summary
            )
        _step(stats, "source", "Input & Normalization", "done", src_summary,
              seconds=estimates.estimate_seconds("normalize", input_count))
        _update(run_id, stats=dict(stats))

        # ============ Step 2: Domain Resolution (gated) ============
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
            # Sheet already carries a domain on every row (standard headers,
            # data looks complete) - resolution is unnecessary, so we don't even
            # ask. Skip straight to exclusion.
            stats["domain_resolution"] = {"skipped": True, "already_present": already_present,
                                          "reason": "every row already has a domain"}
            _step(stats, "domain", "Domain Resolution", "skipped",
                  f"Auto-skipped - all {already_present} row(s) already have a domain.")
            _update(run_id, stats=dict(stats))
        else:
            uncached = domain_resolution.count_uncached(df[missing_mask], resolved_company_col)
            est = estimates.cost_block("domain_resolution", uncached)
            dom_answer = ask(
                run_id, "domain_resolution_needed", "yes_no",
                f"{missing_count} of {len(df)} rows need a domain. {uncached} need a paid Apollo lookup "
                f"(~{est['credits']} credits, ${est['usd']}); {missing_count - uncached} are cached (free). Resolve them?",
                default="yes", context={"step": "domain", "estimate": est, "missing": missing_count, "uncached": uncached},
            )
            if _truthy(dom_answer):
                _update(run_id, stage=RunStage.resolving_domains,
                        message=f"Resolving {missing_count} missing company domain(s) via Apollo (parallel)")
                _step(stats, "domain", "Domain Resolution", "running")

                _dom_t0 = time.time()

                def _dom_progress(done, total, name):
                    elapsed = time.time() - _dom_t0
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (total - done) / rate if rate > 0 else 0
                    _set_message(run_id, f"Resolving domains {done}/{total} - {name[:28]} - ETA {estimates.humanize_seconds(eta)}")
                    if done == 1 or done % 20 == 0 or done == total:
                        _update(run_id, message=f"Domain resolution: {done}/{total} done in {estimates.humanize_seconds(elapsed)}")

                resolved_subset, domain_stats = domain_resolution.resolve_domains_for_df(
                    df[missing_mask].copy(), resolved_company_col, employee_col, progress=_dom_progress)
                df.loc[missing_mask, "Domain"] = resolved_subset["Domain"].values

                still = _blank_domain_mask(df)
                if still.any():
                    _update(run_id, message="Some domains still missing - web-research pass")
                    filled_subset, second = web_completeness.fill_completeness_gaps(df[still].copy(), resolved_company_col)
                    df.loc[still, filled_subset.columns] = filled_subset
                    stats["completeness"]["second_pass"] = second

                resolved_now = missing_count - int(_blank_domain_mask(df).sum())
                cost = estimates.cost_block("domain_resolution", missing_count)
                _accrue_cost(stats, cost)
                domain_stats["already_present"] = already_present
                domain_stats["resolved"] = resolved_now
                stats["domain_resolution"] = domain_stats
                _step(stats, "domain", "Domain Resolution", "done",
                      f"Resolved {resolved_now} of {missing_count} missing domain(s); {already_present} already had one.",
                      seconds=estimates.estimate_seconds("domain_resolution", missing_count), cost=cost)
            else:
                stats["domain_resolution"] = {"skipped": True, "already_present": already_present}
                _step(stats, "domain", "Domain Resolution", "skipped",
                      f"Skipped by user - {missing_count} row(s) left without a domain.")
            _update(run_id, stats=dict(stats))

        # ============ Step 3: Exclusion Check (gated) ============
        exclusion_answer = ask(
            run_id, "exclusion_needed", "yes_no",
            "Check these accounts against the HubSpot DNU list and drop existing clients?",
            default="yes",
            context={"step": "exclusion", "reference_url": config.exclusion_list_url(), "reference_label": "ABM EXCLSIONS - DNU"},
        )
        if _truthy(exclusion_answer):
            _update(run_id, stage=RunStage.checking_exclusions, message="Checking against HubSpot DNU list")
            _step(stats, "exclusion", "Exclusion Check", "running")

            def _excl_progress(fetched, uniq):
                _update(run_id, message=f"Building DNU cache from HubSpot list (one-time): {fetched} members, {uniq} domains")

            exclusion_domain_col = "Domain" if "Domain" in df.columns else (domain_col or _guess_col(df, ["Domain", "Website"]))
            df, exclusion_stats = hubspot_exclusion.run_exclusion_check(df, exclusion_domain_col, progress=_excl_progress)
            exclusion_stats["dnu_list_url"] = config.exclusion_list_url()

            # Capture per-account "why excluded" for the final summary (capped).
            _excl_name_col = resolved_company_col if resolved_company_col in df.columns else company_col
            _ex_df = df[df["Exclusion Status"] == "Excluded"]
            exclusion_stats["excluded_rows"] = [
                {
                    "company": "" if pd.isna(r.get(_excl_name_col)) else str(r.get(_excl_name_col)),
                    "domain": "" if pd.isna(r.get("Domain")) else str(r.get("Domain")),
                    "reason": str(r.get("Exclusion Reason", "")),
                }
                for _, r in _ex_df.head(500).iterrows()
            ]
            _step(stats, "exclusion", "Exclusion Check", "done",
                  f"{exclusion_stats['excluded']} excluded, {exclusion_stats['ok_to_reach_out']} OK "
                  f"(of {exclusion_stats['total']}); matched vs {exclusion_stats['dnu_record_count']} DNU records from list {exclusion_stats['dnu_list_id']}.",
                  seconds=estimates.estimate_seconds("exclusion", len(df)))
        else:
            df["Exclusion Status"] = "OK to reach out"
            df["Exclusion Reason"] = "Exclusion check skipped by user"
            exclusion_stats = {"skipped": True, "total": len(df), "excluded": 0, "ok_to_reach_out": len(df)}
            _step(stats, "exclusion", "Exclusion Check", "skipped", f"Skipped - all {len(df)} treated as OK to reach out.")
        stats["exclusion"] = exclusion_stats
        _update(run_id, stats=dict(stats))

        accounts_processed = df.copy()
        ok_df = df[df["Exclusion Status"] == "OK to reach out"].copy()

        # Job changers must bypass the email/phone cache (old work data is stale).
        job_change_idx = _job_change_indices(ok_df)
        if job_change_idx:
            stats["job_changes"] = len(job_change_idx)

        # Does the sheet already carry named people? If so we reveal THEIR emails
        # (existing-contact path) rather than discovering new people - true for an
        # Apollo export, a Sales-Nav export, or an auto-scraped named list, even
        # when emails aren't present yet.
        email_col_existing = _guess_col(ok_df, ["email", "email address"])
        resolved_first_col = "Cleaned First Name" if "Cleaned First Name" in ok_df.columns else _guess_col(ok_df, ["first name", "firstname"])
        resolved_last_col = "Cleaned Last Name" if "Cleaned Last Name" in ok_df.columns else _guess_col(ok_df, ["last name", "lastname"])
        has_existing_contacts = (
            bool(resolved_first_col) and bool(resolved_last_col)
            and int(ok_df[resolved_first_col].notna().sum()) > 0
        )

        core_df = pd.DataFrame()
        candidates_df = pd.DataFrame()
        phone_cols = None            # (first_col, last_col, domain_col) for phone lookup
        needs_existing_mapping = False

        # ============ Step 4: People Discovery (gated; auto-skip if named contacts present) ============
        if has_existing_contacts:
            named = int(ok_df[email_col_existing].notna().sum()) if email_col_existing else 0
            stats["apollo_search"] = {"skipped": True, "reason": "sheet already had named contacts"}
            _step(stats, "discovery", "People Discovery", "skipped",
                  f"Sheet already has {named} named contact(s) - discovery not needed.")
            _update(run_id, stats=dict(stats))
        else:
            disc_answer = ask(
                run_id, "people_discovery_needed", "yes_no",
                f"No contacts in the sheet. Find decision-makers at the {len(ok_df)} account(s)? "
                "Search is free; revealing emails/phones later costs credits.",
                default="yes", context={"step": "discovery"},
            )
            if _truthy(disc_answer):
                count_answer = ask(
                    run_id, "contacts_per_company", "text",
                    f"How many contacts per company? (ideal 5-7, hard max {config.MAX_CONTACTS_PER_COMPANY_CAP})",
                    default=str(config.MAX_CONTACTS_PER_COMPANY_DEFAULT), context={"step": "discovery"},
                )
                try:
                    max_per_company = min(int(str(count_answer).strip()), config.MAX_CONTACTS_PER_COMPANY_CAP)
                except (TypeError, ValueError):
                    max_per_company = config.MAX_CONTACTS_PER_COMPANY_DEFAULT
                icp_hint = project_meta.get("icp", "") if project_meta else ""
                persona_answer = ask(
                    run_id, "persona_titles", "text",
                    "Job titles to target (comma-separated)? Blank = default HR/People-leader list"
                    + (f", or the Project ICP: {icp_hint}" if icp_hint else ""),
                    default="", context={"step": "discovery"},
                )
                persona_titles = [t.strip() for t in str(persona_answer).split(",") if t.strip()] or None

                _update(run_id, stage=RunStage.enriching, message=f"Searching Apollo at {len(ok_df)} accounts")
                _step(stats, "discovery", "People Discovery", "running")
                candidates_df, search_stats = apollo_enrich.search_candidates(
                    ok_df, resolved_company_col, "Domain", persona_titles=persona_titles, max_per_company=max_per_company)
                stats["apollo_search"] = search_stats
                _step(stats, "discovery", "People Discovery", "done",
                      f"Searched {search_stats['companies_searched']} account(s), found {search_stats['candidates_found']} candidate(s). Search is free.",
                      seconds=estimates.estimate_seconds("people_discovery", len(ok_df)))
            else:
                stats["apollo_search"] = {"skipped": True}
                _step(stats, "discovery", "People Discovery", "skipped", "Skipped by user.")
            _update(run_id, stats=dict(stats))

        # ============ Step 5: Email Reveal & Validation ============
        if has_existing_contacts:
            _update(run_id, stage=RunStage.enriching, message=f"Filling emails for {len(ok_df)} existing contact(s)")
            _step(stats, "reveal", "Email Reveal & Validation", "running")
            core_df, fill_stats = apollo_enrich.enrich_existing_contacts(
                ok_df, resolved_first_col, resolved_last_col, "Domain", email_col_existing,
                force_idx=job_change_idx, progress=_make_progress(run_id, "Email reveal"))
            paid = fill_stats.get("paid_lookups", 0)
            cost = estimates.cost_block("email_reveal", paid)
            _accrue_cost(stats, cost)
            usable = int(core_df["email"].apply(lambda v: bool(str(v).strip()) and str(v).lower() != "nan").sum())
            stats["apollo_enrich"] = {**fill_stats, "has_email": usable}
            jc = fill_stats.get("job_changes_refreshed", 0)
            _step(stats, "reveal", "Email Reveal & Validation", "done",
                  f"{fill_stats.get('already_had_email', 0)} already had email, {fill_stats.get('from_cache', 0)} from cache (free), "
                  f"{fill_stats.get('filled_new', 0)} newly revealed ({paid} paid). {usable} usable."
                  + (f" {jc} job-change refresh(es)." if jc else ""),
                  seconds=estimates.estimate_seconds("email_reveal", paid), cost=cost)
            phone_cols = (resolved_first_col, resolved_last_col, "Domain")
            needs_existing_mapping = True
        elif not candidates_df.empty:
            _update(run_id, stage=RunStage.enriching, message=f"Revealing details for {len(candidates_df)} candidate(s)")
            _step(stats, "reveal", "Email Reveal & Validation", "running")
            core_df, _full_df, enrich_stats = apollo_enrich.enrich_candidates(
                candidates_df, progress=_make_progress(run_id, "Email reveal"))
            core_df["company_domain"] = core_df["search_domain"].apply(outputs.strip_url_prefix)
            paid = enrich_stats.get("paid_lookups", enrich_stats.get("contacts_enriched", 0))
            cost = estimates.cost_block("email_reveal", paid)
            _accrue_cost(stats, cost)
            stats["apollo_enrich"] = enrich_stats
            _step(stats, "reveal", "Email Reveal & Validation", "done",
                  f"{enrich_stats['contacts_enriched']} revealed ({enrich_stats.get('from_cache', 0)} from cache, {paid} paid), "
                  f"{enrich_stats['has_email']} with a verified email.",
                  seconds=estimates.estimate_seconds("email_reveal", paid), cost=cost)
            phone_cols = ("first_name", "last_name", "search_domain")
        else:
            stats["apollo_enrich"] = {"skipped": True, "reason": "no contacts to reveal"}
            _step(stats, "reveal", "Email Reveal & Validation", "skipped", "No contacts to reveal.")
        _update(run_id, stats=dict(stats))

        # ============ Step 6: Mobile Phone (gated) ============
        if core_df.empty or phone_cols is None:
            stats["apollo_phone"] = {"skipped": True}
            _step(stats, "phone", "Mobile Phone", "skipped", "No revealed contacts to look up phones for.")
        else:
            n = len(core_df)
            f_col0, l_col0, d_col0 = phone_cols
            # Job-change force only applies to the existing-contact path (its
            # index aligns with ok_df); discovered contacts have a fresh index.
            phone_force = job_change_idx if needs_existing_mapping else set()
            uncached = apollo_enrich.count_uncached_phones(core_df, f_col0, l_col0, d_col0, force_idx=phone_force)
            est = estimates.cost_block("mobile_phone", uncached)
            phone_answer = ask(
                run_id, "mobile_phone_needed", "yes_no",
                f"Reveal phone numbers for {n} contact(s)? {uncached} need a paid reveal "
                f"(~8 credits each = {est['credits']} credits, ${est['usd']}); {n - uncached} cached (free).",
                default="yes", context={"step": "phone", "estimate": est, "uncached": uncached},
            )
            if _truthy(phone_answer):
                _update(run_id, message="Revealing phone numbers")
                _step(stats, "phone", "Mobile Phone", "running")
                f_col, l_col, d_col = phone_cols
                core_df, phone_stats = apollo_enrich.enrich_phones(
                    core_df, f_col, l_col, d_col, force_idx=phone_force, progress=_make_progress(run_id, "Phone reveal"))
                # Charge on numbers actually revealed (~8 credits each).
                cost = estimates.cost_block("mobile_phone", phone_stats.get("phones_found", 0))
                _accrue_cost(stats, cost)
                stats["apollo_phone"] = phone_stats
                _step(stats, "phone", "Mobile Phone", "done",
                      f"{phone_stats['phones_found']} of {phone_stats['total']} contact(s) have a phone number.",
                      seconds=estimates.estimate_seconds("mobile_phone", n), cost=cost)
            else:
                stats["apollo_phone"] = {"skipped": True}
                _step(stats, "phone", "Mobile Phone", "skipped", "Skipped by user.")
        _update(run_id, stats=dict(stats))

        # Map an existing-contact sheet onto canonical output columns AFTER the
        # optional phone step, so enrich_phones doesn't collide with the
        # "Phone Number" column the mapper would otherwise create.
        if needs_existing_mapping and not core_df.empty:
            core_df = _map_existing_contact_columns(core_df, resolved_first_col, resolved_last_col, resolved_company_col)

        # ============ Step 7: Output Files & Name ============
        suggested_title = naming.suggest_campaign_title(project_meta, ok_df if not ok_df.empty else accounts_processed, region_col)
        campaign_title = ask(
            run_id, "campaign_title", "text",
            "Name this run (used for the campaign tag + HubSpot list). Edit if needed:",
            default=suggested_title, context={"step": "outputs"},
        )
        campaign_title = str(campaign_title).strip() or suggested_title

        _update(run_id, stage=RunStage.assembling_outputs, message="Writing output files")
        _step(stats, "outputs", "Output Files & Name", "running")
        file_paths, hubspot_ready_df = outputs.write_outputs(run_dir, accounts_processed, core_df, campaign_title, stats)
        stats["hubspot_ready_count"] = len(hubspot_ready_df)
        Path(file_paths["SUMMARY.md"]).write_text(outputs.build_summary_markdown(campaign_title, stats, accounts_processed))
        cc = stats.get("channel_counts", {})
        _step(stats, "outputs", "Output Files & Name", "done",
              f"3 channel files written - email {cc.get('email', 0)}, linkedin {cc.get('linkedin', 0)}, calling {cc.get('calling', 0)}.")
        _update(run_id, stats=dict(stats), output_files=list(file_paths.values()))

        # --- Optional PR ---
        pr_url = None
        if config.GITHUB_TOKEN and config.GITHUB_REPO:
            _update(run_id, stage=RunStage.opening_pr, message="Opening PR with output files")
            summary = (
                f"{stats['exclusion'].get('ok_to_reach_out', '?')} OK / {stats['exclusion'].get('excluded', '?')} excluded accounts. "
                f"{stats['hubspot_ready_count']} contacts ready for HubSpot import."
            )
            try:
                pr_url = github_pr.open_output_pr(run_id, campaign_title, file_paths, summary)
            except Exception as e:
                _update(run_id, message=f"Could not open a PR automatically ({e}). Files are still saved locally.")
        hubspot_ready_df.to_json(run_dir / "hubspot_ready.json", orient="records")

        # ============ Step 8: Associations (multi-select) ============
        _step(stats, "associations", "Associations", "running")
        _update(run_id, stats=dict(stats))
        assoc_kinds_answer = ask(
            run_id, "association_types", "multi_choice",
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
            # Auto-populate a searchable dropdown from live HubSpot records.
            _set_message(run_id, f"Loading {kind} records from HubSpot...")
            try:
                records = association_resolve.list_records(kind)
            except Exception:
                records = []

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
                chosen = ask(
                    run_id, f"{kind}_pick", "dropdown",
                    f"Select the {kind} to associate these contacts with (type to filter):",
                    options=options, context={"step": "associations", "kind": kind, "count": len(records)},
                )
                if chosen and chosen != _MANUAL and chosen in option_map:
                    record_id = option_map[chosen]

            # Fallback: no records fetched, or the user chose "Other".
            if record_id is None:
                value = ask(run_id, f"{kind}_value", "text",
                            f"Enter the {kind} name, URL, or record ID:",
                            context={"step": "associations", "kind": kind})
                resolved = association_resolve.resolve(kind, str(value))
                if resolved["status"] == "ambiguous":
                    cands = resolved["candidates"]
                    chosen_name = ask(
                        run_id, f"{kind}_disambiguate", "choice",
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

        _step(stats, "associations", "Associations", "done",
              f"Will associate with: {', '.join(kinds)}." if kinds else "No object association - a static list only.")

        # ============ Step 9: Preview & Upload (await explicit confirm) ============
        _step(stats, "upload", "Preview & Upload", "running", "Review the preview, then confirm to write to HubSpot.")
        _update(
            run_id, _associations=associations, _campaign_title=campaign_title,
            stage=RunStage.awaiting_import_confirmation, pr_url=pr_url, stats=dict(stats),
            message="Ready - review the preview, then confirm to import into HubSpot",
        )

    except Exception as e:
        _update(run_id, stage=RunStage.failed, error=str(e), message="Failed")
        traceback.print_exc()


def run_confirmed_import(run_id: str, run_dir: Path):
    ready_path = run_dir / "hubspot_ready.json"
    df = pd.read_json(ready_path, orient="records")
    # astype(object) first so NaN -> None actually sticks; on a float64 column
    # `.where(..., None)` silently keeps NaN (None can't live in float64), and
    # NaN is not JSON-serializable -> the "Out of range float" upload error.
    rows = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")

    job = get_job(run_id)
    associations = job.get("_associations", [])
    campaign_title = job.get("_campaign_title", f"ABM_WRAPPER_{run_id}")

    # Single canonical path: hard-drops blank emails AND always creates a list.
    result = hubspot_import.import_contacts_with_list(rows, campaign_title, associations)

    # Push the LinkedIn file to HeyReach (best-effort - never sinks the HubSpot
    # import that already succeeded).
    heyreach_result = {"status": "skipped"}
    li_path = run_dir / "linkedin_upload.csv"
    if li_path.exists():
        li_df = pd.read_csv(li_path)
        if not li_df.empty:
            li_df = li_df.where(pd.notna(li_df), None)
            heyreach_result = heyreach.push_leads(li_df.to_dict(orient="records"), campaign_title)
    result["heyreach"] = heyreach_result

    _update(run_id, stage=RunStage.done, message="Imported to HubSpot", hubspot_list_url=result["list"]["list_url"])

    job = get_job(run_id)
    final_stats = {**job["stats"], "hubspot_import": result}
    hr = heyreach_result.get("status")
    hr_note = f" HeyReach: {heyreach_result.get('pushed', 0)} pushed." if hr == "pushed" else ""
    for s in final_stats.get("steps", []):
        if s["key"] == "upload":
            s["status"] = "done"
            if s.get("started_at"):
                s["elapsed_s"] = round(time.time() - s["started_at"], 1)
                s["time"] = estimates.humanize_seconds(s["elapsed_s"])
            s["summary"] = f"Imported {result['total']} contact(s); static list created.{hr_note}"
    _update(run_id, stats=final_stats)

    accounts_processed = pd.read_csv(run_dir / "01_accounts_processed.csv")
    (run_dir / "SUMMARY.md").write_text(
        outputs.build_summary_markdown(campaign_title, final_stats, accounts_processed, import_result=result)
    )
    return result
