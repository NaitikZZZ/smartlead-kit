"""Auto-extract a target list from a web page (e.g. a "top 100" article linked
in a Project's campaign concept) into account rows the pipeline can enrich.

Best-effort: fetches the page HTML, strips it to text, and asks Claude to pull
out the people/companies as structured JSON. Two backends, in order:
  1. The local Claude CLI (your Claude account/subscription) if it's available
     and logged in - no API key needed, extraction is on your account.
  2. The Anthropic API (ANTHROPIC_API_KEY) if configured.
Falls back to Claude's web_search if the page can't be fetched directly.

Scraped data is auto-extracted and should be reviewed - not a substitute for a
clean CRM export.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess

import pandas as pd
import requests

from .. import config

EXTRACT_MODEL = "claude-sonnet-4-5"
MAX_RECORDS = 500          # hard cap on extracted rows
MAX_OUTPUT_TOKENS = 32000  # ~500 records of JSON fit comfortably
DEFAULT_MAX_CHARS = 200000  # how much page text we feed (~50k tokens)
_SCHEMA_HINT = (
    'Return ONLY JSON of the form {"records":[{"first_name":..,"last_name":..,'
    '"company_name":..,"title":..,"linkedin_url":..}]}. Use null for anything not '
    "present. Do NOT invent entries - only include people/companies actually on the list. "
    f"Include at most {MAX_RECORDS} entries (the first {MAX_RECORDS} if the list is longer). "
    "Output the JSON and nothing else."
)


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _fetch_page_text(url: str, max_chars: int):
    """Returns (text, page_truncated). page_truncated is True if the stripped
    page was longer than max_chars (so some entries may not have been seen)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    try:
        r = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
        if r.ok:
            full = _html_to_text(r.text)
            return full[:max_chars], len(full) > max_chars
    except Exception:
        pass
    return "", False


def _scrape_cache_path(url: str):
    return config.CACHE_DIR / f"scrape_{hashlib.md5(url.encode()).hexdigest()[:12]}.json"


def _load_scrape_cache(url: str) -> dict:
    p = _scrape_cache_path(url)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"records": [], "count": 0, "last_truncated": False}


def _save_scrape_cache(url: str, cache: dict):
    try:
        _scrape_cache_path(url).write_text(json.dumps(cache))
    except Exception:
        pass


def _rec_key(rec: dict) -> str:
    parts = [str(rec.get(k) or "").strip().lower() for k in ("First Name", "Last Name", "Company Name")]
    return "|".join(parts)


def _build_prompt(url: str, concept: str, page_text: str, offset: int = 0, seen_names: list | None = None) -> str:
    resume = ""
    if offset > 0:
        seen_blob = "; ".join((seen_names or [])[:600])
        resume = (
            f"IMPORTANT: the first {offset} entries on this list have ALREADY been processed in a "
            f"previous run. Return the NEXT entries only (continue from position {offset + 1}), up to "
            f"{MAX_RECORDS}. Do NOT include any of these already-processed names: {seen_blob}. "
        )
    if page_text:
        return (
            f"{resume}Extract the people or companies on the list in the web page content below into JSON. "
            f"{_SCHEMA_HINT}\n\nCampaign context: {concept[:500]}\n\nPAGE CONTENT:\n{page_text}"
        )
    return (
        f"{resume}Open {url} (use web fetch/search) and extract the people or companies on that list. "
        f"{_SCHEMA_HINT}\n\nCampaign context: {concept[:500]}"
    )


def _parse_records(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0)).get("records", []) or []
    except json.JSONDecodeError:
        return []


