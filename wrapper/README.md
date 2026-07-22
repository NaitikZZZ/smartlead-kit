# ABM Enrichment Wrapper

A hosted web tool that wraps the ABM outbound pipeline (completeness ->
exclusion -> normalization -> Apollo enrichment -> HubSpot import) as an
interactive, question-driven flow, so the whole team can run it without
touching scripts directly.

## v2 UI (SaaS sidebar)

The frontend is a left-sidebar guided wizard with 9 fixed steps, each showing
a live status, a one-line summary, and (for Apollo steps) the credit/$ cost:

1. Input & Normalization (mandatory, automatic)
2. Domain Resolution (gated - shows estimated Apollo credits/$ before running)
3. Exclusion Check (gated - Account Mapping Sheet)
4. People Discovery (gated - auto-skipped if the sheet already has contacts)
5. Email Reveal & Validation
6. Mobile Phone (gated - shows estimated cost)
7. Output Files & Name - writes THREE channel files:
   `email_upload.csv` (HubSpot, verified email only, never blank),
   `linkedin_upload.csv` (HeyReach import), `calling_upload.csv` (dialer)
8. Associations (multi-select: any of Project / Partner / Event; a static
   HubSpot list is always created too)
9. Preview & Upload - review the 3 files + a live email preview, then confirm
   to write to HubSpot. Nothing is written without that confirmation.

Cost basis for the estimates: the team's Apollo contract ($13,566 / 720,000
credits ≈ $0.0188/credit), centralised in `backend/app/pipeline/estimates.py`.

**Exclusion source:** mandatorily the HubSpot **"ABM EXCLSIONS - DNU"** contacts
list (id `28280`) - the members' email domains are the do-not-use set
(`backend/app/pipeline/hubspot_exclusion.py`). The list is ~120k contacts, so
its domain set is pulled once and cached on disk
(`backend/cache/exclusion_domains_28280.json`), then matched by exact/sub/parent
domain. Refresh the cache on a schedule (daily) so it stays current:

```bash
cd wrapper/backend && ./.venv/bin/python -m app.pipeline.hubspot_exclusion
```

If a run hits a missing/stale cache it rebuilds inline (one-time ~10-15 min),
so keep the scheduled refresh running to keep runs instant.

**Caching & Apollo cost model:** every paid lookup is cached to disk so a
re-run never re-pays Apollo for the same person/company:
- Domain → `reference/company_domain_cache.csv` (~1 credit uncached)
- Email match → `cache/email_reveal_cache.json` (~1 credit uncached)
- Full person reveal → `cache/person_enrich_cache.json` (~1 credit uncached)
- Phone reveal → `reference/phone_reveal_cache.csv` (**~8 credits** uncached; even
  "no phone on file" is cached)

Cost basis $13,566 / 720,000 credits. The cost prompts and the review screen
show a **per-operation breakdown** (Domain / Email / Phone-calling / Total) and
count only the **uncached** lookups (what will actually be charged).

**Job changes:** rows flagged in a "Job change" / "Started role last N months"
column bypass the email/phone cache and are force-refreshed (old work data is
stale). Everyone else stays cache-free.

**HeyReach push:** on the confirm-upload step, the LinkedIn file is pushed to a
new HeyReach lead list named after the campaign (`POST /list/CreateEmptyList`
then `POST /list/AddLeadsToListV2`, batched at 100), alongside the HubSpot import
+ list. Needs `HEYREACH_API_KEY` (already in the shared `smartlead-kit/.env`).
Best-effort: a HeyReach failure is reported but never sinks the HubSpot import.

Built as: **React frontend** + **Python/FastAPI backend** (wraps the
existing, tested scripts in `smartlead-kit/scripts/` and the vendored
`abm-exclusion-check` / `name-company-normalizer` skill logic - no
reimplementation). Apollo-only enrichment for now (Lusha is still being
evaluated, see project memory).

## How a run works

