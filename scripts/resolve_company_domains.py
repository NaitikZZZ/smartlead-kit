"""
Resolve company domains for a prospect list, with a persistent cache and
employee-count cross-checking to reduce wrong-company matches.

Usage:
    python3 resolve_company_domains.py <input_csv> <company_col> <employee_col> <output_json>

Reads/writes the shared cache at reference/company_domain_cache.csv so companies
resolved once are instant and correct on every future list.

Matching logic per company (see try_free_tiers() for the free-tier chain):
  1. Check the cache first (normalized name match). If found, done - no API
     call. Seed this cache once, for free, from your own saved Apollo
     Accounts via apollo_export_accounts_to_cache.py - see that script's
     docstring; it's a different, uncredited Apollo endpoint from the paid
     org search used in step 4 below.
  2. HubSpot Company search (free, read-only, needs HUBSPOT_PRIVATE_APP_TOKEN
     or HUBSPOT_API_KEY) - your own team's verified data, so trusted first.
  3. Clearbit's free Autocomplete API (no key needed) - exact-name match
     only; a lone .com among several exact matches is accepted as confident,
     otherwise it's treated as a weak guess (not trusted here - see step 6).
  4. Brandfetch Brand Search API (free tier, needs BRANDFETCH_API_KEY - skipped
     silently if unset) - same exact-name-match philosophy.
  5. Wikidata (free, keyless) - only covers companies notable enough to carry
     an "official website" (P856) claim; strong for large/public companies,
     near-blank for small/private ones.
  6. If none of the above are confident: query Apollo org search (paid, 1
     credit/page - v1/mixed_companies/search), keep only candidates whose
     normalized name exactly equals the query.
  7. If exactly one Apollo exact-name candidate: accept it.
  8. If multiple: rank by closeness of estimated_num_employees to the source
     list's employee count (parsed from free text like "~1,200", "~500-1,000",
     "1-10"). Pick the closest; if the gap between the best and second-best
     candidate is small (ambiguous), flag for manual review instead of guessing.
  9. If Apollo also has zero exact-name candidates: fall back to Clearbit's
     weak guess from step 3, if it had one. Apollo's org database skews
     B2B/SaaS and is frequently blank for small/local businesses (confirmed:
     a real ~700-company wedding-vendor list only resolved ~95 via Apollo alone).
  10. Still nothing: mark Unresolved for manual/web-search follow-up (the
      wrapper backend's runner.py has one more tier after this: a Claude
      web-search pass in web_completeness.py, best-effort, ANTHROPIC_API_KEY-gated).

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
# Two different .env conventions exist in this repo (root .env uses
# HUBSPOT_API_KEY, wrapper/backend/.env uses HUBSPOT_PRIVATE_APP_TOKEN) since
# this script runs standalone under both - accept either.
HUBSPOT_TOKEN = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or os.environ.get('HUBSPOT_API_KEY')
# Optional - these tiers are silently skipped (never block resolution) if unset.
BRANDFETCH_API_KEY = os.environ.get('BRANDFETCH_API_KEY')
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'reference', 'company_domain_cache.csv')

CACHE_FIELDS = ['company_key', 'company_name', 'domain', 'linkedin', 'country', 'city', 'source', 'notes']

# Redis (Upstash REST) is used when configured - required on Vercel, where the
# local CSV file above isn't writable/persistent across invocations. Falls
# back to the CSV file when Redis isn't configured, so this script still runs
# standalone (e.g. via the manual CLAUDE.md pipeline) without any new setup.
#
# Stored as a Redis HASH (one field per company), not a single JSON-blob
# STRING under one key - confirmed live (2026-09-01): writing the whole
# ~290k-company cache as one JSON string silently failed (the SET never took;
# production's key stayed at its pre-write 2,567-company size) once the blob
# grew large enough, almost certainly Upstash's per-value size cap on a single
# STRING. A HASH has no such ceiling since each company is its own field,
# written independently, and reading the whole cache back is one HGETALL.
_REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
_REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
_REDIS_KEY = 'cache:company_domain:hash'
_REDIS_PIPELINE_BATCH = 500  # companies per HTTP round-trip when writing


def _redis_configured():
    return bool(_REDIS_URL and _REDIS_TOKEN)


def _redis_hgetall(key):
    r = requests.get(f'{_REDIS_URL}/hgetall/{key}', headers={'Authorization': f'Bearer {_REDIS_TOKEN}'}, timeout=30)
    r.raise_for_status()
    flat = r.json().get('result') or []
    return {flat[i]: json.loads(flat[i + 1]) for i in range(0, len(flat), 2)}


def _redis_hset_batch(key, items):
    """items: list of (field, value_dict) pairs. Batches many HSET commands
    per HTTP call via Upstash's /pipeline endpoint - one round-trip per 500
    companies instead of one call per company (290k calls) or one oversized
    blob (the failure mode this replaced). Each batch is an idempotent HSET,
    never a delete, so retrying (or re-running the whole push from scratch
    after a partial failure) is always safe - confirmed needed live: a
    transient SSL error killed a real push after only 1 of ~577 batches."""
    for i in range(0, len(items), _REDIS_PIPELINE_BATCH):
        batch = items[i:i + _REDIS_PIPELINE_BATCH]
        commands = [['HSET', key, field, json.dumps(value)] for field, value in batch]
        last_exc = None
        for attempt in range(1, 6):
            try:
                r = requests.post(f'{_REDIS_URL}/pipeline',
                                   headers={'Authorization': f'Bearer {_REDIS_TOKEN}', 'Content-Type': 'application/json'},
                                   data=json.dumps(commands).encode('utf-8'), timeout=30)
                r.raise_for_status()
                last_exc = None
                break
            except requests.exceptions.RequestException as e:
                last_exc = e
                time.sleep(3 * attempt)
        if last_exc:
            raise last_exc


_LEGAL_SUFFIX_RE = re.compile(
    r'[,]?\s*\(?\b(incorporated|corporation|company|limited|pte\.?\s*ltd\.?|pty\.?\s*ltd\.?|'
    r'p\.?\s*ltd\.?|inc\.?|llc\.?|ltd\.?|corp\.?|plc\.?|gmbh\.?|co\.?|'
    r's\.?a\.?r\.?l\.?|s\.?p\.?a\.?|s\.?r\.?o\.?|a/s|aps|kft)\)?\.?\s*$',
    re.IGNORECASE,
)
# AB/AG/SA/BV/NV/AS/KG are legal-entity suffixes in Sweden/Germany/France/
# Netherlands/Norway respectively, but also plain English words or initials
# ("AG Barr", "Landmark AG") - re.IGNORECASE here would risk stripping a real
# word and searching for the wrong company. These are conventionally written
# all-caps as a suffix, so match only the exact uppercase trailing token
# instead of folding case like the suffixes above.
_SHORT_INTL_SUFFIX_RE = re.compile(r'[,]?\s*\b(AB|AG|SA|BV|NV|AS|KG)\s*$')
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
        s = _SHORT_INTL_SUFFIX_RE.sub('', s).strip().rstrip(',.').strip()
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
        return _redis_hgetall(_REDIS_KEY)
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, newline='', encoding='utf-8') as f:
        return {row['company_key']: row for row in csv.DictReader(f)}


def save_cache(cache):
    """Called everywhere with the full, already-merged cache dict (never a
    dict with entries removed - nothing in this codebase ever deletes a
    company), so writing every field via HSET is safe: it only adds/updates,
    it can never orphan an existing company that HSET wasn't told about."""
    if _redis_configured():
        _redis_hset_batch(_REDIS_KEY, list(cache.items()))
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


