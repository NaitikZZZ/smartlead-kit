import math
import mimetypes
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

import inngest
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .. import config, run_status, vercel_blob
from ..inngest_client import client as inngest_client
from ..models import AnswerRequest, ImportConfirmRequest, PendingQuestion, RunStatus
from ..pipeline import runner, input_sources, outputs

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _engine_for(run_id: str) -> Optional[str]:
    """'inngest' or 'legacy' depending on which engine created this run_id, or
    None if neither has a record of it. The two engines use disjoint storage
    (Redis run_status vs. the in-process JOBS dict) so a run_id can only ever
    belong to one - CSV runs go to Inngest; hubspot_project runs stay on the
    legacy thread-based engine until that input path is ported too."""
    if run_status.get(run_id):
        return "inngest"
    if runner.get_job(run_id):
        return "legacy"
    return None


def _nan_safe(o):
    """Recursively strip NaN/Infinity (and numpy scalars) from anything about
    to be JSON-serialized - FastAPI/Starlette use allow_nan=False and 500 on a
    stray NaN, which is how a run showed 'Out of range float values are not
    JSON compliant'."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _nan_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_nan_safe(v) for v in o]
    if hasattr(o, "item"):  # numpy scalar
        try:
            v = o.item()
        except Exception:
            return o
        return None if (isinstance(v, float) and not math.isfinite(v)) else v
    return o


@router.post("", response_model=RunStatus)
async def create_run(
    input_source: str = Form(...),
    hubspot_project_id: Optional[str] = Form(None),
    campaign_idea: Optional[str] = Form(None),
    company_col: Optional[str] = Form(None),
    domain_col: Optional[str] = Form(None),
    employee_col: Optional[str] = Form(None),
    csv_file: Optional[UploadFile] = File(None),
    mapping_sheet_file: Optional[UploadFile] = File(None),  # accepted for request-shape compat, unused (confirmed-dead feature)
):
    csv_bytes = await csv_file.read() if csv_file else None
    csv_filename = csv_file.filename if csv_file else None

    if input_source == "csv" and not csv_bytes:
        raise HTTPException(400, "csv input source requires csv_file")
    if input_source == "hubspot_project" and not hubspot_project_id:
        raise HTTPException(400, "hubspot_project input source requires hubspot_project_id")
    if input_source == "campaign_idea" and not (campaign_idea and campaign_idea.strip()):
        raise HTTPException(400, "campaign_idea input source requires a non-empty campaign_idea")
    if input_source not in ("csv", "hubspot_project", "campaign_idea"):
        raise HTTPException(400, f"Unsupported input_source {input_source!r} (form-link source is temporarily disabled)")

    # Both input sources now run on the Inngest engine (mapping_sheet_file is
    # a confirmed-dead feature - accepted here for backward compatibility but
    # never referenced by either engine). runner.start_run()/_execute() stay
    # on disk, unused from here, as a fallback until this has real mileage.
    run_id = uuid.uuid4().hex[:12]
    run_status.init(run_id)  # synchronous, so an immediate GET right after this returns never 404s
    event_data = {
        "run_id": run_id, "input_source": input_source,
        "company_col": company_col, "domain_col": domain_col, "employee_col": employee_col,
    }
    if csv_bytes:
        csv_blob_pathname = f"runs/{run_id}/{csv_filename}"
        vercel_blob.put(csv_blob_pathname, csv_bytes, content_type=csv_file.content_type if csv_file else None)
        event_data["csv_blob_pathname"] = csv_blob_pathname
        event_data["csv_filename"] = csv_filename
    if input_source == "hubspot_project":
        event_data["hubspot_project_id"] = hubspot_project_id
    if input_source == "campaign_idea":
        event_data["campaign_idea"] = campaign_idea.strip()

    inngest_client.send_sync(inngest.Event(name="run/start", data=event_data))
    return _to_status(run_id, "inngest")


@router.post("/project-preview")
def project_preview(project_id: str = Body(..., embed=True)):
    """Read-only: resolve a pasted Project ID/URL to its campaign properties, and
    flag whether the linked list can be auto-pulled or must be uploaded (behind
    a login). Lets the UI prompt for a download+upload before the run starts."""
    if not project_id or not str(project_id).strip():
        raise HTTPException(400, "project_id (record ID or URL) is required")
    try:
        meta = input_sources.fetch_hubspot_project(project_id)
    except Exception as e:
        raise HTTPException(400, str(e))
    return _nan_safe({
        "project": meta,
        "list_fetchable": input_sources.is_link_autofetchable(meta.get("target_list_link")),
        # Web-page lists can be auto-extracted via the Claude CLI (your account)
        # or an API key.
        "list_scrapable": meta.get("list_link_kind") == "webpage"
        and (bool(config.ANTHROPIC_API_KEY) or bool(os.environ.get("CLAUDE_CODE_EXECPATH"))),
    })


@router.get("/{run_id}", response_model=RunStatus)
def get_run(run_id: str):
    engine = _engine_for(run_id)
    if engine is None:
        raise HTTPException(404, "Run not found")
    return _to_status(run_id, engine)


@router.post("/{run_id}/answer", response_model=RunStatus)
def answer_question(run_id: str, body: AnswerRequest):
    engine = _engine_for(run_id)
    if engine is None:
        raise HTTPException(404, "Run not found")

    if engine == "inngest":
        job = run_status.get(run_id)
        pq = job.get("pending_question")
        if not pq or pq["key"] != body.key:
            raise HTTPException(400, f"No pending question with key {body.key!r} for this run right now")
        inngest_client.send_sync(inngest.Event(
            name="run/answer", data={"run_id": run_id, "key": body.key, "value": body.value}))
    else:
        try:
            runner.submit_answer(run_id, body.key, body.value)
        except ValueError as e:
            raise HTTPException(400, str(e))

    return _to_status(run_id, engine)


@router.get("/{run_id}/files/{filename}")
def download_file(run_id: str, filename: str):
    run_dir = config.RUNS_DIR / run_id
    if not outputs.file_exists(run_dir, filename):
        raise HTTPException(404, "File not found")
    content = outputs.read_file(run_dir, filename)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/import")
def confirm_import(run_id: str, body: ImportConfirmRequest):
    if not body.confirm:
        raise HTTPException(400, "confirm must be true to run this - this writes to HubSpot")

    engine = _engine_for(run_id)
    if engine is None:
        raise HTTPException(404, "Run not found")

    if engine == "inngest":
        job = run_status.get(run_id)
        if job.get("stage") != "awaiting_import_confirmation":
            raise HTTPException(400, "Run has no HubSpot-ready output yet (still running or failed)")
        # The frontend discards this response body and learns the real result
        # (stats.hubspot_import, hubspot_list_url, stage) via its existing
        # GET /{run_id} poll loop, same as every other paused-then-resumed
        # step - the HubSpot import itself runs in the background via Inngest,
        # not inline in this request.
        inngest_client.send_sync(inngest.Event(
            name="run/answer", data={"run_id": run_id, "key": "confirm_import", "value": True}))
        return {"status": "confirmed", "run_id": run_id}

    job = runner.get_job(run_id)
    run_dir = config.RUNS_DIR / run_id
    if not outputs.file_exists(run_dir, "hubspot_ready.json"):
        raise HTTPException(400, "Run has no HubSpot-ready output yet (still running or failed)")

    runner._update(run_id, stage="importing_to_hubspot")
    try:
        result = runner.run_confirmed_import(run_id, run_dir)
    except Exception as e:
        traceback.print_exc()  # full traceback to the server log - str(e) alone isn't enough to diagnose later
        runner._update(run_id, stage="failed", error=str(e), message="Import failed")
        raise HTTPException(500, str(e))
    return _nan_safe(result)


def _to_status(run_id: str, engine: str) -> RunStatus:
    job = run_status.get(run_id) if engine == "inngest" else runner.get_job(run_id)
    pq = job.get("pending_question")
    # Surface the activity log + overall elapsed time alongside stats (stats is a
    # free-form dict, so no schema change needed).
    stats = dict(job.get("stats", {}))
    stats["log"] = job.get("log", [])
    if job.get("started_at"):
        stats["elapsed_s"] = round(time.time() - job["started_at"], 1)
    stats = _nan_safe(stats)
    return RunStatus(
        run_id=run_id, stage=job["stage"], message=job.get("message", ""), error=job.get("error"),
        stats=stats,
        output_files=[Path(p).name for p in job.get("output_files", [])],
        pr_url=job.get("pr_url"),
        hubspot_list_url=job.get("hubspot_list_url"),
        pending_question=PendingQuestion(**pq) if pq else None,
    )
