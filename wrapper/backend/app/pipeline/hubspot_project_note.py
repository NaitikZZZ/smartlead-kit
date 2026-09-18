"""Posts a run's final SUMMARY.md to its linked HubSpot Project record as a
note - the ONE scoped write exception to this pipeline's otherwise
read-only HubSpot access (every other HubSpot write stays limited to the
explicit, user-confirmed contact/list import in hubspot_import.py).

This fires autonomously wherever a run's summary becomes final (see
runner.run_confirmed_import / inngest_runner.run_pipeline_slice1) - there is
no dedicated API route for it and no user click. Only a "project"
association ever gets a note; "partner"/"event" associations are left
untouched. A HubSpot failure here (auth, network, 4xx) must never fail an
already-completed run - post_summary_note() swallows every exception and
just logs a warning.

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
    f"{OBJECT_TYPE['project']}/" "{project_id}"
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


def _project_record_id(associations: list[dict] | None) -> str | None:
    for assoc in associations or []:
        if assoc.get("kind") == "project" and assoc.get("record_id"):
            return str(assoc["record_id"])
    return None


def _post_and_associate(project_id: str, summary_markdown: str) -> str:
    headers = _headers()
    payload = {
        "properties": {
            "hs_note_body": _summary_to_html(summary_markdown),
            "hs_timestamp": str(int(time.time() * 1000)),
        }
    }
    r = request_with_retry("POST", NOTES_URL, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    note_id = r.json()["id"]

    r2 = request_with_retry(
        "PUT", _NOTE_ASSOC_URL.format(note_id=note_id, project_id=project_id),
        headers=headers, timeout=15,
    )
    r2.raise_for_status()
    return note_id


def post_summary_note(associations: list[dict] | None, summary_markdown: str) -> str | None:
    """No-ops (returns None) unless this run has a resolved "project"
    association - "partner"/"event" associations never get a note. Otherwise
    posts one note carrying the run's final summary and associates it to
    that Project record. Never raises."""
    project_id = _project_record_id(associations)
    if not project_id:
        return None
    try:
        note_id = _post_and_associate(project_id, summary_markdown)
        logger.info(f"Posted HubSpot summary note {note_id} to Project {project_id}")
        return note_id
    except Exception as e:
        logger.warning(f"Failed to post HubSpot summary note to Project {project_id}: {e}")
        return None
