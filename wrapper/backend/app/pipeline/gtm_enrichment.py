"""Read-only GTM enrichment computed on top of already-enriched account data:
competitor match (against the attached Xoxoday competitor list) and partner
tech-stack match (against Xoxoday's real HubSpot Partner object, including
which product gets pitched through each matched partner). Never writes to
HubSpot or Apollo, and never blocks the run on failure - same "best-effort"
resilience pattern as web_completeness.py and the dream-accounts lookup this
sits next to in runner.py.

This is the in-pipeline port of the standalone scripts/apollo_gtm_columns.py +
scripts/hubspot_partner_list.py (see those for the original build/verification
notes - the matching rules below (short-alias exact-match, generic-word
denylist, per-tech-entry not whole-blob matching) were tuned against real
data 2026-09-15/16 and should not be "simplified" without re-checking that
work: an earlier, naive whole-blob-substring version produced false positives
like a partner named "ADA" matching the unrelated "Ada" chatbot product
inside a lead's tech stack).

Does NOT touch app/pipeline/association_resolve.py's cached {id, name}
partner dropdown list (used for the Associations step) - this needs three
extra properties (partner_type, partner_status, product_partner_interested)
that dropdown cache doesn't carry, so it fetches its own copy rather than
risk changing that cache's shape.
"""
from __future__ import annotations
import csv
import os
import re

import requests

from .. import config, redis_cache

COMPETITOR_LIST_PATH = os.environ.get(
    "COMPETITOR_LIST_PATH",
    os.path.expanduser("~/Documents/Xoxoday/Xoxoday Competition(Final Competition list).csv"),
)
# Local absolute path only works for local dev runs - Vercel's filesystem
# doesn't have it. Production instead reads the same rows from Redis
# (config below), seeded once via refresh_competitor_cache() and re-run
# manually whenever the competitor list changes (it's small/static enough
# - 531 rows, ~78KB - that a cron refresh like the association dropdowns
# get would be overkill). Falls back to the local file if Redis has no
# cached copy yet (e.g. this hasn't been seeded), so local dev keeps
# working unchanged either way.
_COMPETITOR_REDIS_KEY = "cache:gtm_competitor_list"

_EXCLUDED_STATUSES = {"Prospect", "Denied/Terminated", "Passive"}
_EXCLUDED_TYPES = {"Individual"}
_GENERIC_WORD_DENYLIST = {"engage", "remote", "ada"}
_PAREN_RE = re.compile(r"\([^)]*\)")
_SHORT_ALIAS_LEN = 5


def _norm_alnum(text) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def normalize_domain(value) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    return v.split("/")[0].strip()


def _rows_to_domain_map(rows: list[dict]) -> dict:
    by_domain: dict = {}
    for row in rows:
        domain = normalize_domain(row.get("Website", ""))
        if domain:
            by_domain.setdefault(domain, []).append(row)
    return by_domain


def refresh_competitor_cache(path: str = COMPETITOR_LIST_PATH) -> int:
    """One-time (re-run whenever the competitor list changes) seed of Redis
    from the local CSV. Returns the row count cached. Raises if the local
    file isn't present or Redis isn't configured - this is a deliberate
    maintenance action, not something that should fail silently."""
    if not redis_cache.is_configured():
        raise RuntimeError("Redis isn't configured (UPSTASH_REDIS_REST_URL/TOKEN) - nothing to seed.")
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Competitor list not found at {path!r}")
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    redis_cache.set_json(_COMPETITOR_REDIS_KEY, rows)
    return len(rows)


def load_competitors(path: str = COMPETITOR_LIST_PATH) -> dict:
    """domain -> list of competitor rows. Tries the Redis-cached copy first
    (works on Vercel), falls back to the local file (works for local dev
    even before the cache is ever seeded). Returns {} (not an error) if
    neither is available - callers treat that as "competitor matching
    skipped", never a hard failure."""
    if redis_cache.is_configured():
        try:
            cached = redis_cache.get_json(_COMPETITOR_REDIS_KEY)
        except Exception:
            cached = None
        if cached:
            return _rows_to_domain_map(cached)
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    return _rows_to_domain_map(rows)


def _read_headers():
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _is_junk_partner_name(name: str) -> bool:
    if not name:
        return True
    low = name.lower()
    return ("test" in low or "demo" in low or low.startswith("epic digital")
            or low.startswith("epic joanna") or low.startswith("old -"))


