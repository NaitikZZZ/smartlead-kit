"""
Search Apollo for people at each company matching a list of target personas,
select up to N per company (seniority-ranked), without spending any reveal
credits yet - this is the "search" stage, not the "enrich" stage.

Apollo's people search returns OBFUSCATED previews (e.g. "Laura Bu***r") -
real name/email/phone require a separate per-person enrichment call
(enrich_contacts_apollo.py / enrich_phone_apollo.py) using the Apollo id
this script outputs. That's intentional: search is free, enrichment costs
credits, so we only pay for the candidates we actually selected.

Selection logic: rank returned candidates by how early their title matches
in PERSONAS (the sheet's own priority order = seniority proxy), preferring
one distinct persona covered before doubling up on any single persona.
Then prefer candidates with has_email=true (more likely a real enrichment
hit) as a tiebreaker. Take up to MAX_PER_COMPANY, no minimum forced - if a
company only has 3 real matches, we return 3, not padded fakes.

Usage:
    python3 search_company_contacts_apollo.py <input_csv> <company_col> <domain_col> <output_csv>
"""
import os
import re
import sys
import time
import requests
from _lazy import pd
from dotenv import load_dotenv

load_dotenv()
APOLLO_KEY = os.environ.get('APOLLO_API_KEY')
MAX_PER_COMPANY = 10
# Optional override for one-off runs targeting a persona set other than the
# built-in HR-function list (e.g. a product/partnerships persona list for a
# non-HR segment). Titles outside PERSONA_TIERS's keywords just fall back to
# tier 99 (unranked, has_email tiebreak only) - no separate tier map needed
# for a run that doesn't reuse this persona set again.
_personas_file = os.environ.get('PERSONAS_FILE')
MIN_AIM = 7  # informational only - we report the shortfall, never fabricate

PERSONAS = [
    'Chief Human Resources Officer',
    'Chief People Officer',
    'VP of HR', 'Director of HR',
    'Head of Employee Experience',
    'Head of Employee Engagement',
    'Head of Rewards', 'Head of Recognition',
    'Head of Total Rewards',
    'Head of Compensation', 'Head of Benefits',
    'Director People Operations', 'Manager People Operations',
    'HR Business Partner',
    'Head of Culture', 'Head of Engagement',
    'Head of Talent Management',
]
# Rough persona "tier" - index into this maps a candidate's title to a
# priority bucket for ranking. Order matches the source sheet's own listed
# priority (CHRO/CPO first, down to HRBP last).
PERSONA_TIERS = [
    ('chief human resources officer', 0), ('chro', 0),
    ('chief people officer', 0), ('cpo', 0),
    ('vp', 1), ('vice president', 1), ('director of hr', 1), ('director, hr', 1),
    ('head of employee experience', 2),
    ('head of employee engagement', 2),
    ('head of rewards', 3), ('head of recognition', 3), ('head of total rewards', 3),
    ('head of compensation', 3), ('head of benefits', 3),
    ('director', 4), ('manager', 4),  # people operations director/manager
    ('hr business partner', 5), ('hrbp', 5),
    ('head of culture', 6), ('head of engagement', 6),
    ('head of talent', 6),
]

if _personas_file:
    with open(_personas_file) as _f:
        PERSONAS = [line.strip() for line in _f if line.strip()]


def persona_tier(title):
    t = (title or '').lower()
    for keyword, tier in PERSONA_TIERS:
        if keyword in t:
            return tier
    return 99  # unmatched title - lowest priority, still eligible


# person_seniorities ("Management Level" in Apollo's own UI) - documented,
# confirmed enum (docs.apollo.io/reference/people-api-search).
DEFAULT_SENIORITIES = ['c_suite', 'vp', 'head', 'director', 'manager']
ALL_SENIORITIES = ['owner', 'founder', 'c_suite', 'partner', 'vp', 'head',
                    'director', 'manager', 'senior', 'entry', 'intern']

# person_functions ("Departments & Job Function" in Apollo's own UI) - NOT in
# Apollo's public API docs, but confirmed real and working by live testing
# against mixed_people/api_search: a garbage value returns 0 results while
# each of these returns distinctly relevant titles (e.g. "human_resources"
# surfaces recruiters/talent partners, "legal" surfaces a Chief Legal
# Officer). Other plausible-looking slugs tried and confirmed NOT valid
# (silently return 0, same as a nonsense string): design, media,
# communications, customer_service, recruiting, real_estate, trades.
ALL_FUNCTIONS = ['sales', 'marketing', 'engineering', 'product_management',
                  'finance', 'accounting', 'operations', 'human_resources',
                  'information_technology', 'legal', 'consulting',
                  'administrative', 'education', 'entrepreneurship',
                  'support', 'data_science']


