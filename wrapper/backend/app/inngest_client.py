"""Shared Inngest client. Mode (dev server vs real Inngest Cloud) is decided
by the SDK itself from the INNGEST_DEV env var - NOT hardcoded here - so
local testing against `npx inngest-cli dev` and production both work without
a code change. Set INNGEST_DEV=http://localhost:8288 (or 1) for local dev."""
import logging

import inngest

from . import config

_logger = logging.getLogger("inngest")
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
    _logger.addHandler(_handler)

client = inngest.Inngest(
    app_id="abm-wrapper",
    event_key=config.INNGEST_EVENT_KEY,
    signing_key=config.INNGEST_SIGNING_KEY,
    logger=_logger,
)
