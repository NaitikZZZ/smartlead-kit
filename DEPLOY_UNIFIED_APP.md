# Deploying Unified ABM App (Steps 1-10)

> Single Streamlit app with full workflow: Score → Find → Enrich → Verify → Segment → Copy → Deploy → Export → **Copy Agent → HubSpot**

---

## Architecture

**One unified Streamlit app** with 10 pages:
- Home: `app.py` (ABM 2026 Live dashboard)
- Pages 1-4: Channel analytics, sender efficiency, pipeline, mappings
- **Page 10: Copy Agent** (NEW - post-enrichment copy generation)

**Deployment options:**
1. **Streamlit Community Cloud** (free, 3 apps limit)
2. **Render** (paid, production-grade)
3. **Local dev** (for testing)

---

## Option 1: Streamlit Community Cloud (Fastest)

### Requirements
- GitHub repo (you already have it)
- Streamlit account
- Environment secrets

### Steps

1. **Push to GitHub**
   ```bash
   cd smartlead-kit/dashboard
   git push origin main
   ```

2. **Create app on Streamlit Cloud**
   - Go to https://share.streamlit.io/
   - Click "New app"
   - GitHub repo: `NaitikZZZ/nac_outbound_kit`
   - Branch: `main`
   - Path: `smartlead-kit/dashboard/app.py`
   - Click "Deploy"

3. **Add secrets**
   - After deploy, click app menu → Settings
   - Go to "Secrets"
   - Add your secrets:
     ```
     ANTHROPIC_API_KEY = "sk-ant-..."
     SMARTLEAD_API_KEY = "..."
     HEYREACH_API_KEY = "..."
     HUBSPOT_API_KEY = "..."
     ```

4. **Live!**
   - App available at: `https://[app-name].streamlit.app`
   - Share link with team
   - All 10 pages (including Step 10: Copy Agent) are live

---

## Option 2: Render (Production)

### Requirements
- Render account
- GitHub repo with `dashboard/` folder tracked
- Environment secrets

### Steps

1. **Create Web Service**
   - Go to https://render.com/dashboard
   - New → Web Service
   - GitHub repo: connect repo
   - Root directory: `smartlead-kit/dashboard`
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run app.py --server.port=10000 --server.address=0.0.0.0`

2. **Environment Variables**
   Add in Render dashboard → Environment:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   SMARTLEAD_API_KEY=...
   HEYREACH_API_KEY=...
   HUBSPOT_API_KEY=...
   APP_PASSWORD=yourpassword
   ```

3. **Deploy**
   - Click "Create Web Service"
   - Render auto-deploys on git push
   - App available at: `https://[service-name].onrender.com`

---

## Option 3: Local Development

### Prerequisites
```bash
# Install Python 3.9+
python --version

# Navigate to dashboard
cd smartlead-kit/dashboard

# Create virtual env (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create `.env` file**
   ```bash
   cp .env.example .env
   # Edit .env with your keys
   nano .env
   ```

   Required keys:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   Optional overrides:
   ```
   SMARTLEAD_API_KEY=...
   HEYREACH_API_KEY=...
   HUBSPOT_API_KEY=...
   APP_PASSWORD=yourpassword  # For weekly auth gate
   ```

3. **Run**
   ```bash
   streamlit run app.py
   ```

   Opens at: `http://localhost:8501`

4. **Test Step 10**
   - Click "Step 10: Copy Agent" in sidebar
   - Upload sample CSV
   - Try segmentation, copy generation, export

---

## Step 10 Features

The new Copy Agent page provides:

### 1. Upload (Step 1)
- Drag-drop CSV/Excel upload
- Auto-column detection
- Live preview (first 5 rows)
- Metadata: lead count, column names

### 2. Segmentation (Step 2)
- Claude auto-segments into 4 buckets
- Warm re-engagement 🔥
- Cold intro ❄️
- Multi-product 🎯
- Event-specific 🎪

