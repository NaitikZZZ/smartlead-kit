"""
Resolve company domains for a prospect list, with a persistent cache and
employee-count cross-checking to reduce wrong-company matches.

Usage:
    python3 resolve_company_domains.py <input_csv> <company_col> <employee_col> <output_json>

Reads/writes the shared cache at reference/company_domain_cache.csv so companies
resolved once are instant and correct on every future list.

Matching logic per company:
  1. Check the cache first (normalized name match). If found, done - no API call.
  2. Try Clearbit's free Autocomplete API first (no key needed, no cost) -
     exact-name match only; a lone .com among several exact matches is
     accepted as confident, otherwise it's treated as a weak guess.
  3. If Clearbit gave a confident answer: accept it, skip Apollo entirely
     (saves the credit). Otherwise (Clearbit empty, or only a weak guess),
     query Apollo org search (paid), keep only candidates whose normalized
     name exactly equals the query.
  4. If exactly one Apollo exact-name candidate: accept it.
  5. If multiple: rank by closeness of estimated_num_employees to the source
     list's employee count (parsed from free text like "~1,200", "~500-1,000",
     "1-10"). Pick the closest; if the gap between the best and second-best
     candidate is small (ambiguous), flag for manual review instead of guessing.
  6. If Apollo also has zero exact-name candidates: fall back to Clearbit's
     weak guess from step 2, if it had one. Apollo's org database skews
     B2B/SaaS and is frequently blank for small/local businesses (confirmed:
     a real ~700-company wedding-vendor list only resolved ~95 via Apollo alone).
  7. Still nothing: mark Unresolved for manual/web-search follow-up.

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

CACHE_FIELDS = ['company_key', 'company_name', 'domain', 'linkedin', 'country', 'city', 'source', 'notes']

# Redis (Upstash REST) is used when configured - required on Vercel, where the
# local CSV file above isn't writable/persistent across invocations. Falls
# back to the CSV file when Redis isn't configured, so this script still runs
# standalone (e.g. via the manual CLAUDE.md pipeline) without any new setup.
_REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
_REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
_REDIS_KEY = 'cache:company_domain'


def _redis_configured():
    return bool(_REDIS_URL and _REDIS_TOKEN)


def _redis_get_json(key):
    r = requests.get(f'{_REDIS_URL}/get/{key}', headers={'Authorization': f'Bearer {_REDIS_TOKEN}'}, timeout=15)
    r.raise_for_status()
    raw = r.json().get('result')
    return json.loads(raw) if raw is not None else None


def _redis_set_json(key, value):
    r = requests.post(f'{_REDIS_URL}/set/{key}', headers={'Authorization': f'Bearer {_REDIS_TOKEN}'},
                       data=json.dumps(value).encode('utf-8'), timeout=15)
    r.raise_for_status()


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
    if _redis_configured():
        return _redis_get_json(_REDIS_KEY) or {}
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, newline='', encoding='utf-8') as f:
        return {row['company_key']: row for row in csv.DictReader(f)}


def save_cache(cache):
    if _redis_configured():
        _redis_set_json(_REDIS_KEY, cache)
        return
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


# Apollo's org database skews B2B/SaaS - it's frequently blank for small or
# local businesses (confirmed: a real ~700-company wedding-vendor list only
# resolved ~95 via Apollo alone). Clearbit's Autocomplete endpoint is free,
# needs no API key/account, and covers a much wider long-tail of company
# names - used here as a second-tier fallback before giving up.
CLEARBIT_AUTOCOMPLETE_URL = 'https://autocomplete.clearbit.com/v1/companies/suggest'


def clearbit_search(session, query_name):
    try:
        r = session.get(CLEARBIT_AUTOCOMPLETE_URL, params={'query': query_name}, timeout=(5, 10))
        return r.json() if r.ok else []
    except Exception:
        return []


def clearbit_resolve(session, query_candidates, qn_final):
    """Same exact-name-match philosophy as Apollo: only accept a Clearbit
    suggestion whose normalized name equals the query. Clearbit doesn't
    expose employee counts, so multiple exact-name matches can't be ranked
    the same way Apollo's are - prefer a lone .com among them (the common
    case for the real company vs. regional/unrelated same-named ones seen in
    testing, e.g. multiple "Klarna" entries where only one is klarna.com),
    otherwise take Clearbit's own top-ranked suggestion rather than guess
    further. Returns (best_or_None, source_label, candidates_for_review)."""
    for q in query_candidates:
        suggestions = clearbit_search(session, q)
        qn = norm(q)
        exact = [s for s in suggestions if norm(s.get('name', '')) == qn and s.get('domain')]
        if not exact:
            continue
        if len(exact) == 1:
            return exact[0], 'Clearbit-exact', []
        com_only = [s for s in exact if str(s.get('domain', '')).endswith('.com')]
        if len(com_only) == 1:
            return com_only[0], 'Clearbit-exact-com-preferred', []
        return exact[0], 'Clearbit-exact-top-ranked', []
    return None, None, []


def geo_of(account):
    """HQ country/city, preferring the firmographic organization_* fields
    over the account-record's own address override (a CRM-synced account can
    carry a different, contact-specific address in city/country)."""
    return account.get('organization_country') or account.get('country') or '', \
        account.get('organization_city') or account.get('city') or ''


def build_query_candidates(company_name):
    """Same query-variant construction resolve() and the free Clearbit
    precheck (estimate_needs_apollo) both use, so the estimate checks
    Clearbit with the exact same candidates the real resolve will - full
    name first, a '/' split for genuine dual-listings like "Channel 4 /
    Superstruct Entertainment", then the legal-suffix-stripped form."""
    full_name = str(company_name).strip()
    query_candidates = [full_name]
    if '/' in full_name:
        query_candidates.append(full_name.split('/')[0].strip())
    stripped = strip_legal_suffix(full_name)
    if stripped and stripped not in query_candidates:
        # A literal-ish match isn't fuzzy - "Klarna Bank AB" returns zero
        # results even though "Klarna" (the record's actual stored name) is
        # right there. Retrying with the suffix stripped recovers these
        # instead of flagging every non-English legal-entity name Unresolved.
        query_candidates.append(stripped)
    return query_candidates