The backend pauses at each checkpoint below and waits for an answer from the
frontend (a simple yes/no, free-text, or multiple-choice question) before
continuing - it's not a fire-and-forget pipeline.

1. Pick one of 2 input sources: CSV/data-sheet upload, or a HubSpot Project
   (ABM Campaigns pipeline record - pulls ICP/region/employee-size/campaign
   concept for context, but the account rows still come from an uploaded CSV
   since linked SharePoint/Drive files usually sit behind auth). Form-link
   input is temporarily disabled (the fetch logic still lives in
   `pipeline/input_sources.py` for when it comes back).
2. **Normalization** runs automatically (mandatory, no question).
3. **Completeness check**: fills gaps in whatever Domain/Industry/Employee
   columns already exist, via an LLM with web search (`ANTHROPIC_API_KEY`,
   per-instance - each person running this backend uses their own key).
   Skipped silently if that key isn't configured, or if nothing's missing.
   (Keyless web search was evaluated and doesn't work reliably - DuckDuckGo
   scraping hits an immediate bot-challenge wall, and their no-key
   Instant-Answer API has no useful coverage for company lookups.)
4. **Ask: exclusion needed?** If yes, checks against the Account Mapping
   Sheet (upload one at run start, or configure `ACCOUNT_MAPPING_SHEET_PATH`
   once for the whole instance - only used if this question is answered yes).
5. **Ask: enrichment needed?** If yes: resolves domains, runs a second
   completeness pass specifically for rows Apollo still can't place, asks how
   many contacts per company (ideal 5-7, hard cap 10) and which persona/ICP
   titles to target (defaults to the HR/People-leader list, or the Project's
   own ICP field), then runs the Apollo search -> reveal email -> reveal phone
   sequence.
6. **Ask: what should this run be called?** Suggests a campaign_title per
   `docs/campaign-naming-convention.md` (best-effort - always editable).
7. Three output files get written and, if `GITHUB_TOKEN`/`GITHUB_REPO` are
   set, committed to a new branch with a PR opened automatically. If PR
   creation fails or isn't configured, the UI shows the fallback instruction
   ("merge it yourself, or email naitik.chavda@xoxoday.com") rather than
   sending anything automatically.
8. **Ask: associate with a Partner, Project, Event, or none?** Accepts a
   name, a pasted HubSpot URL, or a raw record ID for partner/project/event -
   resolves it via search, and asks you to disambiguate if multiple records
   match. "None" creates a plain static HubSpot list instead and shows its URL.
9. Review the stats/files, then explicitly confirm to write the
   verified-email contacts into HubSpot. Nothing is written without that
   confirmation.

## Local development

```bash
# Backend
cd wrapper/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in secrets, or rely on the shared smartlead-kit/.env
uvicorn app.main:app --reload --port 8731

# Frontend (separate terminal)
cd wrapper/frontend
npm install
npm run dev   # http://localhost:5173, talks to http://localhost:8731 by default
```

## Deployment

`render.yaml` defines both services (Python backend + static frontend
build). Set the backend's secrets in Render's dashboard (never commit them),
and set the frontend's `VITE_API_BASE` to the deployed backend URL.

## Known limits (v1)

- In-memory job store, pause/resume via a blocked background thread per run -
  single instance only, a restart loses in-flight run state (finished output
  files on disk survive). Fine for a small internal team, not built to scale
  to heavy concurrent load.
- File uploads (target CSV, Account Mapping Sheet) only happen at run
  creation time, not mid-flow - if exclusion turns out to be needed but no
  sheet was attached, the run fails with a clear message to restart with one.
- No auth on the API itself - put it behind your org's SSO/VPN before wider
  rollout.
- HubSpot Project input source still requires a manually-downloaded CSV of
  the linked target list (can't fetch SharePoint/Drive files behind login).
- Event association type ID isn't pre-confirmed against the live portal like
  Partner/Project are (looked up dynamically at request time instead).
