from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routes import runs

app = FastAPI(title="ABM Enrichment Wrapper", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin before wider rollout
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)


@app.get("/api/config")
def get_config():
    resolved_sheet = config.resolve_account_mapping_sheet_path()
    return {
        "account_mapping_sheet_configured": bool(resolved_sheet),
        "account_mapping_sheet_file": Path(resolved_sheet).name if resolved_sheet else None,
        "github_pr_enabled": bool(config.GITHUB_TOKEN and config.GITHUB_REPO),
        "apollo_configured": bool(config.APOLLO_API_KEY),
        "hubspot_read_configured": bool(config.HUBSPOT_READ_TOKEN),
        "hubspot_write_configured": bool(config.HUBSPOT_WRITE_TOKEN),
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
