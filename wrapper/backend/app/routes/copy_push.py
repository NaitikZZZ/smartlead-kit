"""Copy Push (CLAUDE.md "Flow 2"): push already-written copy - email, LinkedIn,
or WhatsApp - into a campaign, independent of any contact/lead data.

Standalone by default. Optionally chains onto a just-completed Flow 1 (Data
push) run via source_run_id, in which case it reuses that run's real HeyReach
list_id and campaign title instead of creating a placeholder empty list.

Synchronous by design, unlike runs.py's Inngest-backed pipeline - parsing copy
(pipeline/copy_import.py - deterministic, no LLM call) and making a handful of
REST calls to Smartlead/HeyReach/Interakt all complete well within a normal
request, so there's no need for the durable-workflow machinery the enrichment
pipeline needs. State between the parse step and the confirm step is still
needed (the user reviews/edits the parsed copy in between), so it reuses
run_status.py's generic Redis-backed store under its own "cp_" id space - same
mechanism, unrelated shape.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import config, run_status
from ..models import CopyPushConfirmRequest, CopyPushStatus
from ..pipeline import copy_import, heyreach, interakt, runner, smartlead

router = APIRouter(prefix="/api/copy-push", tags=["copy-push"])

_VALID_CHANNELS = {"smartlead", "heyreach", "interakt"}

# Region -> keyword to match against a Smartlead mailbox-group tag name, so
# the sender-selection UI can auto-suggest the right group from the same
# region value Copy Push already asks for. Keyword match is substring,
# case-insensitive, against list_account_tags()'s real tag names (confirmed
# live 2026-10-12: "GCC/KSA Email Accounts", "SEA Email Accounts", "India
# Email Accounts", "Africa Email Accounts", "Indonesia Email Accounts",
# "US Team's Email ID"). No match for UKEU/GLOBAL - no such tag exists yet.
_REGION_TAG_KEYWORD = {
    "IND": "india", "IDN": "indonesia", "US": "us team",
    "GCC": "gcc", "KSA": "gcc", "PHL": "sea", "AFR": "africa",
}


@router.get("/senders/heyreach")
def heyreach_senders(search: Optional[str] = None):
    if not heyreach.is_configured():
        return {"status": "not_configured", "accounts": []}
    try:
        accounts = heyreach.list_senders()
    except Exception as e:
        return {"status": "error", "message": f"Could not load HeyReach senders: {e}", "accounts": []}
    if search:
        q = search.lower()
        accounts = [a for a in accounts if q in f"{a.get('firstName', '')} {a.get('lastName', '')} {a.get('emailAddress', '')}".lower()]
    return {"status": "ok", "accounts": [
        {"id": a["id"], "name": f"{a.get('firstName', '')} {a.get('lastName', '')}".strip(),
         "email": a.get("emailAddress"), "active": a.get("isActive", False)}
        for a in accounts
    ]}


@router.get("/senders/smartlead/groups")
def smartlead_sender_groups(region: Optional[str] = None):
    if not smartlead.is_configured():
        return {"status": "not_configured", "groups": []}
    try:
        tags = smartlead.list_account_tags()
    except Exception as e:
        return {"status": "error", "message": f"Could not load Smartlead mailbox groups: {e}", "groups": [], "suggested_tag_id": None}
    suggested_id = None
    keyword = _REGION_TAG_KEYWORD.get((region or "").upper())
    if keyword:
        match = next((t for t in tags if keyword in (t.get("name") or "").lower()), None)
        suggested_id = match["id"] if match else None
    return {"status": "ok", "groups": tags, "suggested_tag_id": suggested_id}


@router.get("/senders/smartlead")
def smartlead_senders(search: Optional[str] = None):
    if not smartlead.is_configured():
        return {"status": "not_configured", "accounts": []}
    try:
        return {"status": "ok", "accounts": smartlead.list_email_accounts(search=search)}
    except Exception as e:
        return {"status": "error", "message": f"Could not load Smartlead senders: {e}", "accounts": []}


def _source_run_context(source_run_id: str) -> dict:
    """Pull campaign title + HeyReach list_id off a completed Flow 1 run, from
    whichever engine created it (see routes/runs.py's _engine_for - duplicated
    narrowly here rather than importing a private helper across modules)."""
    job = run_status.get(source_run_id) or runner.get_job(source_run_id)
    if not job:
        raise HTTPException(404, f"source_run_id {source_run_id!r} not found")
    stats = job.get("stats", {})
    heyreach_result = (stats.get("hubspot_import") or {}).get("heyreach", {})
    return {
        "campaign_title": stats.get("campaign_title"),
        "heyreach_list_id": heyreach_result.get("list_id") if heyreach_result.get("status") == "pushed" else None,
    }


def _get_or_404(push_id: str) -> dict:
    job = run_status.get(push_id)
    if not job:
        raise HTTPException(404, "Copy push not found")
    return job


def _to_status(push_id: str, job: dict) -> CopyPushStatus:
    return CopyPushStatus(
        push_id=push_id, stage=job.get("stage", "failed"), message=job.get("message", ""),
        error=job.get("error"), channels=job.get("channels", []), warnings=job.get("warnings", []),
        mapped=job.get("mapped", {}), result=job.get("result", {}),
    )


@router.post("", response_model=CopyPushStatus)
async def start_copy_push(
    channels: str = Form(...),  # comma-separated: "smartlead,heyreach"
    campaign_name: str = Form(...),
    copy_text: Optional[str] = Form(None),
    source_run_id: Optional[str] = Form(None),
    is_cxo: bool = Form(False),
    region: Optional[str] = Form(None),
    copy_file: Optional[UploadFile] = File(None),
):
    selected = [c.strip() for c in channels.split(",") if c.strip()]
    invalid = set(selected) - _VALID_CHANNELS
    if invalid:
        raise HTTPException(400, f"Unknown channel(s): {', '.join(invalid)}")
    if not selected:
        raise HTTPException(400, "At least one channel is required")
    if not campaign_name.strip():
        raise HTTPException(400, "campaign_name is required")

    file_bytes: Optional[bytes] = None
    filename: Optional[str] = None
    if copy_file is not None:
        file_bytes = await copy_file.read()
        filename = copy_file.filename or "copy.xlsx"
    elif not (copy_text and copy_text.strip()):
        raise HTTPException(400, "Provide copy_text or copy_file")

    warnings: list[str] = []
    heyreach_list_id = None
    campaign_title = campaign_name

    if source_run_id:
        ctx = _source_run_context(source_run_id)
        campaign_title = ctx["campaign_title"] or campaign_name
        heyreach_list_id = ctx["heyreach_list_id"]

    # Deliberately NOT creating the HeyReach placeholder list here - this is
    # the parse/preview step, and the UI promises nothing is sent anywhere
    # until confirm. The actual create_list() call (if still needed) happens
    # in confirm_copy_push, right before the push - just warn about it now.
    if "heyreach" in selected and heyreach_list_id is None:
        if source_run_id:
            warnings.append(f"source_run_id {source_run_id!r} has no pushed HeyReach list - "
                            "an empty one will be created on confirm.")
        else:
            warnings.append("No existing list to attach to - an empty HeyReach list will be created on confirm. "
                            "Add the real contacts/list yourself in HeyReach before starting this campaign.")

    if "heyreach" in selected and is_cxo:
        warnings.append(
            "CXO/exec targeting noted, but the Open Profile routing branch (InMail before connecting) is an "
            "unvalidated draft (docs/heyreach-default-workflow.md) and isn't built here - the validated "
            "CHECK_IS_CONNECTION cadence is used regardless. Build and test the open-profile branch by hand "
            "in the HeyReach UI if this campaign needs it."
        )

    if "interakt" in selected and (region or "").upper() not in config.COPY_PUSH_WHATSAPP_REGIONS:
        warnings.append(
            f"Region {region!r} is outside the standing-rule WhatsApp regions "
            f"({', '.join(sorted(config.COPY_PUSH_WHATSAPP_REGIONS))}) - confirm this is intentional before pushing."
        )

    mapped = {}
    for channel in selected:
        mapped[channel] = copy_import.parse_copy(channel, text=copy_text, filename=filename, file_bytes=file_bytes)

    push_id = f"cp_{uuid.uuid4().hex[:12]}"
    job = {
        "stage": "awaiting_review", "channels": selected, "mapped": mapped, "warnings": warnings,
        "message": "Copy parsed - review before pushing.",
        "_campaign_title": campaign_title, "_heyreach_list_id": heyreach_list_id,
    }
    run_status.update(push_id, **job)
    return _to_status(push_id, job)


@router.get("/{push_id}", response_model=CopyPushStatus)
def get_copy_push(push_id: str):
    return _to_status(push_id, _get_or_404(push_id))


@router.post("/{push_id}/confirm", response_model=CopyPushStatus)
def confirm_copy_push(push_id: str, body: CopyPushConfirmRequest):
    if not body.confirm:
        raise HTTPException(400, "confirm must be true to run this")
    job = _get_or_404(push_id)
    if job.get("stage") != "awaiting_review":
        raise HTTPException(400, f"Copy push is not awaiting review (current stage: {job.get('stage')!r})")

    mapped = dict(job.get("mapped", {}))
    if body.edited_mapping:
        for channel, correction in body.edited_mapping.items():
            if channel in mapped:
                mapped[channel] = {"status": "done", "mapped": correction}

    campaign_title = job.get("_campaign_title")
    heyreach_list_id = job.get("_heyreach_list_id")
    result = {}

    for channel in job.get("channels", []):
        entry = mapped.get(channel, {})
        if entry.get("status") != "done":
            result[channel] = {"status": "skipped", "message": "No valid mapped copy for this channel - fix and retry."}
            continue
        copy = entry["mapped"]

        if channel == "smartlead":
            result[channel] = smartlead.push_campaign_copy(
                campaign_title, copy,
                sender_account_ids=body.smartlead_sender_account_ids,
                sender_tag_id=body.smartlead_sender_tag_id,
            )
        elif channel == "heyreach":
            if heyreach_list_id is None and not heyreach.is_configured():
                result[channel] = {"status": "not_configured", "message": "HEYREACH_API_KEY not set"}
                continue
            if heyreach_list_id is None:
                try:
                    heyreach_list_id = heyreach.create_list(campaign_title)
                except Exception as e:
                    result[channel] = {"status": "error", "message": f"Could not create the placeholder HeyReach list: {e}"}
                    continue
            result[channel] = heyreach.push_campaign_copy(campaign_title, heyreach_list_id, copy,
                                                              sender_ids=body.heyreach_sender_ids)
        elif channel == "interakt":
            result[channel] = interakt.check_template(copy.get("name", campaign_title))

    job = run_status.update(push_id, stage="done", message="Push attempted - see per-channel result.",
                            mapped=mapped, result=result)
    return _to_status(push_id, job)
