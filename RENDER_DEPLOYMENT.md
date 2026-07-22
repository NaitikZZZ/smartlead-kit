# Render Deployment Guide

## Prerequisites
- GitHub account with this repo linked
- Render.com account (free)
- API keys for:
  - HubSpot (read + write tokens)
  - Apollo (if using enrichment)
  - Anthropic (optional, for web scraping)

## Quick Deploy (1 click)

1. Go to https://render.com/
2. Connect your GitHub account
3. Click "New +" → "Blueprint"
4. Select this repo
5. Render will auto-detect `render.yaml` and deploy

## Manual Deploy Steps

### Step 1: Create Backend Service
1. Go to Render Dashboard
2. Click "New +" → "Web Service"
3. Connect to GitHub repo `smartlead-kit`
4. Configure:
   - **Name:** `abm-wrapper-api`
   - **Runtime:** Python
   - **Build Command:** `cd wrapper/backend && pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - **Plan:** Free or Paid (free has 15-min auto-sleep)

### Step 2: Add Persistent Disk (for cache)
1. In service settings, go to "Disks"
2. Add disk:
   - **Name:** `cache`
   - **Mount Path:** `/opt/render/cache`
   - **Size:** 1 GB

### Step 3: Set Environment Variables
In "Environment" section, add:

```
PYTHONUNBUFFERED=1
HUBSPOT_PORTAL_ID=6512810
HUBSPOT_APP_SUBDOMAIN=app-na2.hubspot.com
HUBSPOT_EXCLUSION_LIST_ID=28280
HUBSPOT_PRIVATE_APP_TOKEN=<your-token>
HUBSPOT_WRITE_TOKEN=<your-token>
APOLLO_API_KEY=<your-key>
ANTHROPIC_API_KEY=<optional>
GITHUB_TOKEN=<optional>
GITHUB_REPO=<optional>
```

### Step 4: Create Frontend Service
1. Click "New +" → "Static Site"
2. Connect to GitHub repo
3. Configure:
   - **Name:** `abm-wrapper-web`
   - **Build Command:** `cd wrapper/frontend && npm install && npm run build`
   - **Publish Directory:** `wrapper/frontend/dist`
   - **Routes:** Add catch-all route `/` → `/index.html`

### Step 5: Set Up Daily Cache Refresh (Cron)
1. Click "New +" → "Background Worker"
2. Configure:
   - **Name:** `dnu-cache-refresh`
   - **Schedule:** `0 2 * * *` (2 AM daily)
   - **Command:** `cd wrapper/backend && python -m app.pipeline.hubspot_exclusion`

### Step 6: Link Services
1. In Backend service, add environment variable:
   - **FRONTEND_URL:** (copy URL from frontend service once deployed)
2. In Frontend service, update API calls to backend URL

## Cost Estimate
- **Free Tier:** $0 (auto-sleeps after 15 min inactivity)
- **Starter Tier:** $7/month per service (always on)
- **Total for full app:** $14-20/month for team use

## Team Sharing
Once deployed, share with team:
- Frontend URL (from Render dashboard)
- They access the app, no installation needed
- All features work through web browser

## Monitoring
- **Render Dashboard:** View logs, metrics, deployments
- **Cache status:** Check `/api/health` endpoint
- **Auto-redeploy:** Push to GitHub → auto-deploys

## Troubleshooting

### Services won't start
- Check logs in Render dashboard
- Verify all environment variables are set
- Ensure GitHub repo has `render.yaml` in root

### Cache not persisting
- Verify disk is mounted at `/opt/render/cache`
- Check file permissions in logs

### Cron job not running
- Verify schedule syntax in Render dashboard
- Check Background Worker logs

## Next Steps
1. Commit `render.yaml` to git
2. Push to GitHub
3. Go to Render.com → click "New Blueprint"
4. Select your repo → Deploy
5. Share frontend URL with team
