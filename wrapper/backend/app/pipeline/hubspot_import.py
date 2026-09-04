"""HubSpot contact batch-upsert + Partner/Project/Event associations,
mirroring the flow validated against the live Xoxoday portal this session.
Only ever called after an explicit confirm from the API caller - never runs
as part of the automatic pipeline stages."""
from __future__ import annotations
import math
import re

import requests

from .. import config
from . import association_resolve, hubspot_lists
from .hubspot_retry import request_with_retry


def _headers():
    token = config.require("HUBSPOT_WRITE_TOKEN", config.HUBSPOT_WRITE_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _json_safe(v):
    """Make a value JSON-safe for the HubSpot payload: NaN/Infinity -> None
    (the JSON encoder rejects them), and numpy scalars -> native Python. This
    is the last line of defense so a stray NaN from a numeric column can never
    fail the upload."""
    if v is None:
        return None
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if hasattr(v, "item"):  # numpy scalar (np.float64/np.int64/...)
        try:
            v = v.item()
        except Exception:
            return v
        if isinstance(v, float) and not math.isfinite(v):
            return None
    return v


def _valid_email(v) -> bool:
    """A row is uploadable only if it has a real, non-blank email. This is the
    single hard guard - HARDCODED: no blank-email contact is ever sent to
    HubSpot, no matter which path calls the upsert."""
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and s.lower() != "nan" and "@" in s


_INVALID_EMAIL_RE = re.compile(r"Email address\s+(.+?)\s+is invalid", re.I)


def _invalid_emails_from_error(body: str) -> set[str]:
    """Pulls the addresses HubSpot named as invalid out of a 400 body.

    HubSpot reports these both in the top-level `message` and in an `errors`
    array, and may name several at once, so parse the raw text rather than
    depending on one shape. Lowercased to match how the inputs are keyed."""
    return {m.group(1).strip().strip('\\"').lower() for m in _INVALID_EMAIL_RE.finditer(body or "")}


def batch_upsert_contacts(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    # Drop any blank/invalid-email row at the API-write chokepoint, and use the
    # stripped email as the idempotency key + property value. Also dedupe by
    # email (keep first) - HubSpot rejects an ENTIRE batch if the same
    # idProperty value (email) appears twice in one call, confirmed live: a
    # 179-row real run had 12 duplicate emails (same person surfaced via
    # multiple Apollo search variants) and 400'd with zero detail (see the
    # response-body capture below - added because this exact failure mode
    # took a manual archaeology pass to diagnose from a bare
    # "400 Client Error: Bad Request" with no HubSpot message).
    inputs = []
    seen_emails = set()
    for r in rows:
        if not _valid_email(r.get("email")):
            continue
        email = str(r["email"]).strip().lower()
        if email in seen_emails:
            continue
        seen_emails.add(email)
        props = {k: _json_safe(v) for k, v in r.items()}
        props["email"] = email
        inputs.append({"idProperty": "email", "id": email, "properties": props})
    results = []
    rejected: list[dict] = []
    for i in range(0, len(inputs), 100):  # HubSpot batch limit
        chunk = inputs[i:i + 100]
        # HubSpot rejects the ENTIRE batch when any single record is invalid, so
        # one typo'd address would otherwise block up to 99 good contacts and
        # fail the whole run (seen live: "harsh.kaushik9@gmail.con is invalid"
        # - note .con - killed an import). We can't pre-empt this locally:
        # gmail.con is a syntactically valid address, and HubSpot's rules
        # (typo/deliverability heuristics) aren't reproducible client-side. So
        # take HubSpot's own verdict - drop exactly what it names, retry the
        # rest, and report the drops rather than silently losing them.
        for _attempt in range(6):
            if not chunk:
                break
            r = request_with_retry(
                "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert",
                headers=_headers(), json={"inputs": chunk}, timeout=60,
            )
            if r.ok:
                results.extend(r.json().get("results", []))
                break
            bad = _invalid_emails_from_error(r.text) if r.status_code == 400 else set()
            # Only retry when we can identify (and therefore actually remove)
            # an offender - otherwise we'd spin on an unrelated 400.
            removable = {e for e in bad if any(inp["id"] == e for inp in chunk)}
            if not removable:
                raise requests.HTTPError(
                    f"{r.status_code} {r.reason} for {r.url}: {r.text[:1000]}", response=r)
            for e in sorted(removable):
                rejected.append({"email": e, "reason": "rejected by HubSpot as invalid"})
            chunk = [inp for inp in chunk if inp["id"] not in removable]
        else:
            raise requests.HTTPError(
                "HubSpot kept rejecting this batch after removing every address it named; "
                f"last response: {r.text[:600]}", response=r)
    return results, rejected


def associate_contacts(contact_ids: list[str], object_type_id: str, to_object_id: str):
    assoc_spec = association_resolve.get_association_type(object_type_id)
    inputs = [{"from": {"id": cid}, "to": {"id": to_object_id}, "types": [assoc_spec]} for cid in contact_ids]
    total = 0
    for i in range(0, len(inputs), 2000):  # HubSpot v4 associations batch limit
        chunk = inputs[i:i + 2000]
        r = request_with_retry(
            "POST", f"https://api.hubapi.com/crm/v4/associations/contacts/{object_type_id}/batch/create",
            headers=_headers(), json={"inputs": chunk}, timeout=60,
        )
        if not r.ok:
            raise requests.HTTPError(f"{r.status_code} {r.reason} for {r.url}: {r.text[:1000]}", response=r)
        total += len(r.json().get("results", []))
    return total


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

    upsert_results, rejected_invalid = batch_upsert_contacts(valid_rows)
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
        # Surfaced so a dropped contact is visible, not silently missing.
        "rejected_invalid_email": rejected_invalid,
        "dropped_invalid_email": len(rejected_invalid),
    }
