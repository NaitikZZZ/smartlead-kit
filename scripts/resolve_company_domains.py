"""
Resolve company domains for a prospect list, with a persistent cache and
employee-count cross-checking to reduce wrong-company matches.

Usage:
    python3 resolve_company_domains.py <input_csv> <company_col> <employee_col> <output_json>

Reads/writes the shared cache at reference/company_domain_cache.csv so companies
resolved once are instant and correct on every future list.

Matching logic per company:
  1. Check the cache first (normalized name match). If found, done - no API call.
  2. Otherwise query Apollo org search, keep only candidates whose normalized
     name exactly equals the query (same as before).
  3. If exactly one exact-name candidate: accept it.
  4. If multiple exact-name candidates: rank by closeness of estimated_num_employees
     to the source list's employee count (parsed from free text like "~1,200",
     "~500-1,000", "1-10"). Pick the closest; if the gap between the best and
     second-best candidate is small (ambiguous), flag for manual review instead
     of guessing.
  5. If zero exact-name candidates: mark Unresolved for manual/web-search follow-up.

Confirmed resolutions (any source) get written back to the cache.
"""
import os
import re
import sys
import csv
import json
import time
import requests
from collections import Counter
from dotenv import load_dotenv

load_dotenv()
APOLLO_KEY = os.environ.get('APOLLO_API_KEY')
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'reference', 'company_domain_cache.csv')

CACHE_FIELDS = ['company_key', 'company_name', 'domain', 'linkedin', 'source', 'notes']


_LEGAL_SUFFIX_RE = re.compile(
    r'[,]?\s*\(?\b(incorporated|corporation|company|limited|pte\.?\s*ltd\.?|pty\.?\s*ltd\.?|'
    r'p\.?\s*ltd\.?|inc\.?|llc\.?|ltd\.?|corp\.?|plc\.?|gmbh\.?|co\.?)\)?\.?\s*$',
    re.IGNORECASE,
)
# Catches the dangling "(P)" left behind after "Ltd" strips from "X (P) Ltd"
# (Indian/Asian "Private Limited" shorthand) - "(P)" and "Ltd" are two
# separate tokens, not one atomic suffix, so the main regex above only gets
# the second one in a single pass.
_DANGLING_PAREN_RE = re.compile(r'\(\s*(p|pvt|pte)\s*\)\s*$', re.IGNORECASE)


def strip_legal_suffix(s):
    """Strip trailing legal-entity suffixes so 'Aetna' matches Apollo's
    'Aetna Inc.' record instead of missing it entirely. Loops to catch
    chained suffixes/punctuation (e.g. 'Elevance Health, Inc..')."""
    s = str(s).strip()
    prev = None
    while prev != s:
        prev = s
        s = _LEGAL_SUFFIX_RE.sub('', s).strip().rstrip(',.').strip()
        s = _DANGLING_PAREN_RE.sub('', s).strip().rstrip(',.').strip()
    return s


def norm(s):
    return ''.join(ch for ch in strip_legal_suffix(s).lower() if ch.isalnum())


def parse_employee_count(raw):
    """'~1,200' -> 1200; '~500-1,000' -> 750; '1-10' -> 5; '' -> None"""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.replace('~', '').replace('+', '').replace(',', '').strip()
    s = s.replace('–', '-').replace('—', '-')  # en/em dash
    parts = re.findall(r'\d+', s)
    if not parts:
        return None
    nums = [int(p) for p in parts]
    return sum(nums) / len(nums)


def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, newline='', encoding='utf-8') as f:
        return {row['company_key']: row for row in csv.DictReader(f)}


def save_cache(cache):
    with open(CACHE_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        w.writeheader()
        for row in cache.values():
            w.writerow({k: row.get(k, '') for k in CACHE_FIELDS})


def apollo_search(session, query_name):
    try:
        r = session.post(
            'https://api.apollo.io/api/v1/mixed_companies/search',
            headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'x-api-key': APOLLO_KEY},
            json={'q_organization_name': query_name, 'page': 1, 'per_page': 25},
            timeout=(5, 10),
        )
        data = r.json()
        return data.get('accounts', []) + data.get('organizations', [])
    except Exception:
        return []