def hubspot_search(session, query_name):
    if not HUBSPOT_TOKEN:
        return []
    try:
        r = session.post(
            'https://api.hubapi.com/crm/v3/objects/companies/search',
            headers={'Authorization': f'Bearer {HUBSPOT_TOKEN}', 'Content-Type': 'application/json'},
            json={
                'filterGroups': [{'filters': [{'propertyName': 'name', 'operator': 'CONTAINS_TOKEN', 'value': query_name}]}],
                'properties': ['name', 'domain'],
                'limit': 10,
            },
            timeout=(5, 10),
        )
        return r.json().get('results', []) if r.ok else []
    except Exception:
        return []


def hubspot_resolve(session, query_candidates):
    """Your own HubSpot Company records - read-only (never writes/updates,
    per this kit's HubSpot rule), free, and the most trustworthy source
    since it's data your own team already verified. Same exact-name-match
    philosophy as Clearbit: CONTAINS_TOKEN search casts wide, only a single
    normalized-exact-name result with a domain is trusted."""
    if not HUBSPOT_TOKEN:
        return None, None
    for q in query_candidates:
        results = hubspot_search(session, q)
        qn = norm(q)
        exact = [c for c in results
                 if norm(c.get('properties', {}).get('name', '')) == qn and c.get('properties', {}).get('domain')]
        if len(exact) == 1:
            return {'domain': exact[0]['properties']['domain'], 'country': '', 'city': ''}, 'HubSpot-exact'
    return None, None


