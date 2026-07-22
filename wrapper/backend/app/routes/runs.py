import math
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..models import AnswerRequest, ImportConfirmRequest, PendingQuestion, RunStatus
from ..pipeline import runner, input_sources

router = APIRouter(prefix="/api/runs", tags=["runs"])


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
    company_col: Optional[str] = Form(None),
    domain_col: Optional[str] = Form(None),
    employee_col: Optional[str] = Form(None),
    csv_file: Optional[UploadFile] = File(None),
    mapping_sheet_file: Optional[UploadFile] = File(None),
):
    csv_bytes = await csv_file.read() if csv_file else None
    csv_filename = csv_file.filename if csv_file else None
    mapping_bytes = await mapping_sheet_file.read() if mapping_sheet_file else None
    mapping_filename = mapping_sheet_file.filename if mapping_sheet_file else None

    if input_source == "csv" and not csv_bytes:
        raise HTTPException(400, "csv input source requires csv_file")
    if input_source == "hubspot_project" and not hubspot_project_id:
        raise HTTPException(400, "hubspot_project input source requires hubspot_project_id")
    if input_source not in ("csv", "hubspot_project"):
        raise HTTPException(400, f"Unsupported input_source {input_source!r} (form-link source is temporarily disabled)")

    run_id = runner.start_run(
        input_source=input_source,
        csv_bytes=csv_bytes, csv_filename=csv_filename,
        hubspot_project_id=hubspot_project_id,
        mapping_sheet_bytes=mapping_bytes, mapping_sheet_filename=mapping_filename,
        company_col=company_col, domain_col=domain_col, employee_col=employee_col,
    )
    return _to_status(run_id)


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
    job = runner.get_job(run_id)
    if not job:
        raise HTTPException(404, "Run not found")
    return _to_status(run_id)


@router.post("/{run_id}/answer", response_model=RunStatus)
def answer_question(run_id: str, body: AnswerRequest):
    job = runner.get_job(run_id)
    if not job:
        raise HTTPException(404, "Run not found")
    try:
        runner.submit_answer(run_id, body.key, body.value)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _to_status(run_id)


@router.get("/{run_id}/files/{filename}")
def download_file(run_id: str, filename: str):
    path = config.RUNS_DIR / run_id / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename)


@router.post("/{run_id}/import")
def confirm_import(run_id: str, body: ImportConfirmRequest):
    if not body.confirm:
        raise HTTPException(400, "confirm must be true to run this - this writes to HubSpot")
    job = runner.get_job(run_id)
    if not job:
        raise HTTPException(404, "Run not found")

    run_dir = config.RUNS_DIR / run_id
    if not (run_dir / "hubspot_ready.json").exists():
        raise HTTPException(400, "Run has no HubSpot-ready output yet (still running or failed)")

    runner._update(run_id, stage="importing_to_hubspot")
    try:
        result = runner.run_confirmed_import(run_id, run_dir)
    except Exception as e:
        runner._update(run_id, stage="failed", error=str(e), message="Import failed")
        raise HTTPException(500, str(e))
    return _nan_safe(result)


def _to_status(run_id: str) -> RunStatus:
    job = runner.get_job(run_id)
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
