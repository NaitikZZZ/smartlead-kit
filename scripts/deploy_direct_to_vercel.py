#!/usr/bin/env python3
"""
Direct-file-upload deploy to Vercel via the REST API - the real fix for the
"can't fit the ICP xlsx (or the rest of the monorepo) into an LLM-generated
deploy_to_vercel tool call" problem hit repeatedly in-session.

Root cause: deploy_to_vercel (and any other path where an LLM has to type
out file contents as literal tool-call arguments) requires every file's
bytes to be generated as chat output. Binary content wrapped in base64
tokenizes extremely poorly (~2.5 tokens/char observed for the 44KB ICP
xlsx - roughly 150k tokens for that one file alone), so a monorepo this
size (~75 files, including two 1000+ line pipeline files and one binary
xlsx) can't be embedded in a single message no matter how it's chunked -
confirmed by repeated failed attempts.

This script sidesteps the problem entirely: it uploads each file's raw
bytes straight from disk to Vercel's /v2/files endpoint (one HTTP call per
file, content never touches an LLM context), then creates the deployment
via /v13/deployments referencing each file by its sha1 + size. No content
size limit from a chat context applies here - only Vercel's own (generous)
per-file and per-deployment limits.

Usage:
    python3 scripts/deploy_direct_to_vercel.py [--prod]

Auth: reads the token the Vercel CLI already stored locally (from `vercel
login`) - nothing to configure. Override with VERCEL_TOKEN if you'd rather
supply your own.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import requests

TEAM_ID = "team_4xbCegR173YFeRAt15WIrRYz"
PROJECT_NAME = "abm-wrapper-backend"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Same file set the working git-based deploy uses (confirmed complete and
# correct this session) - every file main.py transitively imports at module
# load time, plus the frontend and the ICP reference workbook. Update this
# list if new files are added to the app; nothing here needs to change for
# file *size* reasons since this path has no chat-context bottleneck.
FILES = [
    "pyproject.toml", "vercel.json", "requirements.txt", "scoring-criteria.md",
    "scripts/resolve_company_domains.py", "scripts/search_company_contacts_apollo.py",
    "scripts/enrich_full_fields_apollo.py", "scripts/enrich_phone_apollo.py",
    "scripts/enrich_contacts_apollo.py",
    "reference/Use cases & ICP.xlsx",
    "wrapper/__init__.py", "wrapper/backend/__init__.py",
    "wrapper/backend/requirements.txt", "wrapper/backend/vercel.json",
    "wrapper/backend/app/__init__.py",
    "wrapper/backend/app/config.py", "wrapper/backend/app/inngest_client.py",
    "wrapper/backend/app/inngest_functions.py", "wrapper/backend/app/main.py",
    "wrapper/backend/app/models.py", "wrapper/backend/app/redis_cache.py",
    "wrapper/backend/app/run_status.py", "wrapper/backend/app/vercel_blob.py",
    "wrapper/backend/app/pipeline/__init__.py",
    "wrapper/backend/app/pipeline/apollo_enrich.py",
    "wrapper/backend/app/pipeline/association_resolve.py",
    "wrapper/backend/app/pipeline/copy_agent.py",
    "wrapper/backend/app/pipeline/domain_resolution.py",
    "wrapper/backend/app/pipeline/estimates.py",
    "wrapper/backend/app/pipeline/exclusion.py",
    "wrapper/backend/app/pipeline/github_pr.py",
    "wrapper/backend/app/pipeline/heyreach.py",
    "wrapper/backend/app/pipeline/hubspot_exclusion.py",
    "wrapper/backend/app/pipeline/hubspot_import.py",
    "wrapper/backend/app/pipeline/hubspot_lists.py",
    "wrapper/backend/app/pipeline/icp_mapper.py",
    "wrapper/backend/app/pipeline/inngest_runner.py",
    "wrapper/backend/app/pipeline/input_sources.py",
    "wrapper/backend/app/pipeline/naming.py",
    "wrapper/backend/app/pipeline/normalize.py",
    "wrapper/backend/app/pipeline/outputs.py",
    "wrapper/backend/app/pipeline/runner.py",
    "wrapper/backend/app/pipeline/web_completeness.py",
    "wrapper/backend/app/pipeline/web_scrape.py",
    "wrapper/backend/app/routes/__init__.py",
    "wrapper/backend/app/routes/cron.py",
    "wrapper/backend/app/routes/runs.py",
    "wrapper/backend/vendor/check_exclusions.py",
    "wrapper/backend/vendor/normalize_data.py",
    "wrapper/frontend/index.html", "wrapper/frontend/package.json",
    "wrapper/frontend/public/favicon.svg", "wrapper/frontend/public/icons.svg",
    "wrapper/frontend/src/App.tsx", "wrapper/frontend/src/components/ActivityLog.tsx",
    "wrapper/frontend/src/components/AddCustomChip.tsx",
    "wrapper/frontend/src/components/CampaignIdeaWizard.tsx",
    "wrapper/frontend/src/components/CostBar.tsx",
    "wrapper/frontend/src/components/LocationMultiSelect.tsx",
    "wrapper/frontend/src/components/QuestionCard.tsx",
    "wrapper/frontend/src/components/ReviewOutputs.tsx",
    "wrapper/frontend/src/components/ReviewUpload.tsx",
    "wrapper/frontend/src/components/SourceForm.tsx",
    "wrapper/frontend/src/components/StageProgress.tsx",
    "wrapper/frontend/src/components/StepCard.tsx",
    "wrapper/frontend/src/components/StepSidebar.tsx",
    "wrapper/frontend/src/components/Tooltip.tsx",
    "wrapper/frontend/src/index.css", "wrapper/frontend/src/lib/api.ts",
    "wrapper/frontend/src/lib/types.ts", "wrapper/frontend/src/main.tsx",
    "wrapper/frontend/src/theme.css",
    "wrapper/frontend/tsconfig.app.json", "wrapper/frontend/tsconfig.json",
    "wrapper/frontend/tsconfig.node.json", "wrapper/frontend/vite.config.ts",
]


def _load_token() -> str:
    env_token = os.environ.get("VERCEL_TOKEN")
    if env_token:
        return env_token
    auth_path = Path.home() / "Library/Application Support/com.vercel.cli/auth.json"
    if not auth_path.exists():
        raise SystemExit(f"No Vercel CLI auth found at {auth_path} and VERCEL_TOKEN not set. Run `vercel login` first.")
    return json.loads(auth_path.read_text())["token"]


def main() -> None:
    target = "production" if "--prod" in sys.argv else None
    token = _load_token()
    headers = {"Authorization": f"Bearer {token}"}

    file_manifest = []
    total_bytes = 0
    for rel in FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            raise SystemExit(f"Missing file: {path}")
        data = path.read_bytes()
        sha1 = hashlib.sha1(data).hexdigest()
        r = requests.post(
            f"https://api.vercel.com/v2/files?teamId={TEAM_ID}",
            headers={**headers, "x-vercel-digest": sha1, "Content-Length": str(len(data))},
            data=data,
            timeout=60,
        )
        if not r.ok:
            raise SystemExit(f"Upload failed for {rel}: {r.status_code} {r.text[:500]}")
        file_manifest.append({"file": rel, "sha": sha1, "size": len(data)})
        total_bytes += len(data)
        print(f"uploaded {rel} ({len(data)} bytes)")

    print(f"\n{len(file_manifest)} files uploaded, {total_bytes} bytes total. Creating {target or 'preview'} deployment...")

    body = {
        "name": PROJECT_NAME,
        "project": PROJECT_NAME,
        "files": file_manifest,
    }
    if target:
        body["target"] = target
    r = requests.post(
        f"https://api.vercel.com/v13/deployments?teamId={TEAM_ID}",
        headers={**headers, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    result = r.json()
    if not r.ok:
        raise SystemExit(f"Deployment creation failed: {r.status_code} {json.dumps(result, indent=2)[:1500]}")

    print(f"\nDeployment created: {result.get('id')}")
    print(f"URL: https://{result.get('url')}")
    print(f"Inspect: {result.get('inspectorUrl', '(none)')}")


if __name__ == "__main__":
    main()
