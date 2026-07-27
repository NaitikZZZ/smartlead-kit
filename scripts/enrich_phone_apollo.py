"""
Phone enrichment via Apollo's async People Match phone reveal, with a
persistent cache so the same person is never paid for twice.

Apollo will NOT return a phone number synchronously - reveal_phone_number
requires a webhook_url, and the number arrives seconds later as a POST to
that URL. This script uses a fresh webhook.site token per run to receive
those callbacks, polls for the results, and deletes the token when done
(success or failure) so nothing lingers on a third-party service.

Cost note, confirmed via live testing:
- Each successful phone reveal costs ~8 Apollo credits (vs ~1 for an email
  match).
- Apollo does NOT deduplicate this on its own - re-requesting reveal for a
  person already unlocked minutes earlier in the same account charged the
  full 8 credits again. The only way to avoid paying twice is a cache on
  our side, which is what this script does (reference/phone_reveal_cache.csv).
- When Apollo has no phone data for a person, it never calls the webhook at
  all - there's no "empty result" callback. That's cached too (as "no phone
  on file") so we don't repeat the same 30s wait for a contact we already
  know has nothing.

Cache invalidation: if you know someone changed jobs, delete their row from
reference/phone_reveal_cache.csv so the next run re-checks Apollo instead of
trusting stale data. There's no automatic job-change detection here.

Usage:
    python3 enrich_phone_apollo.py <input_csv> <first_name_col> <last_name_col> <domain_col> <output_csv>

If the input CSV has an 'apollo_id' column (e.g. from
search_company_contacts_apollo.py), lookups and the cache key both use that
id directly instead of first/last name - necessary when names are still
Apollo-obfuscated (e.g. "Laura Bu***r") and can't be matched on reliably.
"""
import os
import sys
import csv
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
APOLLO_KEY = os.environ.get('APOLLO_API_KEY')
POLL_INTERVAL = 5
POLL_TIMEOUT = 30
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'reference', 'phone_reveal_cache.csv')
CACHE_FIELDS = ['contact_key', 'first_name', 'last_name', 'domain', 'phone_number', 'phone_type', 'phone_confidence', 'note']

# Redis (Upstash REST) is used when configured - required on Vercel, where the
# local CSV file above isn't writable/persistent across invocations. Falls
# back to the CSV file when Redis isn't configured, so this script still runs
# standalone (e.g. via the manual CLAUDE.md pipeline) without any new setup.
_REDIS_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
_REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')
_REDIS_KEY = 'cache:phone_reveal'


def _redis_configured():
    return bool(_REDIS_URL and _REDIS_TOKEN)


def _redis_get_json(key):
    import json
    r = requests.get(f'{_REDIS_URL}/get/{key}', headers={'Authorization': f'Bearer {_REDIS_TOKEN}'}, timeout=15)
    r.raise_for_status()
    raw = r.json().get('result')
    return json.loads(raw) if raw is not None else None


def _redis_set_json(key, value):
    import json
    r = requests.post(f'{_REDIS_URL}/set/{key}', headers={'Authorization': f'Bearer {_REDIS_TOKEN}'},
                       data=json.dumps(value).encode('utf-8'), timeout=15)
    r.raise_for_status()


def norm(s):
    return ''.join(ch for ch in str(s).lower() if ch.isalnum())


def cache_key(first, last, domain, apollo_id=None):
    if apollo_id:
        return f"id:{apollo_id}"
    return f"{norm(first)}.{norm(last)}@{norm(domain)}"


def load_cache():
    if _redis_configured():
        return _redis_get_json(_REDIS_KEY) or {}
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, newline='', encoding='utf-8') as f:
        return {row['contact_key']: row for row in csv.DictReader(f)}