def _extract_via_cli(prompt: str, timeout: int = 300) -> str:
    """Run the local Claude Code CLI headlessly - uses the user's own Claude
    account. Requires the CLI to be present and logged in for this process."""
    execpath = os.environ.get("CLAUDE_CODE_EXECPATH")
    if not execpath or not os.path.exists(execpath):
        raise ValueError("No Claude CLI found and no ANTHROPIC_API_KEY set - can't auto-extract.")
    try:
        proc = subprocess.run(
            [execpath, "-p", prompt, "--allowedTools", "WebFetch,WebSearch"],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:
        raise ValueError(f"Claude CLI call failed: {e}")
    out = (proc.stdout or "").strip()
    if "Not logged in" in out or (proc.returncode != 0 and not out):
        raise ValueError(
            "Your Claude CLI isn't logged in for this process. Run `claude login` in a terminal "
            "(or set ANTHROPIC_API_KEY in the backend .env), then retry."
        )
    return out


def _extract_via_api(prompt: str, use_web_search: bool) -> str:
    from anthropic import Anthropic
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    kwargs = {"model": EXTRACT_MODEL, "max_tokens": MAX_OUTPUT_TOKENS, "messages": [{"role": "user", "content": prompt}]}
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
    resp = client.messages.create(**kwargs)
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")


def scrape_accounts_from_url(url: str, concept: str = "", max_chars: int = DEFAULT_MAX_CHARS):
    """Returns (DataFrame, stats). DataFrame uses the standard headers the
    pipeline understands (First/Last Name, Company Name, Title, Person Linkedin Url).
    Prefers the user's Claude CLI account; falls back to ANTHROPIC_API_KEY.

    Resumable: caps at MAX_RECORDS (500) per run and remembers what was already
    extracted per URL. If a previous run hit the cap, a re-run CONTINUES from the
    next entry (e.g. #501) instead of re-pulling the same 500. A run that got the
    full list (no cap) re-extracts fresh next time. Delete the cache file to reset.

    On failure, saves partial progress so retries resume from checkpoint."""
    cache = _load_scrape_cache(url)
    resume = bool(cache.get("last_truncated")) and cache.get("count", 0) > 0
    prior_records = cache.get("records", []) if resume else []
    offset = len(prior_records)
    seen_keys = {_rec_key(r) for r in prior_records}
    seen_names = [f"{r.get('First Name') or ''} {r.get('Last Name') or ''}".strip() for r in prior_records]

    try:
        page_text, page_truncated = _fetch_page_text(url, max_chars)
        prompt = _build_prompt(url, concept, page_text, offset=offset, seen_names=seen_names)

        if os.environ.get("CLAUDE_CODE_EXECPATH"):
            out_text = _extract_via_cli(prompt)
            method = f"cli:{'page-text' if page_text else 'web'}"
        elif config.ANTHROPIC_API_KEY:
            out_text = _extract_via_api(prompt, use_web_search=not page_text)
            method = f"api:{'page-text' if page_text else 'web-search'}"
        else:
            raise ValueError("Auto-extract needs the Claude CLI (logged in) or ANTHROPIC_API_KEY. Upload the list as CSV instead.")

        new_rows = []
        for rec in _parse_records(out_text):
            if not isinstance(rec, dict):
                continue
            row = {
                "First Name": rec.get("first_name"),
                "Last Name": rec.get("last_name"),
                "Company Name": rec.get("company_name"),
                "Title": rec.get("title"),
                "Person Linkedin Url": rec.get("linkedin_url"),
            }
            if _rec_key(row) in seen_keys:  # skip anything already pulled in prior runs
                continue
            seen_keys.add(_rec_key(row))
            new_rows.append(row)

        hit_cap = len(new_rows) >= MAX_RECORDS
        new_rows = new_rows[:MAX_RECORDS]
        truncated = page_truncated or hit_cap  # there may be still more to fetch next run

        all_records = prior_records + new_rows
        _save_scrape_cache(url, {"records": all_records, "count": len(all_records), "last_truncated": truncated})

        return pd.DataFrame(new_rows), {
            "source_url": url, "scraped": len(new_rows), "method": method,
            "max_records": MAX_RECORDS, "truncated": truncated,
            "resumed": resume, "offset": offset, "total_extracted": len(all_records),
            "checkpoint": f"Cached {len(all_records)} records. Resume from record #{offset + 1} on next run." if truncated else None,
            "truncation_reason": ("page text exceeded input limit" if page_truncated else
                                  (f"hit the {MAX_RECORDS}-record cap" if hit_cap else None)),
        }
    except Exception as e:
        # On any failure, save partial progress so retries resume from checkpoint
        if prior_records:
            _save_scrape_cache(url, {"records": prior_records, "count": len(prior_records), "last_truncated": True})
        raise
