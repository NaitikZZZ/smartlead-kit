from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import config
from ..models import AnswerRequest, ImportConfirmRequest, PendingQuestion, RunStatus
from ..pipeline import runner

router = APIRouter(prefix="/api/runs", tags=["runs"])


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
    return result


def _to_status(run_id: str) -> RunStatus:
    job = runner.get_job(run_id)
    pq = job.get("pending_question")
    return RunStatus(
        run_id=run_id, stage=job["stage"], message=job.get("message", ""), error=job.get("error"),
        stats=job.get("stats", {}),
        output_files=[Path(p).name for p in job.get("output_files", [])],
        pr_url=job.get("pr_url"),
        hubspot_list_url=job.get("hubspot_list_url"),
        pending_question=PendingQuestion(**pq) if pq else None,
    )
