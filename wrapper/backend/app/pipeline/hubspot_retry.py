"""Shared retry wrapper for HubSpot write calls in the import flow
(batch upsert, list create/add, associations). These all fire back-to-back
in a single request and share one portal-wide per-second rate limit, so a
handful of writes - or any other job hitting the same portal at the same
moment - is enough to trip HubSpot's "secondly limit". None of the call
sites had any 429 handling, so a transient rate-limit hit became a hard
failure instead of a retry. Honors Retry-After when HubSpot sends one."""
from __future__ import annotations
import time

import requests

_MAX_ATTEMPTS = 5


def request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(_MAX_ATTEMPTS):
        r = requests.request(method, url, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == _MAX_ATTEMPTS - 1:
                return r
            retry_after = r.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else (2 ** attempt)
            time.sleep(delay)
            continue
        return r
    return r
