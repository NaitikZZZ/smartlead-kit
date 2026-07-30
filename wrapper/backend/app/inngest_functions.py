"""Inngest function definitions. Starting with a minimal connectivity-test
function before the real run-engine rewrite - confirms the whole chain
(client -> FastAPI webhook -> Inngest Cloud -> function execution -> step
memoization) actually works end to end before betting the run engine on it.
"""
import datetime

import inngest

from .inngest_client import client


@client.create_function(
    fn_id="connectivity_test",
    trigger=inngest.TriggerEvent(event="test/connectivity"),
)
async def connectivity_test(ctx: inngest.Context, step: inngest.Step) -> dict:
    async def _step_one():
        return {"hello": "from step one"}

    result = await step.run("step_one", _step_one)
    return {"received_data": ctx.event.data, "step_result": result}


@client.create_function(
    fn_id="wait_test",
    trigger=inngest.TriggerEvent(event="test/wait_start"),
)
async def wait_test(ctx: inngest.Context, step: inngest.Step) -> dict:
    """Mirrors the real pattern: do some work, pause for an external answer
    (matching this run's own id via if_exp, same as multiple concurrent runs
    would need), resume once it arrives, do more work."""
    run_key = ctx.event.data["run_key"]

    async def _before():
        return {"stage": "before wait"}

    before = await step.run("before", _before)

    answer_event = await step.wait_for_event(
        "wait_for_answer",
        event="test/wait_answer",
        timeout=datetime.timedelta(minutes=5),
        if_exp=f"async.data.run_key == '{run_key}'",
    )

    async def _after():
        return {"stage": "after wait", "answer_received": answer_event.data if answer_event else None}

    after = await step.run("after", _after)
    return {"before": before, "after": after, "timed_out": answer_event is None}


@client.create_function(
    fn_id="refresh_exclusion_cache",
    trigger=inngest.TriggerEvent(event="cron/refresh_exclusion"),
)
async def refresh_exclusion_cache(ctx: inngest.Context, step: inngest.Step) -> dict:
    """Rebuilds the HubSpot DNU cache across as many slices as it takes.

    Needed because a full rebuild can't fit in one Vercel invocation (~972s of
    work measured against the live list, against a 300s function cap) and the
    obvious fix - a frequent cron - isn't available: Vercel rejects sub-daily
    cron schedules on Hobby plans. Inngest gives each step.run() its own fresh
    invocation, so N sequential steps get N x 300s while Inngest handles the
    durability and retries. The daily cron just emits the trigger event.

    Each slice persists its own cursor/progress to Redis (see
    hubspot_exclusion.refresh_cache_resumable), so a step that does get killed
    mid-slice only loses that slice's work, not the whole build."""
    from .pipeline import hubspot_exclusion

    async def _fresh_check():
        return {"fresh": hubspot_exclusion.cache_is_fresh()}

    if (await step.run("cache_fresh_check", _fresh_check))["fresh"]:
        return {"status": "skipped", "reason": "cache is fresh and no build in progress"}

    # Bounded so a pathological case can't loop forever; ~5 slices is typical.
    for i in range(1, 13):
        async def _slice():
            return hubspot_exclusion.refresh_cache_resumable(budget_seconds=200)

        result = await step.run(f"refresh_slice_{i}", _slice)
        if result.get("done"):
            return {"status": "done", "slices": i, **result}
    return {"status": "incomplete", "slices": 12,
            "note": "hit the slice cap - next scheduled run resumes from saved progress"}