def resolve(session, cache, company_name, employee_raw):
    # Full name first - most accurate. Only fall back to a '/' split for
    # genuine dual-listings like "Channel 4 / Superstruct Entertainment".
    # Never split on '&' - it's commonly part of a real single company name
    # (e.g. "Dock & Bay", "Armstrong & Partners") and truncating it produced
    # a wrong-company match in testing (Dock & Bay -> "Dock" -> dock.tech).
    full_name = str(company_name).strip()
    key = norm(full_name)
    if key in cache:
        c = cache[key]
        return {'domain': c['domain'], 'linkedin': c['linkedin'], 'source': 'Cache', 'candidates': []}
    slash_key = norm(full_name.split('/')[0].strip())
    if slash_key != key and slash_key in cache:
        c = cache[slash_key]
        return {'domain': c['domain'], 'linkedin': c['linkedin'], 'source': 'Cache', 'candidates': []}

    query_candidates = [full_name]
    if '/' in full_name:
        query_candidates.append(full_name.split('/')[0].strip())

    accounts, qn, query_name = [], norm(full_name), full_name
    for q in query_candidates:
        accounts = apollo_search(session, q)
        qn = norm(q)
        query_name = q
        if any(norm(a.get('name', '')) == qn and a.get('primary_domain') for a in accounts):
            break  # found an exact match on this query variant, stop trying looser ones

    exact = [a for a in accounts if norm(a.get('name', '')) == qn and a.get('primary_domain')]

    if not exact:
        cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'linkedin': a.get('linkedin_url')} for a in accounts[:3]]
        return {'domain': '', 'linkedin': '', 'source': 'Unresolved', 'candidates': cands}

    if len(exact) == 1:
        best = exact[0]
        result_source = 'Apollo-exact'
    elif Counter(a.get('primary_domain') for a in exact).most_common(1)[0][1] > len(exact) / 2:
        # Multiple Apollo records can exist for the same real company -
        # duplicate/fragmented org entries with identical display names
        # (seen a lot with large multinationals: regional subsidiaries all
        # named e.g. "Ernst & Young"). That's database noise, not real
        # ambiguity. If a clear majority of the exact-name candidates
        # already agree on one domain, trust it instead of flagging - only
        # flag when the candidates genuinely disagree on domain.
        top_domain = Counter(a.get('primary_domain') for a in exact).most_common(1)[0][0]
        best = next(a for a in exact if a.get('primary_domain') == top_domain)
        result_source = 'Apollo-exact-majority-domain'
    else:
        target_emp = parse_employee_count(employee_raw)
        if target_emp is None:
            # No employee signal to disambiguate - flag instead of guessing
            cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'employees': a.get('estimated_num_employees')} for a in exact]
            return {'domain': '', 'linkedin': '', 'source': 'Ambiguous - multiple exact-name matches, no employee signal', 'candidates': cands}

        with_emp = [a for a in exact if a.get('estimated_num_employees') is not None]
        if not with_emp:
            # None of the exact-name candidates carry employee data - there's
            # nothing to rank on. Flag rather than silently taking the first
            # result (that's the exact bug that let "Flip" resolve to the
            # wrong company before: all 3 candidates had employees=None, and
            # picking "first in Apollo's list" is not a real signal).
            cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'employees': None} for a in exact]
            return {'domain': '', 'linkedin': '', 'source': 'Ambiguous - multiple exact-name matches, none have employee data', 'candidates': cands}

        def gap(a):
            return abs(a.get('estimated_num_employees') - target_emp) / max(target_emp, 1)

        ranked = sorted(with_emp, key=gap)
        best, second = ranked[0], ranked[1] if len(ranked) > 1 else None
        if second is not None and gap(best) > 0.5 and abs(gap(best) - gap(second)) < 0.15:
            cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'employees': a.get('estimated_num_employees')} for a in ranked]
            return {'domain': '', 'linkedin': '', 'source': 'Ambiguous - employee count did not clearly disambiguate', 'candidates': cands}
        result_source = 'Apollo-exact-employee-ranked'

    return {
        'domain': best.get('primary_domain', ''),
        'linkedin': best.get('linkedin_url', ''),
        'source': result_source,
        'candidates': [],
    }


def main():
    input_csv, company_col, employee_col, output_json = sys.argv[1:5]

    import pandas as pd
    df = pd.read_csv(input_csv)
    companies = df[[company_col, employee_col]].drop_duplicates(subset=[company_col])

    cache = load_cache()
    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    results = {}
    new_cache_entries = 0
    for i, row in companies.iterrows():
        name = row[company_col]
        emp = row[employee_col]
        res = resolve(session, cache, name, emp)
        results[name] = res
        if res['domain'] and res['source'] != 'Cache':
            key = norm(str(name).strip())
            cache[key] = {
                'company_key': key, 'company_name': name, 'domain': res['domain'],
                'linkedin': res['linkedin'], 'source': res['source'], 'notes': ''
            }
            new_cache_entries += 1
        print(f"{name} -> {res['source']}: {res['domain']}", flush=True)
        if res['source'] != 'Cache':
            time.sleep(0.2)

    save_cache(cache)
    with open(output_json, 'w') as f:
        json.dump(results, f, indent=2)

    from_cache = sum(1 for r in results.values() if r['source'] == 'Cache')
    resolved = sum(1 for r in results.values() if r['domain'])
    print(f"\n{len(results)} companies: {from_cache} from cache, {resolved} total resolved, "
          f"{len(results) - resolved} unresolved/ambiguous. {new_cache_entries} new cache entries saved.")


if __name__ == '__main__':
    main()
