"""HubSpot contact batch-upsert + Partner/Project/Event associations,
mirroring the flow validated against the live Xoxoday portal this session.
Only ever called after an explicit confirm from the API caller - never runs
as part of the automatic pipeline stages."""
from __future__ import annotations
import requests

from .. import config
from . import association_resolve, hubspot_lists


def _headers():
    token = config.require("HUBSPOT_WRITE_TOKEN", config.HUBSPOT_WRITE_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _valid_email(v) -> bool:
    """A row is uploadable only if it has a real, non-blank email. This is the
    single hard guard - HARDCODED: no blank-email contact is ever sent to
    HubSpot, no matter which path calls the upsert."""
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and s.lower() != "nan" and "@" in s


def batch_upsert_contacts(rows: list[dict]) -> list[dict]:
    # Drop any blank/invalid-email row at the API-write chokepoint, and use the
    # stripped email as the idempotency key + property value.
    inputs = []
    for r in rows:
        if not _valid_email(r.get("email")):
            continue
        email = str(r["email"]).strip()
        inputs.append({"idProperty": "email", "id": email, "properties": {**r, "email": email}})
    results = []
    for i in range(0, len(inputs), 100):  # HubSpot batch limit
        chunk = inputs[i:i + 100]
        r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert",
            headers=_headers(), json={"inputs": chunk}, timeout=60,
        )
        r.raise_for_status()
        results.extend(r.json().get("results", []))
    return results


def associate_contacts(contact_ids: list[str], object_type_id: str, to_object_id: str):
    assoc_spec = association_resolve.get_association_type(object_type_id)
    inputs = [{"from": {"id": cid}, "to": {"id": to_object_id}, "types": [assoc_spec]} for cid in contact_ids]
    r = requests.post(
        f"https://api.hubapi.com/crm/v4/associations/contacts/{object_type_id}/batch/create",
        headers=_headers(), json={"inputs": inputs}, timeout=60,
    )
    r.raise_for_status()
    return len(r.json().get("results", []))


def import_contacts_with_list(rows: list[dict], campaign_title: str, associations: list[dict] | None = None):
    """The single, canonical HubSpot import path. Two HARDCODED invariants,
    enforced here so no caller can bypass them:
      1. No blank-email contact is ever uploaded (filtered here AND in batch_upsert).
      2. A static HubSpot list is ALWAYS created for the imported contacts.
    associations: list of {"kind": "partner"|"project"|"event", "record_id": str}.
    """
    associations = associations or []
    valid_rows = [r for r in rows if _valid_email(r.get("email"))]
    dropped = len(rows) - len(valid_rows)

    upsert_results = batch_upsert_contacts(valid_rows)
    contact_ids = [r["id"] for r in upsert_results]
    new_count = sum(1 for r in upsert_results if r.get("new"))
    updated_count = len(upsert_results) - new_count

    # Invariant #2: always create a static list on import.
    list_result = hubspot_lists.create_list_with_contacts(campaign_title, contact_ids)

    assoc_results = {}
    for assoc in associations:
        object_type_id = association_resolve.OBJECT_TYPE[assoc["kind"]]
        count = associate_contacts(contact_ids, object_type_id, assoc["record_id"]) if contact_ids else 0
        assoc_results[assoc["kind"]] = {"record_id": assoc["record_id"], "associated": count}

    return {
        "total": len(upsert_results), "new": new_count, "updated": updated_count,
        "dropped_blank_email": dropped, "contact_ids": contact_ids,
        "list": list_result, "associations": assoc_results,
    }
