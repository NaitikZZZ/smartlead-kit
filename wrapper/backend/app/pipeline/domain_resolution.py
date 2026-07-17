"""Wraps smartlead-kit/scripts/resolve_company_domains.py directly (single
source of truth - not duplicated here) to resolve a company name to a domain,
using the shared persistent cache at reference/company_domain_cache.csv."""
from __future__ import annotations
import sys

import pandas as pd

from .. import config

sys.path.insert(0, str(config.SCRIPTS_DIR))
import resolve_company_domains as _rcd  # noqa: E402
import requests as _requests  # noqa: E402


def resolve_domains_for_df(df: pd.DataFrame, company_col: str, employee_col: str | None):
    session = _requests.Session()
    session.mount("https://", _requests.adapters.HTTPAdapter(max_retries=0))
    cache = _rcd.load_cache()

    domains, countries, cities, sources, ambiguous_rows = [], [], [], [], []
    for _, row in df.iterrows():
        name = row.get(company_col, "")
        emp = row.get(employee_col, "") if employee_col else ""
        res = _rcd.resolve(session, cache, name, emp)
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
    return out, {
        "total": len(out),
        "resolved": resolved,
        "unresolved_or_ambiguous": len(out) - resolved,
        "ambiguous": ambiguous_rows,
    }
