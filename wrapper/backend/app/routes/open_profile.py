"""Open profile check: a teammate pastes a Sales Navigator search link and later downloads two lists
(open profile, not open) plus a summary.

This module is the intake and results layer only. The real work (split the search, import into Waalaxy
through Chrome, export, merge by Premium) is done by a worker machine that follows
.claude/skills/sales-nav-open-profile and reports back through the worker routes below using
open_profile_app/worker_cli.py. Checks run one at a time because the shared Waalaxy account allows it.

Storage: job records and events in Upstash Redis, result files in Vercel Blob, so the page works
while the worker machine is off. Without Upstash / Blob configured (local dev, tests) it falls back to
in-process memory. Files are stored and served in parts of at most PART_BYTES because Vercel functions
cannot accept or return bodies much over 4.5 MB; the page stitches the parts back together.
"""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from .. import audit, config, redis_cache, vercel_blob
from ..auth import Actor, require_user

router = APIRouter(prefix="/api/open-profile", tags=["open-profile"], dependencies=[Depends(require_user)])
worker_router = APIRouter(prefix="/api/open-profile-worker", tags=["open-profile-worker"])

PART_BYTES = 3_000_000
STAGES = ["queued", "sizing", "importing", "merging", "done"]
# kind -> (stored file name, label used in the download name, required for completion)
FILES = {
    "open-profile": ("open-profile.csv", "open-profile", True),
    "not-open": ("not-open.csv", "not-open", True),
    "master": ("master.csv", "all-leads", True),
    "summary": ("SUMMARY.md", "summary", False),
}
PREVIEW_COLUMNS = [
    ("Name", ("firstName", "lastName")),
    ("Title", ("occupation", "job_title")),
    ("Location", ("location",)),
    ("Profile", ("linkedinUrl",)),
]
RECENT = 60


# --------------------------------------------------------------------------- storage

class _Memory:
    """Local dev and tests: no Upstash or Blob needed. Process-local, so it resets on restart."""
    kv: dict = {}
    files: dict = {}


def _redis() -> bool:
    return redis_cache.is_configured()


def _cmd(*args):
    return redis_cache._pipeline([[str(a) for a in args]])[0]


def kv_get(key: str) -> Optional[str]:
    return _cmd("GET", key) if _redis() else _Memory.kv.get(key)


def kv_mget(keys: list) -> list:
    if not keys:
        return []
    if _redis():
        return redis_cache._pipeline([["GET", k] for k in keys])
    return [_Memory.kv.get(k) for k in keys]


def kv_set(key: str, value: str) -> None:
    if _redis():
        _cmd("SET", key, value)
    else:
        _Memory.kv[key] = value


def kv_setnx(key: str, value: str) -> bool:
    if _redis():
        return _cmd("SET", key, value, "NX") == "OK"
    if key in _Memory.kv:
        return False
    _Memory.kv[key] = value
    return True


def kv_del(key: str) -> None:
    if _redis():
        _cmd("DEL", key)
    else:
        _Memory.kv.pop(key, None)


def kv_incr(key: str) -> int:
    if _redis():
        return int(_cmd("INCR", key))
    n = int(_Memory.kv.get(key, "0")) + 1
    _Memory.kv[key] = str(n)
    return n


def kv_push(key: str, value: str, front: bool = False) -> None:
    if _redis():
        _cmd("LPUSH" if front else "RPUSH", key, value)
        return
    lst = _Memory.kv.setdefault(key, [])
    lst.insert(0, value) if front else lst.append(value)


def kv_list(key: str, start: int, stop: int) -> list:
    if _redis():
        return _cmd("LRANGE", key, start, stop) or []
    lst = _Memory.kv.get(key, [])
    return lst[start:] if stop == -1 else lst[start:stop + 1]


def file_put(path: str, data: bytes) -> None:
    if vercel_blob.is_configured():
        vercel_blob.put(path, data, "application/octet-stream")
    else:
        _Memory.files[path] = data


def file_get(path: str) -> Optional[bytes]:
    if not vercel_blob.is_configured():
        return _Memory.files.get(path)
    try:
        return vercel_blob.get(vercel_blob.url_for(path))
    except Exception:
        return None


