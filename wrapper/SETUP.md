# ABM Wrapper - Team Setup Guide

The ABM wrapper is an interactive web tool that runs your enrichment pipeline end-to-end without touching scripts. The team can upload a CSV or select a HubSpot Project, and the tool handles domain resolution → enrichment → HubSpot import.

## Prerequisites

You'll need these once, at instance-startup time:

### Secrets (Backend)
Set these in your `.env` or Render dashboard (never commit them):
- `SMARTLEAD_API_KEY` — for HeyReach push (optional, but recommended)
- `ANTHROPIC_API_KEY` — for completeness fill-in and web scraping
- `HUBSPOT_PRIVATE_APP_KEY` — read from "ABM EXCLSIONS - DNU" list (28280) + write contacts
- `GITHUB_TOKEN` + `GITHUB_REPO` — auto-commit output files to a branch (optional)
- `HEYREACH_API_KEY` — LinkedIn list import (optional)

If a key is missing, that step is skipped gracefully (completeness, HeyReach push, etc.).

### Secrets (Frontend)
- `VITE_API_BASE` — set to your deployed backend URL (e.g., `https://wrapper-api.mycompany.com`)

### Caching
- **Exclusion domains**: The tool pulls HubSpot list 28280 (ABM EXCLSIONS - DNU) once and caches the domain set at `backend/cache/exclusion_domains_28280.json`. Set a daily refresh job to keep it current:
  ```bash
  cd wrapper/backend && ./.venv/bin/python -m app.pipeline.hubspot_exclusion
  ```
  Without this, the first run on a new instance rebuilds it inline (~10-15 min).

- **Apollo lookups**: Email reveals, person reveals, and phone reveals are cached in `backend/cache/` so re-runs never re-charge Apollo. Job-change rows bypass the cache and force-refresh automatically.

## Local Development

### Backend (Python FastAPI)
```bash
cd wrapper/backend

# One-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Fill in your secrets (see Prerequisites above)
# Then start the server
uvicorn app.main:app --reload --port 8731
```

Backend runs at `http://localhost:8731`. The health check is `GET /health`.

### Frontend (React + Vite)
```bash
cd wrapper/frontend

# One-time setup
npm install

# Start dev server (talks to http://localhost:8731 by default)
npm run dev
```

Frontend runs at `http://localhost:5173`. If your backend is elsewhere, set `VITE_API_BASE`:
```bash
VITE_API_BASE=http://localhost:8731 npm run dev
```

## Deployment (Render)

Both services are defined in `render.yaml`:

1. **Backend**: Python FastAPI service
   - Set all secrets in Render's dashboard (don't commit them)
   - Render auto-builds from `requirements.txt` and starts with `uvicorn`

2. **Frontend**: Static site (built React bundle)
   - Set `VITE_API_BASE` to your backend's URL
   - Render auto-builds with `npm run build` and serves the `dist/` folder

After deployment, share the frontend URL with the team.

## How the Team Uses It

### For a CSV Upload
1. Open the tool → select "CSV Upload"
2. Upload your prospect CSV (columns: `Company Name`, optionally `Domain`, `# Employees`, `Industry`)
3. Optionally upload an Account Mapping Sheet (for exclusion checking)
4. Walk through the steps:
   - **Normalization**: automatic
   - **Completeness**: fills missing domains/industries via Claude + web search
   - **Exclusion**: checks against HubSpot "ABM EXCLSIONS - DNU" list
   - **Enrichment**: resolves domains, searches Apollo, reveals emails/phones
   - **Naming**: auto-suggests a campaign name (editable)
   - **Output**: generates 3 files (email_upload, linkedin_upload, calling_upload)
   - **Associations**: link to HubSpot Partner / Project / Event (optional, or just a static list)
   - **Review & Confirm**: preview the data, then write to HubSpot

### For a HubSpot Project
1. Open the tool → select "HubSpot Project"
2. Paste the project name or URL
3. The tool pulls the campaign context (ICP region, employee size, concept) and asks for a prospect CSV
4. Rest is the same as CSV upload

### Output Files
Three CSVs are always written to the run's output directory:
- **email_upload.csv**: Verified email only (blank emails excluded), ready for HubSpot import
- **linkedin_upload.csv**: HeyReach format (LinkedIn URLs); pushed to HeyReach as a new list if configured
- **calling_upload.csv**: Phone numbers + names, ready for a dialer

## Key Features

- **Cost visibility**: Before running Apollo enrichment, the tool estimates the credit cost and shows the breakdown (Domain / Email / Phone). Only uncached lookups are charged.
- **Activity log**: Every action is logged with a timestamp. You can see exactly what's happening and how long each step takes.
- **Job-change handling**: Rows flagged with "Started role last N months" bypass the cache and are force-refreshed (old company data is stale).
- **HeyReach integration**: LinkedIn file is auto-pushed to a new HeyReach list (named after your campaign) if `HEYREACH_API_KEY` is set.
- **GitHub auto-commit**: Output files can be auto-committed to a GitHub branch with a PR opened (requires `GITHUB_TOKEN` + `GITHUB_REPO`).
- **Best-effort architecture**: HeyReach failures, GitHub failures, etc., don't sink the HubSpot import — they're reported but non-blocking.

## Troubleshooting

### "No cache found" / Slow first run
The first run on a new instance builds the exclusion domain cache inline (~10-15 min). Set up the daily refresh job to avoid this next time:
```bash
cd wrapper/backend && ./.venv/bin/python -m app.pipeline.hubspot_exclusion
```

### "Missing ANTHROPIC_API_KEY" / Completeness skipped
If you don't set `ANTHROPIC_API_KEY`, completeness fill-in is skipped. Optional, but recommended for better domain/industry coverage.

### "Apollo rate limit" / Temporary backoff
If you hit Apollo's rate limit, the tool pauses and retries. Usually resolves in a few minutes.

### "HeyReach push failed"
If the LinkedIn file can't be pushed to HeyReach (bad API key, rate limit, etc.), the HubSpot import still succeeds. The error is logged and reported in the UI.

## Maintenance

- **Daily**: Refresh the HubSpot exclusion cache (see Prerequisites)
- **Weekly**: Check the activity logs to see which campaigns ran and how long they took
- **As needed**: Clear `backend/cache/` if you suspect stale lookups (then redeploy, and the next run will rebuild)

## Architecture Notes

- **In-memory job store**: Runs are stored in memory. A backend restart loses in-flight state, but finished output files survive on disk.
- **Single instance**: Not built for heavy concurrent load. Fine for a small team (5-10 concurrent runs). For scale, add job queueing (Redis + Celery).
- **No auth**: Put it behind your org's SSO/VPN before wider rollout.

## Questions?

Slack: @naitik or check the activity log in the UI for detailed timestamps and status messages.
