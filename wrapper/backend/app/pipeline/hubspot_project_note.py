"""Posts a run's final SUMMARY.md to its linked HubSpot record(s) as a note -
the ONE scoped write exception to this pipeline's otherwise read-only
HubSpot access (every other HubSpot write stays limited to the explicit,
user-confirmed contact/list import in hubspot_import.py).

This fires autonomously wherever a run's summary becomes final (see
runner.run_confirmed_import / inngest_runner.run_pipeline_slice1) - there is
no dedicated API route for it and no user click. A run's resolved
associations list can carry any combination of "project", "partner", and
"event" entries (see association_resolve.resolve()); every kind actually
present gets its own copy of the same note, posted to that record - a run
linked to two or three of them gets two or three independent notes. A
HubSpot failure on one association (auth, network, 4xx) must never stop the
others from being attempted, and must never fail an already-completed run -
post_summary_note() swallows every exception per-association and just logs
a warning.

Auth matches the other read-side HubSpot calls in this package (see
association_resolve.py/hubspot_exclusion.py) - HUBSPOT_PRIVATE_APP_TOKEN,
not the separate HUBSPOT_WRITE_TOKEN hubspot_import.py uses for the contact
upsert."""
from __future__ import annotations

import logging
import time

from .. import config
from .association_resolve import OBJECT_TYPE
from .hubspot_retry import request_with_retry

logger = logging.getLogger(__name__)

NOTES_URL = "https://api.hubapi.com/crm/v3/objects/notes"
_NOTE_ASSOC_URL = (
    "https://api.hubapi.com/crm/v4/objects/notes/{note_id}/associations/default/"
    "{object_type_id}/{record_id}"
)


def _headers() -> dict:
    token = config.require("HUBSPOT_PRIVATE_APP_TOKEN", config.HUBSPOT_READ_TOKEN)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _summary_to_html(summary_markdown: str) -> str:
    """Cheap markdown->HTML for the note body: reuses the SUMMARY.md text
    as-is (no re-deriving a field list) so the note mirrors exactly what the
    frontend lets the user download, just wrapping each non-blank line in
    <p> so HubSpot's note editor doesn't render it as one run-on line."""
    lines = (summary_markdown or "").splitlines()
    return "".join(f"<p>{line.strip()}</p>" for line in lines if line.strip())


def _record_ids(associations: list[dict] | None) -> dict[str, str]:
    """Returns {kind: record_id} for every project/partner/event
    association actually present and resolved on this run - each present
    kind gets its own note, independent of the others."""
    out: dict[str, str] = {}
    for assoc in associations or []:
        kind = assoc.get("kind")
        if kind in OBJECT_TYPE and assoc.get("record_id"):
            out[kind] = str(assoc["record_id"])
    return out


def _post_and_associate(kind: str, record_id: str, note_body_html: str) -> str:
    headers = _headers()
    payload = {
        "properties": {
            "hs_note_body": note_body_html,
            "hs_timestamp": str(int(time.time() * 1000)),
        }
    }
    r = request_with_retry("POST", NOTES_URL, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    note_id = r.json()["id"]

    r2 = request_with_retry(
        "PUT",
        _NOTE_ASSOC_URL.format(note_id=note_id, object_type_id=OBJECT_TYPE[kind], record_id=record_id),
        headers=headers, timeout=15,
    )
    r2.raise_for_status()
    return note_id


def post_summary_note(associations: list[dict] | None, summary_markdown: str) -> dict[str, str]:
    """No-ops (returns {}) unless this run has at least one resolved
    project/partner/event association. Otherwise posts one copy of the same
    summary note to EACH present association's record - project, partner,
    and event are independent, so a run linked to two or three of them gets
    two or three separate notes. One association's HubSpot failure is
    logged and skipped; it never stops the others and never raises. Returns
    {kind: note_id} for whichever posts succeeded."""
    record_ids = _record_ids(associations)
    if not record_ids:
        return {}

    note_body_html = _summary_to_html(summary_markdown)
    posted: dict[str, str] = {}
    for kind, record_id in record_ids.items():
        try:
            note_id = _post_and_associate(kind, record_id, note_body_html)
            logger.info(f"Posted HubSpot summary note {note_id} to {kind} {record_id}")
            posted[kind] = note_id
        except Exception as e:
            logger.warning(f"Failed to post HubSpot summary note to {kind} {record_id}: {e}")
    return posted
