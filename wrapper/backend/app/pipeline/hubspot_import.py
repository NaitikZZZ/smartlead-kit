"""HubSpot contact batch-upsert + Partner/Project/Event associations,
mirroring the flow validated against the live Xoxoday portal this session.
Only ever called after an explicit confirm from the API caller - never runs
as part of the automatic pipeline stages."""
from __future__ import annotations
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .. import config
from . import association_resolve, hubspot_lists
from .hubspot_retry import request_with_retry

# Own handler: the app configures no root logging, so plain INFO would be dropped.
logger = logging.getLogger("import_timing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s"))
    logger.addHandler(_h)


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

_EMAIL_TOKEN_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _split_multi_email_rows(rows: list[dict]) -> list[dict]:
    """A source list sometimes crams several addresses into one `email` cell
    (e.g. "a@x.com / info@x.com", seen live from a business-card-scan import -
    HubSpot then 400s the whole compound string as invalid rather than
    accepting any part of it). Extract every address-shaped token out of the
    cell and fan the row out into one copy per address, so each real email
    still gets a contact instead of the whole row silently dropping. A row
    with exactly one address (the common case) passes through with its email
    normalized to just that token; a row with none is left as-is so the
    existing _valid_email guard drops it as before."""
    out = []
    for r in rows:
        tokens = _EMAIL_TOKEN_RE.findall(str(r.get("email") or ""))
        if not tokens:
            out.append(r)
            continue
        for t in tokens:
            out.append({**r, "email": t})
    return out


def _collapse_escaped_backslashes(s: str) -> str:
    """A genuinely backslash-containing address (e.g. a typo'd
    "andrew\\.osborne-hunt@go1.com") comes back from HubSpot at two different
    escaping depths: once inside the top-level `message` summary, which is
    itself a JSON-encoded string (so its backslashes are doubled), and once
    in the `errors` array (single-encoded). Collapse either back to the real
    address by repeatedly halving doubled backslashes until stable, so both
    occurrences match the locally-held id regardless of which one HubSpot
    named."""
    while "\\\\" in s:
        s = s.replace("\\\\", "\\")
    return s


def _invalid_emails_from_error(body: str) -> set[str]:
    """Pulls the addresses HubSpot named as invalid out of a 400 body.

    HubSpot reports these both in the top-level `message` and in an `errors`
    array, and may name several at once, so parse the raw text rather than
    depending on one shape. Lowercased to match how the inputs are keyed."""
    return {
        _collapse_escaped_backslashes(m.group(1).strip().strip('\\"')).lower()
        for m in _INVALID_EMAIL_RE.finditer(body or "")
    }



# HubSpot's contact batch upsert caps at 100 inputs per call. Batches are
# independent (emails are deduped across the WHOLE import before splitting, so
# no address can appear in two batches) and share only the portal-wide burst
# limit (190+ req/10s), so they run concurrently. One import chunk of
# IMPORT_CHUNK_SIZE contacts is exactly _UPSERT_WORKERS batches in flight.
_UPSERT_BATCH = 100
_UPSERT_WORKERS = 10
IMPORT_CHUNK_SIZE = 1000  # contacts per Inngest step; keeps each step well under the 300s limit


def _build_inputs(rows: list[dict]) -> list[dict]:
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
    for r in _split_multi_email_rows(rows):
        if not _valid_email(r.get("email")):
            continue
        email = str(r["email"]).strip().lower()
        if email in seen_emails:
            continue
        seen_emails.add(email)
        props = {k: _json_safe(v) for k, v in r.items()}
        props["email"] = email
        inputs.append({"idProperty": "email", "id": email, "properties": props})
    return inputs


def prepare_import(rows: list[dict]) -> tuple[list[dict], int]:
    """Returns (upsert inputs, count of rows dropped for a blank email).
    Pure and deterministic, so safe to recompute on every Inngest replay."""
    valid_rows = [r for r in rows if _valid_email(r.get("email"))]
    return _build_inputs(valid_rows), len(rows) - len(valid_rows)


def split_chunks(inputs: list[dict], size: int = IMPORT_CHUNK_SIZE) -> list[list[dict]]:
    return [inputs[i:i + size] for i in range(0, len(inputs), size)]


def _upsert_one_batch(chunk: list[dict], batch_no: int) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    rejected: list[dict] = []
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
        t0 = time.monotonic()
        r = request_with_retry(
            "POST", "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert",
            headers=_headers(), json={"inputs": chunk}, timeout=60,
        )
        logger.info("hubspot_import upsert batch %d attempt %d: %d rows, http %s, %.1fs",
                    batch_no, _attempt + 1, len(chunk), r.status_code, time.monotonic() - t0)
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