def estimate_needs_apollo(session, cache, company_name):
    """Free pre-check (Clearbit only, no Apollo) for whether this company
    would actually cost an Apollo credit in resolve() below - i.e. it's not
    already cached AND Clearbit can't confidently resolve it either. Exists
    so the pre-run cost estimate shown to the user reflects what will really
    get charged, instead of assuming every uncached company needs Apollo and
    ignoring that Clearbit resolves a large share of them for free. Repeats
    the same free Clearbit call resolve() will make rather than caching the
    verdict here, to avoid a second, possibly-stale place tracking it."""
    key = norm(str(company_name).strip())
    if key in cache:
        return False
    query_candidates = build_query_candidates(company_name)
    cb_best, cb_source, _ = clearbit_resolve(session, query_candidates, norm(query_candidates[-1]))
    return not (cb_best and cb_source != 'Clearbit-exact-top-ranked')


def resolve(session, cache, company_name, employee_raw):
    # Full name first - most accurate. Never split on '&' - it's commonly
    # part of a real single company name (e.g. "Dock & Bay", "Armstrong &
    # Partners") and truncating it produced a wrong-company match in testing
    # (Dock & Bay -> "Dock" -> dock.tech).
    full_name = str(company_name).strip()
    key = norm(full_name)
    if key in cache:
        c = cache[key]
        return {'domain': c['domain'], 'linkedin': c['linkedin'], 'country': c.get('country', ''), 'city': c.get('city', ''), 'source': 'Cache', 'candidates': []}
    slash_key = norm(full_name.split('/')[0].strip())
    if slash_key != key and slash_key in cache:
        c = cache[slash_key]
        return {'domain': c['domain'], 'linkedin': c['linkedin'], 'country': c.get('country', ''), 'city': c.get('city', ''), 'source': 'Cache', 'candidates': []}

    query_candidates = build_query_candidates(full_name)

    # Clearbit first - it's free, so try it before spending an Apollo credit.
    # Only trust it outright when confident (a single exact match, or a lone
    # .com among several); its weaker "top-ranked guess among multiple .coms"
    # tier falls through to Apollo, which can actually disambiguate via
    # employee count instead of guessing.
    cb_best, cb_source, _ = clearbit_resolve(session, query_candidates, norm(query_candidates[-1]))
    if cb_best and cb_source != 'Clearbit-exact-top-ranked':
        return {
            'domain': cb_best.get('domain', ''), 'linkedin': '', 'country': '', 'city': '',
            'source': cb_source, 'candidates': [],
        }

    accounts, qn, query_name = [], norm(full_name), full_name
    for q in query_candidates:
        accounts = apollo_search(session, q)
        qn = norm(q)
        query_name = q
        if any(norm(a.get('name', '')) == qn and a.get('primary_domain') for a in accounts):
            break  # found an exact match on this query variant, stop trying looser ones

    exact = [a for a in accounts if norm(a.get('name', '')) == qn and a.get('primary_domain')]

    if not exact:
        # Apollo also has no exact-name hit (common for small/local businesses
        # its B2B-oriented database doesn't track) - fall back to Clearbit's
        # weaker top-ranked guess if it had one, rather than nothing at all.
        if cb_best:
            return {
                'domain': cb_best.get('domain', ''), 'linkedin': '', 'country': '', 'city': '',
                'source': cb_source, 'candidates': [],
            }
        cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'linkedin': a.get('linkedin_url')} for a in accounts[:3]]
        return {'domain': '', 'linkedin': '', 'country': '', 'city': '', 'source': 'Unresolved', 'candidates': cands}

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
            return {'domain': '', 'linkedin': '', 'country': '', 'city': '', 'source': 'Ambiguous - multiple exact-name matches, no employee signal', 'candidates': cands}

        with_emp = [a for a in exact if a.get('estimated_num_employees') is not None]
        if not with_emp:
            # None of the exact-name candidates carry employee data - there's
            # nothing to rank on. Flag rather than silently taking the first
            # result (that's the exact bug that let "Flip" resolve to the
            # wrong company before: all 3 candidates had employees=None, and
            # picking "first in Apollo's list" is not a real signal).
            cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'employees': None} for a in exact]
            return {'domain': '', 'linkedin': '', 'country': '', 'city': '', 'source': 'Ambiguous - multiple exact-name matches, none have employee data', 'candidates': cands}

        def gap(a):
            return abs(a.get('estimated_num_employees') - target_emp) / max(target_emp, 1)

        ranked = sorted(with_emp, key=gap)
        best, second = ranked[0], ranked[1] if len(ranked) > 1 else None
        if second is not None and gap(best) > 0.5 and abs(gap(best) - gap(second)) < 0.15:
            cands = [{'name': a.get('name'), 'domain': a.get('primary_domain'), 'employees': a.get('estimated_num_employees')} for a in ranked]
            return {'domain': '', 'linkedin': '', 'country': '', 'city': '', 'source': 'Ambiguous - employee count did not clearly disambiguate', 'candidates': cands}
        result_source = 'Apollo-exact-employee-ranked'

    country, city = geo_of(best)
    return {
        'domain': best.get('primary_domain', ''),
        'linkedin': best.get('linkedin_url', ''),
        'country': country,
        'city': city,
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
                'linkedin': res['linkedin'], 'country': res.get('country', ''), 'city': res.get('city', ''),
                'source': res['source'], 'notes': ''
            }
            new_cache_entries += 1
        print(f"{name} -> {res['source']}: {res['domain']} ({res.get('country','')})", flush=True)
        if res['source'] != 'Cache':
            time.sleep(0.2)

    save_cache(cache)
    with open(output_json, 'w') as f:
        json.dump(results, f, indent=2)

    from_cache = sum(1 for r in results.values() if r['source'] == 'Cache')
    from_apollo = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Apollo'))
    from_clearbit = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Clearbit'))
    resolved = sum(1 for r in results.values() if r['domain'])
    print(f"\n{len(results)} companies: {from_cache} from cache, {from_apollo} via Apollo, "
          f"{from_clearbit} via Clearbit fallback, {resolved} total resolved, "
          f"{len(results) - resolved} unresolved/ambiguous. {new_cache_entries} new cache entries saved.")


if __name__ == '__main__':
    main()
