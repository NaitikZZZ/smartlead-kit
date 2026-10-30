"""Creates a static HubSpot contact list for the "no association" path -
upload the contacts, put them in a plain list, hand back the list URL
directly rather than requiring a Partner/Project/Event association."""
from __future__ import annotations
import requests

from .. import config
from .hubspot_retry import request_with_retry


def _headers():
    token = config.require("HUBSPOT_WRITE_TOKEN", config.HUBSPOT_WRITE_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _raise_with_body(r: requests.Response):
    """requests' default HTTPError swallows the response body, which is
    exactly where HubSpot puts the actual validation message - surface it so
    failures are diagnosable instead of a bare '400 Client Error: Bad Request
    for url: ...'."""
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason} for {r.url}: {r.text[:500]}", response=r)


def _find_list_id_by_exact_name(list_name: str) -> str | None:
    r = request_with_retry(
        "POST", "https://api.hubapi.com/crm/v3/lists/search",
        headers=_headers(),
        json={"query": list_name, "processingTypes": ["MANUAL"], "objectTypeId": "0-1"},
        timeout=20,
    )
    _raise_with_body(r)
    for lst in r.json().get("lists", []):
        if lst.get("name") == list_name:
            return lst.get("listId")
    return None


def create_list(list_name: str) -> str:
    """Creates the static list (or reuses the one already holding this exact
    name) and returns its id."""
    create_resp = request_with_retry(
        "POST", "https://api.hubapi.com/crm/v3/lists",
        headers=_headers(),
        json={"name": list_name, "objectTypeId": "0-1", "processingType": "MANUAL"},
        timeout=20,
    )
    if create_resp.status_code == 400 and "DUPLICATE_LIST_NAMES" in create_resp.text:
        # Re-running the same campaign title (a retried/failed prior run, or a
        # second batch of contacts for the same campaign) hits this - reuse
        # the existing list instead of failing the whole import.
        list_id = _find_list_id_by_exact_name(list_name)
        if not list_id:
            _raise_with_body(create_resp)  # name collision but couldn't resolve which list - surface the original error
    else:
        _raise_with_body(create_resp)
        list_id = create_resp.json()["list"]["listId"]
    return list_id


def add_members(list_id: str, contact_ids: list[str]) -> None:
    """Idempotent: adding an id already in the list is a no-op."""
    add_resp = request_with_retry(
        "PUT", f"https://api.hubapi.com/crm/v3/lists/{list_id}/memberships/add",
        headers=_headers(),
        json=contact_ids,
        timeout=30,
    )
    _raise_with_body(add_resp)


def list_url(list_id: str) -> str:
    return f"https://{config.HUBSPOT_APP_SUBDOMAIN}/contacts/{config.HUBSPOT_PORTAL_ID}/objectLists/{list_id}"


def create_list_with_contacts(list_name: str, contact_ids: list[str]) -> dict:
    list_id = create_list(list_name)
    if contact_ids:
        add_members(list_id, contact_ids)
    return {"list_id": list_id, "list_url": list_url(list_id), "members_added": len(contact_ids)}