# --------------------------------------------------------------------------- helpers

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_url(raw: str) -> str:
    """Canonical Sales Navigator people-search URL, or ValueError with a reason a teammate can act on."""
    raw = (raw or "").strip()
    m = re.match(r"^https?://([^/?#]+)(/[^?#]*)?(\?[^#]*)?", raw)
    if not m:
        raise ValueError("That does not look like a link. Copy the full address from your browser.")
    host, path, qs = m.group(1).lower(), m.group(2) or "", (m.group(3) or "")[1:]
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise ValueError("This is not a LinkedIn link.")
    if path.startswith("/sales/lists"):
        raise ValueError("This is a saved list. Open a people search instead, then copy its link.")
    if not path.startswith("/sales/search/people"):
        raise ValueError("We need a Sales Navigator people search link. It starts with linkedin.com/sales/search/people.")
    keep = [p for p in qs.split("&") if p.split("=", 1)[0] in ("query", "savedSearchId")]
    if not keep:
        raise ValueError("This link has no filters. Apply your filters in Sales Navigator, then copy the link.")
    return "https://www.linkedin.com/sales/search/people?" + "&".join(keep)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "check"


def _job(job_id: str) -> Optional[dict]:
    raw = kv_get(f"opc:job:{job_id}")
    return json.loads(raw) if raw else None


def _need(job_id: str) -> dict:
    job = _job(job_id)
    if not job:
        raise HTTPException(404, "We could not find that check.")
    return job


def _save(job: dict) -> None:
    job["updated_at"] = now()
    kv_set(f"opc:job:{job['id']}", json.dumps(job))


def _recent(limit: int = RECENT) -> list:
    ids = kv_list("opc:index", 0, limit - 1)
    return [j for j in (json.loads(r) if r else None for r in kv_mget([f"opc:job:{i}" for i in ids])) if j]


def _event(job_id: str, message: str) -> None:
    last = kv_list(f"opc:events:{job_id}", -1, -1)
    if last and json.loads(last[-1])["message"] == message:
        return
    kv_push(f"opc:events:{job_id}", json.dumps({"ts": now(), "message": message}))


def _cancel_requested(job_id: str) -> bool:
    return kv_get(f"opc:cancel:{job_id}") is not None


def _view(job: dict, jobs: Optional[list] = None, events: bool = False) -> dict:
    d = {k: v for k, v in job.items() if k != "files"}
    d["cancelling"] = job["status"] == "running" and _cancel_requested(job["id"])
    d["queue_ahead"] = 0
    if job["status"] == "queued":
        pool = jobs if jobs is not None else _recent(200)
        d["queue_ahead"] = sum(1 for j in pool if j["status"] in ("queued", "running") and j["seq"] < job["seq"])
    d["files"] = sorted((job.get("files") or {}).keys()) if job["status"] == "done" else []
    if events:
        rows = kv_list(f"opc:events:{job['id']}", 0, -1)[-100:]
        d["events"] = [json.loads(r) for r in rows]
    return d


def _release_running(job_id: str) -> None:
    if kv_get("opc:running") == job_id:
        kv_del("opc:running")


# --------------------------------------------------------------------------- user routes

class NewJob(BaseModel):
    url: str
    name: Optional[str] = None


