"""Resolves a Partner/Project/Event association from whatever the user typed
(a raw record ID, a pasted HubSpot record URL, or a name to search for), and
provides the cached full record lists that power the association dropdowns."""
from __future__ import annotations
import json
import re

try:
    from datetime import datetime, UTC
except ImportError:  # Python <3.11
    from datetime import datetime, timezone
    UTC = timezone.utc

import requests

from .. import config, redis_cache

OBJECT_TYPE = {
    "partner": config.HUBSPOT_PARTNER_OBJECT,
    "project": config.HUBSPOT_PROJECT_OBJECT,
    "event": config.HUBSPOT_EVENT_OBJECT,
}
NAME_PROPERTY = {"partner": "partner_name", "project": "hs_name", "event": "event_name"}

_ASSOC_TYPE_CACHE: dict[str, dict] = {
    config.HUBSPOT_PARTNER_OBJECT: config.ASSOC_CONTACT_TO_PARTNER,
    config.HUBSPOT_PROJECT_OBJECT: config.ASSOC_CONTACT_TO_PROJECT,
}


def _read_headers():
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_association_type(object_type_id: str) -> dict:
    """Looks up (and caches) the association type between contacts and the
    given object type, rather than hardcoding a guess for objects we haven't
    confirmed live (e.g. Events)."""
    if object_type_id in _ASSOC_TYPE_CACHE:
        return _ASSOC_TYPE_CACHE[object_type_id]
    r = requests.get(
        f"https://api.hubapi.com/crm/v4/associations/contacts/{object_type_id}/labels",
        headers=_read_headers(), timeout=15,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise ValueError(f"No association type found between contacts and object type {object_type_id}")
    spec = {"associationCategory": results[0]["category"], "associationTypeId": results[0]["typeId"]}
    _ASSOC_TYPE_CACHE[object_type_id] = spec
    return spec


def _assoc_cache_path(kind: str):
    return config.CACHE_DIR / f"assoc_{kind}.json"


def _assoc_redis_key(kind: str) -> str:
    return f"cache:assoc:{kind}"


def _assoc_cache_read(kind: str) -> dict | None:
    if redis_cache.is_configured():
        return redis_cache.get_json(_assoc_redis_key(kind))
    p = _assoc_cache_path(kind)
    return json.loads(p.read_text()) if p.exists() else None


def _assoc_cache_write(kind: str, data: dict) -> None:
    if redis_cache.is_configured():
        redis_cache.set_json(_assoc_redis_key(kind), data)
        return
    _assoc_cache_path(kind).write_text(json.dumps(data))


def fetch_all_records(kind: str) -> list[dict]:
    """Read-only: fetch EVERY record for the dropdown - [{id, name}], fully
    paginated (no limit). Projects are filtered to the ABM Campaigns pipeline;
    partners/events are listed as-is. Sorted by name where possible."""
    object_type_id = OBJECT_TYPE[kind]
    name_property = NAME_PROPERTY[kind]

    base_body: dict = {"properties": [name_property]}
    if kind == "project":
        base_body["filterGroups"] = [
            {"filters": [{"propertyName": "hs_pipeline", "operator": "EQ", "value": config.HUBSPOT_ABM_PIPELINE_ID}]}
        ]

    def _fetch(with_sort: bool):
        out, after = [], None
        while True:
            body = dict(base_body)
            body["limit"] = 100
            if with_sort:
                body["sorts"] = [{"propertyName": name_property, "direction": "ASCENDING"}]
            if after:
                body["after"] = after
            r = requests.post(
                f"https://api.hubapi.com/crm/v3/objects/{object_type_id}/search",
                headers=_read_headers(), json=body, timeout=30,
            )
            r.raise_for_status()
            j = r.json()
            for res in j.get("results", []):
                out.append({"id": res["id"], "name": res["properties"].get(name_property) or res["id"]})
            after = j.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
        return out

    try:
        return _fetch(with_sort=True)
    except requests.HTTPError:
        return _fetch(with_sort=False)


def refresh_cache(kinds: list[str] | None = None) -> dict:
    """Fetch all records for each kind and cache them. Run on a cron."""
    kinds = kinds or ["project", "partner", "event"]
    result = {}
    for kind in kinds:
        recs = fetch_all_records(kind)
        _assoc_cache_write(kind, {"built_at": datetime.now(UTC).isoformat(), "records": recs})
        result[kind] = len(recs)
    return result


def list_records(kind: str) -> list[dict]:
    """Serve the full record list from cache - a Vercel Cron Job (see
    app/routes/cron.py) is the only thing that rebuilds this now; a real
    request never fetches inline (removed - an unbounded-duration HubSpot
    pagination call has no business running inside a request a human is
    waiting on, or inside a Vercel function's duration limit). A stale cache
    (past TTL) is still served - the caller (runner.py's associations step)
    already treats a missing/failed cache as "fall back to manual entry"."""
    data = _assoc_cache_read(kind)
    if data is None:
        raise RuntimeError(
            f"{kind} dropdown cache has never been built - the cron (app/routes/cron.py) "
            "populates it; wait for the next run or trigger it manually."
        )
    return data["records"]


def _extract_id_from_url(value: str) -> str | None:
    m = re.search(r"/record/[^/]+/(\d+)", value)
    return m.group(1) if m else None


def resolve(kind: str, value: str) -> dict:
    """Returns {"status": "resolved", "record_id": ...} or
    {"status": "ambiguous", "candidates": [{"id":..., "name":...}, ...]} or
    {"status": "not_found"}."""
    value = value.strip()
    object_type_id = OBJECT_TYPE[kind]

    if value.isdigit():
        return {"status": "resolved", "record_id": value}

    url_id = _extract_id_from_url(value)
    if url_id:
        return {"status": "resolved", "record_id": url_id}

    # Treat as a name search
    name_property = NAME_PROPERTY[kind]
    r = requests.post(
        f"https://api.hubapi.com/crm/v3/objects/{object_type_id}/search",
        headers=_read_headers(),
        json={"filterGroups": [{"filters": [{"propertyName": name_property, "operator": "CONTAINS_TOKEN", "value": value}]}],
              "properties": [name_property]},
        timeout=15,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return {"status": "not_found"}
    if len(results) == 1:
        return {"status": "resolved", "record_id": results[0]["id"]}
    return {
        "status": "ambiguous",
        "candidates": [{"id": res["id"], "name": res["properties"].get(name_property, "")} for res in results],
    }


if __name__ == "__main__":  # cron entrypoint: refresh association dropdown caches
    import sys
    kinds = [a for a in sys.argv[1:] if a in ("project", "partner", "event")] or None
    print(f"Refreshing association caches: {kinds or ['project', 'partner', 'event']} ...")
    counts = refresh_cache(kinds)
    for k, n in counts.items():
        print(f"  {k}: {n} records cached")