def fetch_partners() -> list[dict]:
    """Read-only fetch of every record on Xoxoday's HubSpot Partner object
    (config.HUBSPOT_PARTNER_OBJECT), with the 3 properties needed for
    tech-stack matching that the Associations dropdown cache doesn't carry.
    ~295 records as of 2026-09-16 (3 paginated calls) - fetched fresh per
    run rather than cached, since that's fast enough not to need it yet."""
    props = ["partner_name", "partner_type", "partner_status", "product_partner_interested"]
    out: list[dict] = []
    after = None
    while True:
        params = {"limit": 100, "properties": ",".join(props)}
        if after:
            params["after"] = after
        r = requests.get(f"https://api.hubapi.com/crm/v3/objects/{config.HUBSPOT_PARTNER_OBJECT}",
                          headers=_read_headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("results", []):
            p = rec.get("properties", {})
            name = (p.get("partner_name") or "").strip()
            if _is_junk_partner_name(name):
                continue
            products_raw = (p.get("product_partner_interested") or "").strip()
            products = [x.strip() for x in products_raw.split(";") if x.strip()] if products_raw else []
            out.append({"name": name, "type": p.get("partner_type"), "status": p.get("partner_status"),
                        "products": products})
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return out


def build_partner_alias_map(partners: list[dict] | None = None) -> dict:
    """display_name -> {'aliases': [...], 'products': set(...)}."""
    partners = partners if partners is not None else fetch_partners()
    alias_map: dict = {}
    seen_norms: dict = {}
    for p in partners:
        if p["type"] in _EXCLUDED_TYPES or p["status"] in _EXCLUDED_STATUSES:
            continue
        name = _PAREN_RE.sub("", p["name"]).strip()
        norm = _norm_alnum(name)
        if len(norm) < 3 or norm in _GENERIC_WORD_DENYLIST:
            continue
        display = seen_norms.setdefault(norm, name)
        entry = alias_map.setdefault(display, {"aliases": [], "products": set()})
        entry["aliases"].append(norm)
        entry["products"].update(p["products"])
    return alias_map


def match_partner_tech(tech_value, alias_map: dict) -> tuple[str, str]:
    """Returns (matched_partner_names_str, suggested_products_str)."""
    if not tech_value:
        return "", ""
    entries = [_norm_alnum(e) for e in str(tech_value).split(",") if e.strip()]
    if not entries:
        return "", ""
    matched, products = [], set()
    for name, entry in alias_map.items():
        for alias in entry["aliases"]:
            hit = (any(alias == e for e in entries) if len(alias) < _SHORT_ALIAS_LEN
                   else any(alias in e for e in entries))
            if hit:
                matched.append(name)
                products.update(entry["products"])
                break
    return ", ".join(matched), ", ".join(sorted(products))


def enrich(df, domain_col: str = "Domain", tech_col: str = "technologies"):
    """Adds Competitor Match/Name/Threat/Products and Partner Tech
    Match/Suggested Products columns to df (a copy). Returns (df, stats).
    Never raises - on any failure, returns df unchanged plus an error note,
    matching web_completeness.fill_completeness_gaps's contract."""
    out = df.copy()
    stats = {"competitor_matches": 0, "partner_tech_matches": 0}

    try:
        competitors = load_competitors()
        stats["competitor_list_loaded"] = bool(competitors)
    except Exception as e:
        competitors = {}
        stats["competitor_error"] = str(e)

    try:
        alias_map = build_partner_alias_map()
        stats["partner_count"] = len(alias_map)
    except Exception as e:
        alias_map = {}
        stats["partner_error"] = str(e)

    comp_match, comp_name, comp_threat, comp_products = [], [], [], []
    tech_match, tech_products = [], []
    for _, row in out.iterrows():
        domain = normalize_domain(row.get(domain_col, "")) if domain_col in out.columns else ""
        rows = competitors.get(domain, [])
        if rows:
            stats["competitor_matches"] += 1
            best = rows[0]
            comp_match.append("Yes")
            comp_name.append(best.get("Name", ""))
            comp_threat.append(best.get("Threat", ""))
            comp_products.append(best.get("Products", ""))
        else:
            comp_match.append("No")
            comp_name.append("")
            comp_threat.append("")
            comp_products.append("")

        tv = row.get(tech_col, "") if tech_col in out.columns else ""
        m, p = match_partner_tech(tv, alias_map)
        tech_match.append(m)
        tech_products.append(p)
        if m:
            stats["partner_tech_matches"] += 1

    out["Competitor Match"] = comp_match
    out["Competitor Name"] = comp_name
    out["Competitor Threat"] = comp_threat
    out["Competitor Products"] = comp_products
    out["Partner Tech Match"] = tech_match
    out["Partner Suggested Products"] = tech_products
    return out, stats