def upsert_inputs(inputs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Upserts already-prepared inputs in concurrent batches of 100. Results
    keep input order. Raises the first batch failure (after in-flight batches
    finish - upserts are idempotent, so a retry of the caller is safe)."""
    batches = [inputs[i:i + _UPSERT_BATCH] for i in range(0, len(inputs), _UPSERT_BATCH)]
    if not batches:
        return [], []
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(_UPSERT_WORKERS, len(batches))) as pool:
        outs = list(pool.map(_upsert_one_batch, batches, range(len(batches))))
    results = [x for res, _ in outs for x in res]
    rejected = [x for _, rej in outs for x in rej]
    logger.info("hubspot_import upsert total: %d contacts in %d batches, %.1fs", len(results), len(batches), time.monotonic() - t0)
    return results, rejected


def batch_upsert_contacts(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    return upsert_inputs(_build_inputs(rows))


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


def create_import_list(campaign_title: str) -> dict:
    """Invariant #2: always create a static list on import. Created once, up
    front, so every chunk adds to the SAME list."""
    t0 = time.monotonic()
    list_id = hubspot_lists.create_list(campaign_title)
    logger.info("hubspot_import list create: %.1fs", time.monotonic() - t0)
    return {"list_id": list_id, "list_url": hubspot_lists.list_url(list_id)}


def import_chunk(inputs: list[dict], list_id: str, associations: list[dict]) -> dict:
    """Upserts one chunk, then adds it to the list and associates it, with the
    list add and each association running concurrently (independent calls).
    Every call is idempotent, so a retried chunk step just repeats it."""
    t0 = time.monotonic()
    results, rejected = upsert_inputs(inputs)
    ids = [r["id"] for r in results]
    assoc_counts: dict[str, int] = {}
    if ids:
        with ThreadPoolExecutor(max_workers=1 + len(associations)) as pool:
            add_f = pool.submit(hubspot_lists.add_members, list_id, ids)
            assoc_fs = {
                a["kind"]: pool.submit(associate_contacts, ids, association_resolve.OBJECT_TYPE[a["kind"]], a["record_id"])
                for a in associations
            }
            add_f.result()
            assoc_counts = {kind: f.result() for kind, f in assoc_fs.items()}
    logger.info("hubspot_import chunk: %d contacts upserted+listed+associated, %.1fs", len(ids), time.monotonic() - t0)
    return {
        "contact_ids": ids, "new": sum(1 for r in results if r.get("new")),
        "rejected": rejected, "associated": assoc_counts,
    }


def build_result(dropped: int, list_info: dict, chunk_results: list[dict], associations: list[dict]) -> dict:
    contact_ids = [i for c in chunk_results for i in c["contact_ids"]]
    new_count = sum(c["new"] for c in chunk_results)
    rejected = [x for c in chunk_results for x in c["rejected"]]
    assoc_results = {
        a["kind"]: {"record_id": a["record_id"], "associated": sum(c["associated"].get(a["kind"], 0) for c in chunk_results)}
        for a in associations
    }
    return {
        "total": len(contact_ids), "new": new_count, "updated": len(contact_ids) - new_count,
        "dropped_blank_email": dropped, "contact_ids": contact_ids,
        "list": {**list_info, "members_added": len(contact_ids)}, "associations": assoc_results,
        # Surfaced so a dropped contact is visible, not silently missing.
        "rejected_invalid_email": rejected,
        "dropped_invalid_email": len(rejected),
    }


def import_contacts_with_list(rows: list[dict], campaign_title: str, associations: list[dict] | None = None):
    """The single, canonical HubSpot import path. Two HARDCODED invariants,
    enforced here so no caller can bypass them:
      1. No blank-email contact is ever uploaded (filtered here AND in batch_upsert).
      2. A static HubSpot list is ALWAYS created for the imported contacts.
    associations: list of {"kind": "partner"|"project"|"event", "record_id": str}.
    The Inngest engine calls prepare_import / create_import_list / import_chunk
    / build_result directly as separate steps; this runs the same pieces in one go.
    """
    associations = associations or []
    inputs, dropped = prepare_import(rows)
    list_info = create_import_list(campaign_title)
    chunk_results = [import_chunk(c, list_info["list_id"], associations) for c in split_chunks(inputs)]
    return build_result(dropped, list_info, chunk_results, associations)