def search_people(session, domain, person_locations=None, employee_ranges=None, organization_locations=None,
                   person_seniorities=None, person_functions=None):
    # person_seniorities matters a lot for large companies: without it, a
    # single page of title-matched results can be dominated by hundreds of
    # "HR Business Partner" hits and never surface the actual CHRO/CPO at
    # all (confirmed on Cognizant - adding this filter surfaced their real
    # Chief People Officer immediately, where the unfiltered search buried
    # her under lower-level titles). Defaults to DEFAULT_SENIORITIES
    # (unchanged prior behavior) when the caller doesn't specify one.
    #
    # person_locations filters by where the PERSON is based, not the
    # company's HQ - confirmed via testing. Useful when a target company is
    # multinational but you only want contacts physically in a given region.
    #
    # organization_locations is the separate, company-HQ-based filter (city,
    # state, or country of the employer's headquarters) - for "HQ based use
    # cases" where you want everyone at a company HQ'd in a given place,
    # regardless of where the individual contact personally sits.
    #
    # person_functions is the "Departments & Job Function" filter - see
    # ALL_FUNCTIONS above for how its value list was verified.
    payload = {
        'q_organization_domains_list': [domain], 'person_titles': PERSONAS,
        'person_seniorities': person_seniorities or DEFAULT_SENIORITIES,
        'page': 1, 'per_page': 50,
    }
    if person_locations:
        payload['person_locations'] = person_locations
    if employee_ranges:
        payload['organization_num_employees_ranges'] = employee_ranges
    if organization_locations:
        payload['organization_locations'] = organization_locations
    if person_functions:
        payload['person_functions'] = person_functions
    try:
        r = session.post(
            'https://api.apollo.io/api/v1/mixed_people/api_search',
            headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'x-api-key': APOLLO_KEY},
            json=payload,
            timeout=(5, 15),
        )
        return r.json().get('people', [])
    except Exception:
        return []


def select_candidates(people):
    for p in people:
        p['_tier'] = persona_tier(p.get('title'))
    people.sort(key=lambda p: (p['_tier'], p.get('has_email') is not True))

    selected, seen_tiers = [], set()
    # Pass 1: one candidate per distinct persona tier first
    for p in people:
        if len(selected) >= MAX_PER_COMPANY:
            break
        if p['_tier'] not in seen_tiers:
            selected.append(p)
            seen_tiers.add(p['_tier'])
    # Pass 2: fill remaining slots with the next-best candidates regardless of tier reuse
    for p in people:
        if len(selected) >= MAX_PER_COMPANY:
            break
        if p not in selected:
            selected.append(p)
    return selected


_TITLE_STOPWORDS = {"of", "the", "and", "&", "for", "a", "an", "in"}


def _title_word_set(title):
    """Normalizes a title into its significant words (lowercased, punctuation
    stripped, connector words dropped), so word-order variants of the same
    title compare equal - 'Total Rewards Head' and 'Head of Total Rewards'
    both reduce to {total, rewards, head} - while a genuinely different title
    that merely shares words ('Total Rewards Manager', 'VP Total Rewards')
    does not, since 'manager'/'vp' change the set."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return frozenset(w for w in words if w not in _TITLE_STOPWORDS)


def select_candidates_per_persona(people, personas, per_persona_cap, exact=False):
    """Guarantee up to `per_persona_cap` candidates for EACH persona/title in
    `personas`, instead of ranking everyone against the hardcoded PERSONA_TIERS
    keyword list (which only recognizes the built-in HR titles). Within a
    persona, has_email=true candidates are preferred. A candidate matching
    more than one requested persona is only counted once, under whichever
    persona it matches first in list order. Candidates matching none of the
    listed personas are dropped - the point is guaranteed per-title coverage,
    not a general top-N fill.

    exact=True restricts matches to the same title (allowing word-order
    variants, via _title_word_set) rather than any title that merely contains
    the requested phrase as a substring - e.g. a search for "Total Rewards
    Head" no longer also pulls in "Total Rewards Manager" or "VP Total
    Rewards". exact=False (the substring behavior) is the "include similar/
    lookalike titles" option."""
    selected, seen_ids = [], set()
    for tier, persona in enumerate(personas):
        needle = (persona or '').strip().lower()
        if not needle:
            continue
        if exact:
            needle_words = _title_word_set(persona)
            matches = [
                p for p in people
                if _title_word_set(p.get('title')) == needle_words and p.get('id') not in seen_ids
            ]
        else:
            matches = [
                p for p in people
                if needle in (p.get('title') or '').lower() and p.get('id') not in seen_ids
            ]
        matches.sort(key=lambda p: p.get('has_email') is not True)
        for p in matches[:per_persona_cap]:
            p['_tier'] = tier  # index of the persona it matched, for the output's persona_tier column
            selected.append(p)
            seen_ids.add(p.get('id'))
    return selected


def main():
    args = sys.argv[1:]
    input_csv, company_col, domain_col, output_csv = args[:4]
    person_locations = args[4].split(',') if len(args) > 4 else None
    df = pd.read_csv(input_csv)

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    rows = []
    for i, row in df.iterrows():
        company, domain = row[company_col], row.get(domain_col)
        if pd.isna(domain) or not str(domain).strip():
            print(f"{i+1}/{len(df)} SKIP {company} (no domain)", flush=True)
            continue
        people = search_people(session, domain, person_locations)
        selected = select_candidates(people)
        for p in selected:
            rows.append({
                'Company': company, 'Domain': domain, 'apollo_id': p.get('id'),
                'obfuscated_name': f"{p.get('first_name','')} {p.get('last_name_obfuscated','')}",
                'title': p.get('title'), 'persona_tier': p['_tier'],
                'has_email': p.get('has_email'), 'has_direct_phone': p.get('has_direct_phone'),
            })
        shortfall = f" (below {MIN_AIM} target)" if len(selected) < MIN_AIM else ""
        print(f"{i+1}/{len(df)} {company} -> {len(people)} found, {len(selected)} selected{shortfall}", flush=True)
        time.sleep(0.3)

    out = pd.DataFrame(rows)
    out.to_csv(output_csv, index=False)
    print(f"\n{len(rows)} candidates selected across {df[domain_col].notna().sum()} companies with a domain.")


if __name__ == '__main__':
    main()