### 3. Copy Generation (Step 3)
- 5-step email sequences with A/B variants
- LinkedIn cadence (5 steps)
- Edit inline (full WYSIWYG)
- Smartlead merge tags: `{{first_name}}`, `{{company_name}}`, etc.

### 4. Campaign Setup (Step 4)
- Smartlead campaign config (timezone, schedule, daily limits)
- HeyReach LinkedIn list config
- Creates campaigns PAUSED (safe for review)
- Shows campaign IDs

### 5. Export (Step 5)
- HubSpot-ready CSV
- Includes campaign IDs, segment assignments, enrichment data
- Optional: create HubSpot list on import
- Download button (CSV)

---

## Workflow Options

### Sequential (Default)
- Steps 1-5 in order
- Upload → Segment → Copy → Setup → Export
- Button at each step to advance

### Jump Directly to Step 10
- Users with already-enriched data skip Steps 1-9
- Sidebar radio button: pick any step
- Useful for re-running copy generation on same data

---

## Architecture: App Structure

```
smartlead-kit/
├── dashboard/
│   ├── app.py                 ← Home page (ABM Live Dashboard)
│   ├── pages/
│   │   ├── 1_Channel_Comparison.py
│   │   ├── 2_Sender_Efficiency.py
│   │   ├── 3_Pipeline.py
│   │   ├── 4_Mappings.py
│   │   └── 10_Copy_Agent.py   ← NEW: Post-enrichment workflow
│   ├── lib/
│   │   ├── config.py          (API key loading, mappings)
│   │   ├── disk_cache.py      (Offline snapshot caching)
│   │   └── metrics.py         (Analytics helpers)
│   ├── config/
│   │   └── mappings.yaml      (Campaign naming vocabularies)
│   ├── requirements.txt        (Dependencies + anthropic)
│   └── README.md              (Streamlit-specific docs)
```

---

## Troubleshooting

### App won't start
```bash
# Check Python version
python --version  # Should be 3.9+

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check .env file exists and has valid keys
cat .env
```

### "API key missing" error
- Ensure `.env` file exists in `smartlead-kit/dashboard/` directory
- Key format: `ANTHROPIC_API_KEY=sk-ant-...` (no quotes)
- No spaces: `KEY=value` not `KEY = value`

### Slow segmentation / copy generation
- Claude API calls take 30-60 seconds
- Check console for progress (should show "Analyzing leads...", "Generating sequences...")
- First run is slower due to API latency; subsequent runs use cache

### Streamlit Cloud deployment issues
- Ensure `smartlead-kit/dashboard/` is tracked in git (not in `.gitignore`)
- Check `.gitignore` - only ignore `.env`, `outputs/`, `__pycache__/`
- Verify all imports in `10_Copy_Agent.py` are in `requirements.txt`

---

## Security

### Secrets Management

**Never commit `.env` to git:**
```bash
# .env is already in .gitignore
cat smartlead-kit/dashboard/.gitignore
# Should show: .env
```

**Render / Streamlit Cloud:**
- Secrets stored in platform UI, not in code
- Environment variables injected at runtime
- Safe for team collaboration

**Local development:**
- `.env` file is local-only
- Each team member has their own `.env` with their Claude key

---

## Team Usage

### For Streamlit Cloud:
```
1. Get app link: https://[app-name].streamlit.app
2. Open in browser
3. Go to "Step 10: Copy Agent"
4. Upload CSV → Auto-segment → Edit copy → Download export
```

### For Render:
```
1. Get app URL: https://[service-name].onrender.com
2. Enter weekly password (from APP_PASSWORD secret)
3. Same workflow as above
```

### No installation needed!
- Team members don't need Python, pip, or `.env`
- Works in any browser
- All processing on server

---

## Next Steps

1. **Choose deployment platform** (Streamlit Cloud = fastest, Render = most control)
2. **Deploy** (follows steps above)
3. **Test** (try Step 10 with sample CSV)
4. **Share link** with team
5. **Monitor** (check analytics in Streamlit dashboard)

---

## Questions?

Contact: naitik.chavda@xoxoday.com
