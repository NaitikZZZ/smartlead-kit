"""Apollo credit/cost model + rough per-step time estimates.

Cost basis is the team's actual Apollo contract: $13,566 for 720,000 credits,
so one credit costs ~$0.018842. Only the paid Apollo operations consume
credits - people *search* is free on the plan, revealing email/phone/org data
is what costs. These are surfaced in the run stats so the UI can show a cost
breakdown before and after each paid step (and a running total for the run).
"""
from __future__ import annotations

APOLLO_CONTRACT_DOLLARS = 13566.0
APOLLO_CONTRACT_CREDITS = 720000
COST_PER_CREDIT = APOLLO_CONTRACT_DOLLARS / APOLLO_CONTRACT_CREDITS  # ~0.018842

# Credits consumed per unit of work. People search itself is free; the cost is
# in revealing data. Kept conservative and easy to tune in one place.
CREDITS = {
    "domain_resolution": 1,   # per company org-enrich / domain lookup
    "email_reveal": 1,        # per contact email unlock
    "mobile_phone": 1,        # per contact phone/mobile unlock
}

# Rough wall-clock seconds per unit, for the "time estimate" shown per step.
SECONDS_PER_UNIT = {
    "normalize": 0.002,
    "domain_resolution": 0.6,
    "exclusion": 0.05,
    "people_discovery": 0.8,
    "email_reveal": 0.5,
    "mobile_phone": 0.5,
    "outputs": 0.01,
}


def dollars(credits: int | float) -> float:
    return round(credits * COST_PER_CREDIT, 2)


def estimate_credits(operation: str, units: int) -> int:
    return CREDITS.get(operation, 0) * max(0, int(units))


def cost_block(operation: str, units: int) -> dict:
    """A small, JSON-friendly cost record for one paid operation."""
    credits = estimate_credits(operation, units)
    return {
        "operation": operation,
        "units": int(units),
        "credits": credits,
        "usd": dollars(credits),
        "cost_per_credit": round(COST_PER_CREDIT, 6),
    }


def estimate_seconds(operation: str, units: int) -> float:
    return round(SECONDS_PER_UNIT.get(operation, 0.01) * max(0, int(units)), 1)


def humanize_seconds(seconds: float) -> str:
    seconds = max(0, round(seconds))
    if seconds < 60:
        return f"~{seconds}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"~{minutes:.1f} min"
    return f"~{minutes / 60:.1f} hr"