BRANDFETCH_SEARCH_URL = 'https://api.brandfetch.io/v2/search/{}'


def brandfetch_search(session, query_name):
    if not BRANDFETCH_API_KEY:
        return []
    try:
        r = session.get(
            BRANDFETCH_SEARCH_URL.format(requests.utils.quote(query_name, safe='')),
            headers={'Authorization': f'Bearer {BRANDFETCH_API_KEY}'},
            timeout=(5, 10),
        )
        return r.json() if r.ok else []
    except Exception:
        return []


def brandfetch_resolve(session, query_candidates):
    """Free tier (requires a free Brandfetch API key - set BRANDFETCH_API_KEY
    to enable; silently skipped otherwise). Multiple real
    companies/sub-brands/CDN domains commonly share the same display name -
    confirmed live: 'Stripe' alone returns 5 exact-name matches (stripe.com,
    stripecdn.com, stripeassets.com, stripe-atlas.com, getstripe.com), all
    ending in .com, so a Clearbit-style "lone .com" tiebreak wouldn't
    disambiguate this at all. Brandfetch exposes a real relevance score
    (_score) per result, unlike Clearbit's unscored list order - ranking by
    it and trusting the top exact-name match outright is a materially
    stronger signal than Clearbit's blind top-ranked guess, so (unlike
    Clearbit's equivalent tier) this is treated as confident, not deferred."""
    if not BRANDFETCH_API_KEY:
        return None, None
    for q in query_candidates:
        suggestions = brandfetch_search(session, q)
        qn = norm(q)
        exact = [s for s in suggestions if norm(s.get('name', '')) == qn and s.get('domain')]
        if not exact:
            continue
        if len(exact) == 1:
            return {'domain': exact[0]['domain'], 'country': '', 'city': ''}, 'Brandfetch-exact'
        best = max(exact, key=lambda s: s.get('_score', 0))
        return {'domain': best['domain'], 'country': '', 'city': ''}, 'Brandfetch-exact-top-scored'
    return None, None



# Wikimedia rejects requests with the default python-requests User-Agent
# (their UA policy blocks generic/unidentified clients, confirmed: got a
# bare 403 without this) - a descriptive UA with contact info is required,
# not optional. See https://meta.wikimedia.org/wiki/User-Agent_policy
WIKIDATA_HEADERS = {'User-Agent': 'XoxodayOutboundKit-DomainResolver/1.0 (internal tool; no public contact)'}


def wikidata_search(session, query_name):
    try:
        r = session.get(
            'https://www.wikidata.org/w/api.php',
            params={'action': 'wbsearchentities', 'search': query_name, 'language': 'en',
                    'type': 'item', 'format': 'json', 'limit': 5},
            headers=WIKIDATA_HEADERS,
            timeout=(5, 10),
        )
        return r.json().get('search', []) if r.ok else []
    except Exception:
        return []


def wikidata_official_website(session, qid):
    try:
        r = session.get(
            'https://www.wikidata.org/w/api.php',
            params={'action': 'wbgetclaims', 'entity': qid, 'property': 'P856', 'format': 'json'},
            headers=WIKIDATA_HEADERS,
            timeout=(5, 10),
        )
        claims = r.json().get('claims', {}).get('P856', [])
        if claims:
            return claims[0]['mainsnak']['datavalue']['value']
    except Exception:
        pass
    return None


