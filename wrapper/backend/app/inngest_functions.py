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
