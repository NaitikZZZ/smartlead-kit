from pathlib import Path

import inngest.fast_api
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .inngest_client import client as inngest_client
from .inngest_functions import connectivity_test, wait_test, refresh_exclusion_cache
from .pipeline.inngest_runner import run_pipeline_slice1
from .routes import cron, runs

app = FastAPI(title="ABM Enrichment Wrapper", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin before wider rollout
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)
app.include_router(cron.router)
inngest.fast_api.serve(app, inngest_client,
                       [connectivity_test, wait_test, run_pipeline_slice1, refresh_exclusion_cache])


@app.get("/api/config")
def get_config():
    resolved_sheet = config.resolve_account_mapping_sheet_path()
    exclusion_list_url = config.exclusion_list_url()
    return {
        "account_mapping_sheet_configured": bool(resolved_sheet),
        "account_mapping_sheet_file": Path(resolved_sheet).name if resolved_sheet else None,
        "github_pr_enabled": bool(config.GITHUB_TOKEN and config.GITHUB_REPO),
        "apollo_configured": bool(config.APOLLO_API_KEY),
        "hubspot_read_configured": bool(config.HUBSPOT_READ_TOKEN),
        "hubspot_write_configured": bool(config.HUBSPOT_WRITE_TOKEN),
        "interakt_configured": bool(config.INTERAKT_API_KEY),
        "exclusion_list_name": "ABM EXCLSIONS - DNU",
        "exclusion_list_id": config.HUBSPOT_EXCLUSION_LIST_ID,
        "exclusion_list_url": exclusion_list_url,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
