"""Wraps smartlead-kit/scripts/resolve_company_domains.py directly (single
source of truth - not duplicated here) to resolve a company name to a domain,
using the shared persistent cache at reference/company_domain_cache.csv.

Lookups run in a small thread pool (each is an independent, I/O-bound Apollo
call) and stream progress, so a large domain-less list resolves in a fraction
of the sequential time and never looks frozen."""
from __future__ import annotations
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from .._lazy import pd

from .. import config

sys.path.insert(0, str(config.SCRIPTS_DIR))
import resolve_company_domains as _rcd  # noqa: E402
import requests as _requests  # noqa: E402

DEFAULT_WORKERS = 6


def count_uncached(df: pd.DataFrame, company_col: str) -> int:
    """How many companies in df are NOT already in the domain cache. Kept for
    callers that just want a cheap, no-network ceiling; count_needs_apollo
    below is the accurate pre-run cost estimate (it also free-checks
    Clearbit, which resolves a large share of these for free before Apollo
    is ever touched)."""
    cache = _rcd.load_cache()
    n = 0
    for _, row in df.iterrows():
        key = _rcd.norm(str(row.get(company_col, "")).strip())
        if key and key not in cache:
            n += 1
    return n


def count_needs_apollo(df: pd.DataFrame, company_col: str, max_workers: int = DEFAULT_WORKERS) -> int:
    """Accurate pre-run estimate of how many companies would actually cost an
    Apollo credit: not in the domain cache AND Clearbit (checked live, for
    free, in parallel) can't confidently resolve them either. This is what
    the "resolve domains?" cost estimate should show - count_uncached alone
    overstates it, since Clearbit resolves a large share of uncached
    companies for free before Apollo is ever called."""
    cache = _rcd.load_cache()
    names = [str(row.get(company_col, "")).strip() for _, row in df.iterrows()]
    names = [n for n in names if n]
    if not names:
        return 0
    session = _requests.Session()
    session.mount("https://", _requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))
    with ThreadPoolExecutor(max_workers=min(max_workers, len(names))) as ex:
        results = list(ex.map(lambda n: _rcd.estimate_needs_apollo(session, cache, n), names))
    return sum(1 for r in results if r)


def resolve_domains_for_df(df: pd.DataFrame, company_col: str, employee_col: str | None,
                           progress=None, max_workers: int = DEFAULT_WORKERS):
    session = _requests.Session()
    session.mount("https://", _requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=max_workers))
    cache = _rcd.load_cache()

    rows = list(df.iterrows())
    total = len(rows)
    results: dict = {}
    lock = threading.Lock()
    counter = {"done": 0}

    def work(item):
        idx, row = item
        name = row.get(company_col, "")
        emp = row.get(employee_col, "") if employee_col else ""
        res = _rcd.resolve(session, cache, name, emp)  # cache reads only; writes happen after join
        with lock:
            counter["done"] += 1
            done = counter["done"]
        if progress:
            try:
                progress(done, total, str(name))
            except Exception:
                pass
        return idx, name, res

    if total:
        with ThreadPoolExecutor(max_workers=min(max_workers, total)) as ex:
            for idx, name, res in ex.map(work, rows):
                results[idx] = (name, res)

    domains, countries, cities, sources, ambiguous_rows = [], [], [], [], []
    for idx, _row in rows:
        name, res = results[idx]
        domains.append(res["domain"])
        countries.append(res.get("country", ""))
        cities.append(res.get("city", ""))
        sources.append(res["source"])
        if not res["domain"]:
            ambiguous_rows.append({"company": name, "reason": res["source"], "candidates": res.get("candidates", [])})
        if res["domain"] and res["source"] != "Cache":
            key = _rcd.norm(str(name).strip())
            cache[key] = {
                "company_key": key, "company_name": name, "domain": res["domain"],
                "linkedin": res.get("linkedin", ""), "country": res.get("country", ""),
                "city": res.get("city", ""), "source": res["source"], "notes": "",
            }

    _rcd.save_cache(cache)

    out = df.copy()
    out["Domain"] = domains
    out["Resolved Country"] = countries
    out["Resolved City"] = cities
    out["Domain Resolution Source"] = sources

    resolved = sum(1 for d in domains if d)
    from_apollo = sum(1 for d, s in zip(domains, sources) if d and s.startswith("Apollo"))
    from_clearbit = sum(1 for d, s in zip(domains, sources) if d and s.startswith("Clearbit"))
    return out, {
        "total": len(out),
        "resolved": resolved,
        "from_apollo": from_apollo,
        "from_clearbit": from_clearbit,
        "unresolved_or_ambiguous": len(out) - resolved,
        "ambiguous": ambiguous_rows,
    }
