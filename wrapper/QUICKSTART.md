# ABM Wrapper - Quick Start (5 min)

## 🚀 For Team Members (Use the Tool)

The wrapper is already running at: **[deployed URL here]**

1. **Open the tool** in your browser
2. **Pick your input**: CSV upload or HubSpot Project
3. **Upload your prospects** (Company Name required, Domain/Industry/Employee Count optional)
4. **Walk through the steps**: Answer a few yes/no questions
5. **Review the 3 output files** (email for HubSpot, LinkedIn for HeyReach, calling for dialers)
6. **Confirm to upload** to HubSpot

That's it. Takes 5-10 min per run (depending on list size).

### How to Prepare Your CSV

Minimum columns:
- `Company Name`

Optional (improves results, saves Apollo credits):
- `Domain`
- `# Employees`
- `Industry`

The tool will fill in missing domains and industries via Claude + web search (if `ANTHROPIC_API_KEY` is set).

### Output Files

After running, you get 3 CSVs:
- **email_upload.csv** → HubSpot import (verified email only)
- **linkedin_upload.csv** → HeyReach import (LinkedIn URLs)
- **calling_upload.csv** → Dialer (phone + name)

## 🛠️ For Developers (Deploy & Run Locally)

### Prerequisites
- Python 3.10+, Node.js 18+, npm

### Local Setup (10 min)

```bash
# Clone and enter the repo
cd smartlead-kit

# Backend
cd wrapper/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Add your secrets to .env (see SETUP.md for details)
# ANTHROPIC_API_KEY, HUBSPOT_PRIVATE_APP_KEY, etc.

# Start backend
uvicorn app.main:app --reload --port 8731

# In a new terminal: Frontend
cd wrapper/frontend
npm install
npm run dev
```

**Frontend**: http://localhost:5173  
**Backend**: http://localhost:8731

### Deploy to Render (5 min setup, auto-deploys after)

1. Create a new Render account (or use your org's)
2. Connect your GitHub repo
3. Render auto-deploys both services from `render.yaml`
4. Set secrets in Render's dashboard (ANTHROPIC_API_KEY, HUBSPOT_PRIVATE_APP_KEY, etc.)
5. Redeploy to pick up the secrets
6. Share the frontend URL with the team

See [SETUP.md](./SETUP.md) for detailed deployment + config.

### Useful Commands

```bash
# Backend: health check
curl http://localhost:8731/health

# Backend: refresh HubSpot exclusion cache
cd wrapper/backend && ./.venv/bin/python -m app.pipeline.hubspot_exclusion

# Frontend: build for production
cd wrapper/frontend && npm run build
```

## 📊 Cost Tracking

The tool shows estimated Apollo credit cost **before** you run enrichment. Only uncached lookups are charged:
- Domain resolve: ~1 credit per company
- Email reveal: ~1 credit per email
- Phone reveal: **~8 credits** per phone (expensive, but cached)

With a 50-person list and no cache: expect ~$5-20 depending on domains + phones requested.

The cost breakdown appears on the step card — you can decide to skip phone enrichment if you want to save credits.

## 🤔 Common Workflows

### Scenario: "I have a 'Top 100 VCs' article I want to extract"

1. Paste the URL into the tool (select "URL Scrape" when that step appears)
2. Tool uses Claude to auto-extract the list into structured JSON
3. Review the extracted data, fix any errors
4. Continue with enrichment

### Scenario: "I want to exclude leads from competitors + previous campaigns"

1. Upload your CSV
2. When asked "Exclude against Account Mapping Sheet?", say **Yes**
3. Upload your exclusion sheet (or the tool pulls HubSpot list 28280 by default)
4. Tool checks every domain against the exclusion set
5. Excluded rows are flagged and removed

### Scenario: "I want to associate all leads to a HubSpot Project"

1. After enrichment, when asked "Associate with Project / Partner / Event?", select **Project**
2. Paste the project name or HubSpot URL
3. Tool auto-links all imported contacts to that project

## 🐛 Need Help?

- **Activity log**: Look at the timestamps in the UI — they show exactly what's happening
- **Secrets missing**: Check if `ANTHROPIC_API_KEY` or `HUBSPOT_PRIVATE_APP_KEY` are set (features degrade gracefully if missing)
- **Stuck on a step**: Refresh the page — the run is still happening in the background
- **Slack**: @naitik for any blockers

## Next: Read Full Setup

For deploying to production, managing secrets, scheduling cron jobs, and troubleshooting, see [SETUP.md](./SETUP.md).
