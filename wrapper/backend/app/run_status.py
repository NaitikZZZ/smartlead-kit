"""Redis-backed run status - replaces runner.py's in-memory JOBS dict (which
only works because one process stays running for the whole interactive
ask/answer flow; Vercel serverless gives no such guarantee). Same field
shape as the RunStatus model, so routes/runs.py's response contract - and
therefore the frontend - needs no changes once this is what backs it.

No cross-process locking here (Redis itself has none via the plain REST
GET/SET pattern used) - acceptable because Inngest executes one function
run's steps sequentially, so concurrent writers to the SAME run_id shouldn't
happen in practice. Revisit with a proper CAS/lock if that stops being true.
"""
from __future__ import annotations

import time

from . import redis_cache


def _key(run_id: str) -> str:
    return f"run_status:{run_id}"


def init(run_id: str) -> None:
    redis_cache.set_json(_key(run_id), {
        "run_id": run_id, "stage": "queued", "message": "Queued", "error": None,
        "stats": {}, "output_files": [], "pr_url": None, "hubspot_list_url": None,
        "pending_question": None, "started_at": time.time(), "log": [],
        "_associations": [], "_campaign_title": None,
    })


def get(run_id: str) -> dict:
    return redis_cache.get_json(_key(run_id)) or {}


def update(run_id: str, **kwargs) -> dict:
    """Mirrors runner.py's _update(): merges kwargs into the stored job dict,
    appending to the activity log when `message` changes."""
    job = get(run_id)
    if "message" in kwargs and kwargs["message"]:
        msg = kwargs["message"]
        log = job.setdefault("log", [])
        if not log or log[-1]["msg"] != msg:
            started = job.get("started_at")
            elapsed = round(time.time() - started, 1) if started else 0.0
            log.append({"elapsed_s": elapsed, "msg": msg})
    job.update(kwargs)
    redis_cache.set_json(_key(run_id), job)
    return job


def humanize_seconds(seconds) -> str:
    if seconds is None:
        return None
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes / 60:.1f}h"


def set_step(run_id: str, key: str, title: str, status: str, summary=None, seconds=None, cost=None) -> None:
    """Mirrors runner.py's _step(): upsert a step's status/summary/time/cost
    into stats["steps"] (ordered), tracking real elapsed time via started_at."""
    job = get(run_id)
    stats = job.setdefault("stats", {})
    steps = stats.setdefault("steps", [])
    prev = next((s for s in steps if s["key"] == key), None)
    started_at = prev.get("started_at") if prev else None
    now = time.time()
    if status == "running" and not started_at:
        started_at = now

    if seconds is not None:
        time_str = humanize_seconds(seconds)
    else:
        time_str = prev.get("time") if prev else None
    elapsed_s = prev.get("elapsed_s") if prev else None

    if status in ("done", "skipped") and started_at:
        elapsed_s = round(now - started_at, 1)
        time_str = humanize_seconds(elapsed_s)

    entry = {"key": key, "title": title, "status": status, "summary": summary,
             "time": time_str, "elapsed_s": elapsed_s, "cost": cost, "started_at": started_at}
    if prev is not None:
        steps[steps.index(prev)] = entry
    else:
        steps.append(entry)

    job["stats"] = stats
    redis_cache.set_json(_key(run_id), job)


def set_stat(run_id: str, key: str, value) -> None:
    """Mirrors runner.py's stats[key] = value pattern (e.g. stats["domain_resolution"],
    stats["exclusion"]) - a structured result object per pipeline stage, distinct from
    the human-readable summary text stored in stats["steps"] by set_step()."""
    job = get(run_id)
    stats = job.setdefault("stats", {})
    stats[key] = value
    job["stats"] = stats
    redis_cache.set_json(_key(run_id), job)


def accrue_cost(run_id: str, block: dict) -> None:
    job = get(run_id)
    stats = job.setdefault("stats", {})
    c = stats.setdefault("cost", {"credits": 0, "usd": 0.0, "breakdown": []})
    c["credits"] += block["credits"]
    c["usd"] = round(c["usd"] + block["usd"], 2)
    c["breakdown"].append(block)
    job["stats"] = stats
    redis_cache.set_json(_key(run_id), job)