def wikidata_resolve(session, query_candidates):
    """Free, keyless, no signup. Only covers companies notable enough to
    have a Wikidata item with an 'official website' (P856) claim - strong
    for large/public companies, essentially blank for small/private ones.
    Treat as a supplemental long-tail-of-fame tier, not a general fallback."""
    for q in query_candidates:
        qn = norm(q)
        exact = [c for c in wikidata_search(session, q) if norm(c.get('label', '')) == qn]
        if len(exact) == 1:
            url = wikidata_official_website(session, exact[0]['id'])
            if url:
                domain = re.sub(r'^https?://(www\.)?', '', str(url)).split('/')[0].strip()
                if domain:
                    return {'domain': domain, 'country': '', 'city': ''}, 'Wikidata-exact'
    return None, None


def try_free_tiers(session, query_candidates):
    """Ordered cheapest/most-trustworthy first: HubSpot (your own verified
    data) -> Clearbit (confident branch only) -> Brandfetch -> Wikidata.
    Returns (result_dict_or_None, source_or_None, cb_best, cb_source) - the
    last two are Clearbit's raw weak-guess result (if any), always computed
    since resolve() needs it later as a last-resort fallback after Apollo
    itself finds nothing, even when it wasn't confident enough to win here.

    Kept as a single function (not inlined into resolve()) so
    estimate_needs_apollo() calls the exact same chain instead of a second,
    possibly-drifting copy of it - that drift is exactly what caused the old
    Clearbit-only estimate to overstate cost before this file's own
    docstring/comments flagged it."""
    hubspot_result, hubspot_source = hubspot_resolve(session, query_candidates)
    if hubspot_result:
        return hubspot_result, hubspot_source, None, None

    cb_best, cb_source, _ = clearbit_resolve(session, query_candidates, norm(query_candidates[-1]))
    if cb_best and cb_source != 'Clearbit-exact-top-ranked':
        return {'domain': cb_best.get('domain', ''), 'country': '', 'city': ''}, cb_source, cb_best, cb_source

    brandfetch_result, brandfetch_source = brandfetch_resolve(session, query_candidates)
    if brandfetch_result:
        return brandfetch_result, brandfetch_source, cb_best, cb_source

    wikidata_result, wikidata_source = wikidata_resolve(session, query_candidates)
    if wikidata_result:
        return wikidata_result, wikidata_source, cb_best, cb_source

    return None, None, cb_best, cb_source


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
    """Free pre-check (no Apollo call) for whether this company would
    actually cost an Apollo credit in resolve() below - i.e. it's not
    already cached AND none of the free tiers (HubSpot, Clearbit, Brandfetch,
    Wikidata) can confidently resolve it either. Exists so the pre-run cost
    estimate shown to the user reflects what will really get charged, instead
    of assuming every uncached company needs Apollo. Calls try_free_tiers -
    the same chain resolve() uses - rather than duplicating it, to avoid a
    second, possibly-stale copy of the chain drifting out of sync."""
    key = norm(str(company_name).strip())
    if key in cache:
        return False
    query_candidates = build_query_candidates(company_name)
    best, source, _cb_best, _cb_source = try_free_tiers(session, query_candidates)
    return best is None


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

    # Free tiers first, cheapest/most-trustworthy order - HubSpot (your own
    # verified data) -> Clearbit (confident branch only) -> Brandfetch ->
    # Wikidata - all before spending an Apollo credit. Clearbit's weaker
    # "top-ranked guess" tier isn't trusted here; it's only used later as a
    # last-resort fallback if Apollo itself comes back with nothing.
    free_result, free_source, cb_best, cb_source = try_free_tiers(session, query_candidates)
    if free_result:
        return {
            'domain': free_result.get('domain', ''), 'linkedin': '',
            'country': free_result.get('country', ''), 'city': free_result.get('city', ''),
            'source': free_source, 'candidates': [],
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
    from_hubspot = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('HubSpot'))
    from_clearbit = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Clearbit'))
    from_brandfetch = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Brandfetch'))
    from_wikidata = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Wikidata'))
    from_apollo = sum(1 for r in results.values() if r['domain'] and r['source'].startswith('Apollo'))
    resolved = sum(1 for r in results.values() if r['domain'])
    print(f"\n{len(results)} companies: {from_cache} from cache, {from_hubspot} via HubSpot, "
          f"{from_clearbit} via Clearbit, {from_brandfetch} via Brandfetch, {from_wikidata} via Wikidata, "
          f"{from_apollo} via Apollo, {resolved} total resolved, "
          f"{len(results) - resolved} unresolved/ambiguous. {new_cache_entries} new cache entries saved.")


if __name__ == '__main__':
    main()