def save_cache(cache):
    if _redis_configured():
        _redis_set_json(_REDIS_KEY, cache)
        return
    with open(CACHE_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        w.writeheader()
        for row in cache.values():
            w.writerow({k: row.get(k, '') for k in CACHE_FIELDS})


def create_webhook():
    r = requests.post('https://webhook.site/token', timeout=10)
    r.raise_for_status()
    token = r.json()['uuid']
    return token, f'https://webhook.site/{token}'


def delete_webhook(token):
    try:
        requests.delete(f'https://webhook.site/token/{token}', timeout=10)
    except Exception:
        pass  # best-effort cleanup - don't fail the run over this


def request_phone(session, first, last, domain, webhook_url, apollo_id=None):
    base = {'id': apollo_id} if apollo_id else {'first_name': first, 'last_name': last, 'domain': domain}
    try:
        r = session.post(
            'https://api.apollo.io/api/v1/people/match',
            headers={'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'x-api-key': APOLLO_KEY},
            json={**base, 'reveal_personal_emails': False, 'reveal_phone_number': True, 'webhook_url': webhook_url},
            timeout=(5, 15),
        )
        person = r.json().get('person') or {}
        return person.get('id')
    except Exception:
        return None


def poll_webhook_results(token, expected_ids):
    """Poll webhook.site until every expected person id has a callback, or timeout."""
    results = {}
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline and len(results) < len(expected_ids):
        time.sleep(POLL_INTERVAL)
        try:
            r = requests.get(f'https://webhook.site/token/{token}/requests', timeout=15)
            for req in r.json().get('data', []):
                import json as _json
                try:
                    payload = _json.loads(req['content'])
                except Exception:
                    continue
                for p in payload.get('people', []):
                    if p.get('id') in expected_ids and p['id'] not in results:
                        results[p['id']] = p
        except Exception:
            continue
    return results


def best_phone(person_payload):
    phones = person_payload.get('phone_numbers') or []
    if not phones:
        return '', '', ''
    # Prefer work_direct, then highest confidence
    phones_sorted = sorted(phones, key=lambda p: (p.get('type_cd') != 'work_direct', p.get('confidence_cd') != 'high'))
    best = phones_sorted[0]
    return best.get('sanitized_number', ''), best.get('type_cd', ''), best.get('confidence_cd', '')


def main():
    input_csv, first_col, last_col, domain_col, output_csv = sys.argv[1:6]
    df = pd.read_csv(input_csv)
    cache = load_cache()
    has_id_col = 'apollo_id' in df.columns

    session = requests.Session()
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    def label_for(row, apollo_id):
        first = row.get(first_col)
        return first if isinstance(first, str) and first.strip() else (apollo_id or '?')

    # Split into cache hits (free, instant) and rows that actually need an
    # Apollo call. Only rows in the second bucket ever cost credits.
    out_rows = {}
    need_lookup = []
    for i, row in df.iterrows():
        domain = row.get(domain_col)
        apollo_id = row.get('apollo_id') if has_id_col else None
        apollo_id = None if (apollo_id is None or (isinstance(apollo_id, float) and pd.isna(apollo_id))) else apollo_id
        if pd.isna(domain) or not str(domain).strip():
            out_rows[i] = {'Phone Number': '', 'Phone Type': '', 'Phone Confidence': '', 'Phone Note': 'No domain', 'Phone Source': 'Skipped'}
            continue
        key = cache_key(row.get(first_col), row.get(last_col), domain, apollo_id)
        if key in cache:
            c = cache[key]
            out_rows[i] = {'Phone Number': c['phone_number'], 'Phone Type': c['phone_type'], 'Phone Confidence': c['phone_confidence'], 'Phone Note': c['note'], 'Phone Source': 'Cache'}
            print(f"{i+1}/{len(df)} {label_for(row, apollo_id)} -> Cache: {c['note']}", flush=True)
        else:
            need_lookup.append((i, row, key, apollo_id))

    print(f"\n{len(df) - len(need_lookup)} from cache (free), {len(need_lookup)} need a live Apollo lookup (~8 credits each if found).", flush=True)

    if need_lookup:
        token, webhook_url = create_webhook()
        print(f"Webhook created: {webhook_url}", flush=True)
        row_to_person_id = {}
        try:
            for i, row, key, apollo_id in need_lookup:
                domain = row[domain_col]
                pid = request_phone(session, row.get(first_col), row.get(last_col), domain, webhook_url, apollo_id)
                if pid:
                    row_to_person_id[i] = (pid, key, row)
                    print(f"{i+1}/{len(df)} {label_for(row, apollo_id)} -> requested (person {pid})", flush=True)
                else:
                    out_rows[i] = {'Phone Number': '', 'Phone Type': '', 'Phone Confidence': '', 'Phone Note': 'No person match', 'Phone Source': 'Apollo'}
                    print(f"{i+1}/{len(df)} {label_for(row, apollo_id)} -> no person match, no credit spent", flush=True)
                time.sleep(0.3)

            expected_ids = {pid for pid, _, _ in row_to_person_id.values()}
            print(f"\nWaiting up to {POLL_TIMEOUT}s for {len(expected_ids)} async phone callbacks...", flush=True)
            results = poll_webhook_results(token, expected_ids)
            print(f"Received {len(results)}/{len(expected_ids)} callbacks", flush=True)
        finally:
            delete_webhook(token)
            print("Webhook token deleted.", flush=True)

        for i, (pid, key, row) in row_to_person_id.items():
            payload = results.get(pid)
            if payload is None:
                # No callback = Apollo has no phone data for this person - confirmed via testing, not a timeout.
                number, ptype, conf, note = '', '', '', 'No phone number on file'
            else:
                number, ptype, conf = best_phone(payload)
                note = 'OK' if number else 'No phone number on file'
            out_rows[i] = {'Phone Number': number, 'Phone Type': ptype, 'Phone Confidence': conf, 'Phone Note': note, 'Phone Source': 'Apollo'}
            cache[key] = {
                'contact_key': key, 'first_name': row.get(first_col), 'last_name': row.get(last_col), 'domain': row.get(domain_col),
                'phone_number': number, 'phone_type': ptype, 'phone_confidence': conf, 'note': note,
            }

        save_cache(cache)

    out_df = pd.DataFrame([out_rows[i] for i in df.index])
    out = pd.concat([df.reset_index(drop=True), out_df], axis=1)
    out.to_csv(output_csv, index=False)

    ok = sum(1 for r in out_rows.values() if r['Phone Note'] == 'OK')
    from_cache = sum(1 for r in out_rows.values() if r['Phone Source'] == 'Cache')
    print(f"\n{len(out_rows)} contacts: {ok} phone numbers found, {from_cache} served from cache (0 credits).")


if __name__ == '__main__':
    main()
