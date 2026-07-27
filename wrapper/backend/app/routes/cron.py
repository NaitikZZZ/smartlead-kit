"""Scheduled cache-refresh endpoints, meant to be hit only by Vercel Cron Jobs
(see vercel.json) - never by a real user request. The exclusion-list rebuild
takes ~25-30 min and the association-dropdown rebuild takes tens of seconds;
neither should ever run inline inside a request a human is waiting on, which
is why hubspot_exclusion.py/association_resolve.py no longer have an
inline-rebuild-on-stale-cache fallback - see their load_exclusion_records()/
list_records() docstrings.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from .. import config
from ..pipeline import association_resolve, hubspot_exclusion

router = APIRouter(prefix="/api/cron", tags=["cron"])


def _verify_cron_secret(authorization: Optional[str]):
    """Vercel sends `Authorization: Bearer {CRON_SECRET}` on every Cron Job
    invocation. Reject (even locally, even if CRON_SECRET isn't set) rather
    than silently allow - a public GET to these routes would otherwise let
    anyone trigger a ~25-30 min HubSpot rebuild."""
    expected = f"Bearer {config.CRON_SECRET}" if config.CRON_SECRET else None
    if not expected or authorization != expected:
        raise HTTPException(401, "Unauthorized")


@router.get("/refresh-exclusion")
def refresh_exclusion(authorization: Optional[str] = Header(None)):
    _verify_cron_secret(authorization)
    meta = hubspot_exclusion.refresh_cache()
    return {"status": "ok", "record_count": meta["record_count"], "built_at": meta["built_at"]}


@router.get("/refresh-associations")
def refresh_associations(authorization: Optional[str] = Header(None), kinds: str = Query("project,partner,event")):
    _verify_cron_secret(authorization)
    kind_list = [k.strip() for k in kinds.split(",") if k.strip() in ("project", "partner", "event")]
    result = association_resolve.refresh_cache(kind_list or None)
    return {"status": "ok", "counts": result}