@router.post("/jobs")
def create_job(body: NewJob, request: Request, actor: Actor = Depends(require_user)) -> dict:
    try:
        url = normalize_url(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    pool = _recent(200)
    dup = next((j for j in pool if j["url"] == url and j["status"] in ("queued", "running")), None)
    if dup:
        return {"job": _view(dup, pool), "duplicate": True}
    job_id = secrets.token_hex(6)
    ts = now()
    job = {
        "id": job_id, "url": url, "name": (body.name or "").strip()[:80] or f"Check from {actor.name}",
        "requester": actor.name, "status": "queued", "stage": "queued", "percent": 0,
        "message": "Waiting for its turn", "eta_minutes": None, "total_leads": None, "unique_leads": None,
        "open_count": None, "not_open_count": None, "unknown_count": None, "expected_total": None,
        "captured_total": None, "error": None, "seq": kv_incr("opc:seq"), "files": {},
        "created_at": ts, "updated_at": ts, "started_at": None, "finished_at": None,
    }
    _save(job)
    kv_push("opc:index", job_id, front=True)
    _event(job_id, "Check requested")
    audit.log(actor.name, "open_profile_requested", actor.ip, job_id=job_id)
    return {"job": _view(job), "duplicate": False}


@router.get("/jobs")
def list_jobs() -> dict:
    pool = _recent()
    return {"jobs": [_view(j, pool) for j in sorted(pool, key=lambda j: -j["seq"])]}


@router.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    return {"job": _view(_need(job_id), events=True)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, actor: Actor = Depends(require_user)) -> dict:
    job = _need(job_id)
    if job["status"] not in ("queued", "running"):
        raise HTTPException(409, "This check is already finished.")
    kv_set(f"opc:cancel:{job_id}", actor.name)
    if job["status"] == "queued":
        job.update(status="cancelled", message="Cancelled", finished_at=now())
        _save(job)
        _event(job_id, "Cancelled before it started")
    else:
        job["message"] = "Stopping safely"
        _save(job)
        _event(job_id, "Cancel requested, stopping safely")
    audit.log(actor.name, "open_profile_cancelled", actor.ip, job_id=job_id)
    return {"job": _view(_need(job_id))}


@router.get("/jobs/{job_id}/files/{kind}/{part}")
def download_part(job_id: str, kind: str, part: int) -> Response:
    """One piece of a result file. The page fetches parts 0..parts-1 and stitches them together."""
    job = _need(job_id)
    meta = (job.get("files") or {}).get(kind)
    if job["status"] != "done" or kind not in FILES or not meta:
        raise HTTPException(404, "This file is not ready yet.")
    if not 0 <= part < meta["parts"]:
        raise HTTPException(404, "No such part.")
    data = file_get(f"opc/{job_id}/{kind}.part{part}")
    if data is None:
        raise HTTPException(404, "This file is not available right now. Try again in a moment.")
    ext = FILES[kind][0].rsplit(".", 1)[-1]
    return Response(content=data, media_type="application/octet-stream", headers={
        "X-Parts": str(meta["parts"]), "X-Total-Bytes": str(meta["bytes"]),
        "X-Filename": f"{slug(job['name'])}-{FILES[kind][1]}.{ext}",
        "Access-Control-Expose-Headers": "X-Parts, X-Total-Bytes, X-Filename",
    })


@router.get("/jobs/{job_id}/preview/{kind}")
def preview(job_id: str, kind: str, n: int = Query(8, ge=1, le=25)) -> dict:
    if kind not in ("open-profile", "not-open"):
        raise HTTPException(404, "Unknown list.")
    job = _need(job_id)
    data = file_get(f"opc/{job_id}/{kind}.part0") if job["status"] == "done" else None
    if data is None:
        raise HTTPException(404, "This list is not ready yet.")
    rows = []
    for r in csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace"))):
        rows.append({label: " ".join(v for v in ((r.get(c) or "").strip() for c in cols) if v) for label, cols in PREVIEW_COLUMNS})
        if len(rows) >= n:
            break
    return {"columns": [c for c, _ in PREVIEW_COLUMNS], "rows": rows}


# --------------------------------------------------------------------------- worker routes

def _require_worker(token: Optional[str]) -> None:
    expected = config.OPEN_PROFILE_WORKER_TOKEN
    if not expected or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Worker token missing or wrong.")


class Progress(BaseModel):
    stage: str
    percent: float
    message: str = ""
    eta_minutes: Optional[int] = None
    total_leads: Optional[int] = None


class Complete(BaseModel):
    unique_leads: int
    open_count: int
    not_open_count: int
    unknown_count: int = 0
    expected_total: Optional[int] = None
    captured_total: Optional[int] = None


class Fail(BaseModel):
    message: str = ""
    cancelled: bool = False


@worker_router.post("/claim")
def claim(x_worker_token: Optional[str] = Header(None)) -> dict:
    """The running job (so a restarted worker resumes it), else start the oldest queued one."""
    _require_worker(x_worker_token)
    rid = kv_get("opc:running")
    if rid:
        running = _job(rid)
        if running and running["status"] == "running":
            return {"job": _view(running), "resumed": True}
        kv_del("opc:running")
    for job in sorted((j for j in _recent(200) if j["status"] == "queued"), key=lambda j: j["seq"]):
        if _cancel_requested(job["id"]):
            job.update(status="cancelled", message="Cancelled", finished_at=now())
            _save(job)
            continue
        if not kv_setnx("opc:running", job["id"]):
            current = _job(kv_get("opc:running") or "")
            return {"job": _view(current) if current else None, "resumed": True}
        job.update(status="running", stage="sizing", percent=2, message="Reading your search", started_at=now())
        _save(job)
        _event(job["id"], "Started")
        return {"job": _view(job), "resumed": False}
    return {"job": None}


@worker_router.post("/jobs/{job_id}/progress")
def progress(job_id: str, body: Progress, x_worker_token: Optional[str] = Header(None)) -> dict:
    _require_worker(x_worker_token)
    if body.stage not in STAGES[1:4]:
        raise HTTPException(422, f"stage must be one of {STAGES[1:4]}")
    job = _need(job_id)
    if job["status"] != "running":
        raise HTTPException(409, f"Check is {job['status']}, not running.")
    job.update(stage=body.stage, percent=max(0.0, min(99.0, body.percent)), message=body.message,
               eta_minutes=body.eta_minutes)
    if body.total_leads is not None:
        job["total_leads"] = body.total_leads
    _save(job)
    if body.message:
        _event(job_id, body.message)
    return {"cancel": _cancel_requested(job_id)}


@worker_router.put("/jobs/{job_id}/files/{kind}")
async def upload_part(job_id: str, kind: str, request: Request, part: int = Query(..., ge=0),
                      parts: int = Query(..., ge=1, le=50), x_worker_token: Optional[str] = Header(None)) -> dict:
    """One piece (at most PART_BYTES) of a result file. Send every part 0..parts-1, then call complete."""
    _require_worker(x_worker_token)
    if kind not in FILES:
        raise HTTPException(404, "Unknown file kind.")
    job = _need(job_id)
    if job["status"] != "running":
        raise HTTPException(409, f"Check is {job['status']}, not running.")
    data = await request.body()
    if len(data) > PART_BYTES + 1024:
        raise HTTPException(413, f"Parts must be at most {PART_BYTES} bytes.")
    if part >= parts:
        raise HTTPException(422, "part must be smaller than parts.")
    file_put(f"opc/{job_id}/{kind}.part{part}", data)
    kv_set(f"opc:up:{job_id}:{kind}:{part}", str(len(data)))
    kv_set(f"opc:up:{job_id}:{kind}:parts", str(parts))
    return {"ok": True, "part": part, "bytes": len(data)}


@worker_router.post("/jobs/{job_id}/complete")
def complete(job_id: str, body: Complete, x_worker_token: Optional[str] = Header(None)) -> dict:
    _require_worker(x_worker_token)
    job = _need(job_id)
    if job["status"] != "running":
        raise HTTPException(409, f"Check is {job['status']}, not running.")
    files = {}
    for kind, (_, _, required) in FILES.items():
        n = kv_get(f"opc:up:{job_id}:{kind}:parts")
        if n is None:
            if required:
                raise HTTPException(422, f"Upload {kind} before completing.")
            continue
        sizes = kv_mget([f"opc:up:{job_id}:{kind}:{i}" for i in range(int(n))])
        if any(s is None for s in sizes):
            raise HTTPException(422, f"{kind} is missing some parts. Upload all {n} parts.")
        files[kind] = {"parts": int(n), "bytes": sum(int(s) for s in sizes)}
    ts = now()
    job.update(status="done", stage="done", percent=100, message="Your lists are ready", eta_minutes=None,
               unique_leads=body.unique_leads, open_count=body.open_count, not_open_count=body.not_open_count,
               unknown_count=body.unknown_count, expected_total=body.expected_total,
               captured_total=body.captured_total, files=files, finished_at=ts)
    _save(job)
    _event(job_id, "Lists are ready")
    _release_running(job_id)
    return {"job": _view(job)}


@worker_router.post("/jobs/{job_id}/fail")
def fail(job_id: str, body: Fail, x_worker_token: Optional[str] = Header(None)) -> dict:
    _require_worker(x_worker_token)
    job = _need(job_id)
    if job["status"] not in ("queued", "running"):
        raise HTTPException(409, f"Check is already {job['status']}.")
    job.update(status="cancelled" if body.cancelled else "failed",
               message="Cancelled" if body.cancelled else "Needs attention",
               error=None if body.cancelled else body.message, finished_at=now())
    _save(job)
    _event(job_id, "Cancelled" if body.cancelled else f"Stopped: {body.message}")
    _release_running(job_id)
    return {"job": _view(job)}
