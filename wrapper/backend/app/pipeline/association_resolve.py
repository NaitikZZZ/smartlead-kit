"""Resolves a Partner/Project/Event association from whatever the user typed
(a raw record ID, a pasted HubSpot record URL, or a name to search for)."""
from __future__ import annotations
import re

import requests

from .. import config

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
