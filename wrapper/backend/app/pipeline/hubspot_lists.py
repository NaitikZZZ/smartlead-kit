"""Creates a static HubSpot contact list for the "no association" path -
upload the contacts, put them in a plain list, hand back the list URL
directly rather than requiring a Partner/Project/Event association."""
from __future__ import annotations
import requests

from .. import config


def _headers():
    token = config.require("HUBSPOT_WRITE_TOKEN", config.HUBSPOT_WRITE_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_list_with_contacts(list_name: str, contact_ids: list[str]) -> dict:
    create_resp = requests.post(
        "https://api.hubapi.com/crm/v3/lists",
        headers=_headers(),
        json={"name": list_name, "objectTypeId": "0-1", "processingType": "MANUAL"},
        timeout=20,
    )
    create_resp.raise_for_status()
    list_id = create_resp.json()["list"]["listId"]

    if contact_ids:
        add_resp = requests.put(
            f"https://api.hubapi.com/crm/v3/lists/{list_id}/memberships/add",
            headers=_headers(),
            json=contact_ids,
            timeout=30,
        )
        add_resp.raise_for_status()

    list_url = f"https://{config.HUBSPOT_APP_SUBDOMAIN}/contacts/{config.HUBSPOT_PORTAL_ID}/objectLists/{list_id}"
    return {"list_id": list_id, "list_url": list_url, "members_added": len(contact_ids)}
