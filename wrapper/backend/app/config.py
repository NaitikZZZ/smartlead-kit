"""Central config/env loading for the ABM wrapper backend.

Loads secrets from a .env file. Never log or return these values in API
responses - only use them internally when calling Apollo/HubSpot/GitHub.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
SMARTLEAD_KIT_DIR = BACKEND_DIR.parent.parent  # .../smartlead-kit
SCRIPTS_DIR = SMARTLEAD_KIT_DIR / "scripts"
REFERENCE_DIR = SMARTLEAD_KIT_DIR / "reference"
# outputs.write_file() always writes locally first (still needed same-request,
# e.g. github_pr.py reads these paths directly) even when Vercel Blob is also
# configured - everywhere outside /tmp is read-only on Vercel, so this must
# resolve to /tmp there. VERCEL=1 is set automatically on every Vercel deploy.
RUNS_DIR = (Path("/tmp") / "runs") if os.environ.get("VERCEL") else (BACKEND_DIR / "runs")

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(SMARTLEAD_KIT_DIR / ".env", override=False)  # fall back to shared kit .env

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
HUBSPOT_READ_TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "")
HUBSPOT_WRITE_TOKEN = os.environ.get("HUBSPOT_WRITE_TOKEN", "")
HEYREACH_API_KEY = os.environ.get("HEYREACH_API_KEY", "")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY", "")

# Upstash Redis (REST API) - replaces the local file-based caches below so
# they survive across serverless invocations (Vercel's filesystem is
# ephemeral/read-only outside /tmp). See app/redis_cache.py.
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# Vercel Blob - replaces local per-run output file storage (config.RUNS_DIR)
# for the same reason. See app/vercel_blob.py.
BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")

# Vercel sends this as `Authorization: Bearer {CRON_SECRET}` on every Cron Job
# invocation - app/routes/cron.py checks it matches before doing real work,
# rejecting the request (even locally) if this isn't set, so a public request
# to a cron route can never trigger a rebuild by accident.
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Inngest - durable workflow engine replacing the in-memory JOBS dict +
# blocked-thread ask/answer mechanism in runner.py (see app/inngest_client.py).
INNGEST_EVENT_KEY = os.environ.get("INNGEST_EVENT_KEY", "")
INNGEST_SIGNING_KEY = os.environ.get("INNGEST_SIGNING_KEY", "")

# Exclusion sources: two dynamic HubSpot lists, checked with different match
# rules because they represent different things (confirmed 2026-09-01):
#   - PROSPECT list: Meeting Completed (SDR/AE) / Lifecycle DNC / Lead Status
#     DNC. These are signals about ONE PERSON, not their employer - one
#     contact completing a meeting must not block outreach to their
#     colleagues. Matched narrowly: exact email address or exact LinkedIn
#     URL only.
#   - COMPANY list: Parent Company Type (Farming/Churned) / active deal
#     stages. These are account-level signals, so matched broadly on company
#     domain/name to protect the whole account.
# See pipeline/hubspot_exclusion.py for the matching logic.
# Do NOT change these IDs without explicit authorization.
HUBSPOT_EXCLUSION_LIST_ID_PROSPECT = os.environ.get("HUBSPOT_EXCLUSION_LIST_ID_PROSPECT", "29147")
# Built 2026-09-10: "ABM EXCLSIONS Company Level (Deal Stage & Parent Company
# Type) - DNU", a dynamic Contacts list (objectTypeId 0-1), confirmed via a
# read-only GET against crm/v3/lists/29338. run_exclusion_check() skips
# company-level matching entirely if this is ever unset again, rather than
# erroring.
HUBSPOT_EXCLUSION_LIST_ID_COMPANY = os.environ.get("HUBSPOT_EXCLUSION_LIST_ID_COMPANY", "29338")
# Cache TTL: keeps local copy fresh within 24h. Daily cron at 2 AM rebuilds it
# during off-hours, so daytime runs use cached version (instant).
EXCLUSION_CACHE_TTL_HOURS = int(os.environ.get("EXCLUSION_CACHE_TTL_HOURS", "24"))
# Association dropdowns (Project/Partner/Event) are cached from HubSpot and
# kept fresh by crons (projects/events every 30 min, partners daily 6am). This
# TTL is only the inline-refresh fallback for when a cron was missed (machine
# asleep) - 24h so normal runs always serve the cron-maintained cache.
ASSOC_CACHE_TTL_HOURS = int(os.environ.get("ASSOC_CACHE_TTL_HOURS", "24"))
CACHE_DIR = BACKEND_DIR / "cache"
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # read-only filesystem (Vercel) - fine, every cache under here is Redis-backed when configured

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # "owner/repo"
GITHUB_BASE_BRANCH = os.environ.get("GITHUB_BASE_BRANCH", "main")

# LLM-with-web-search backend for the completeness step (fills missing
# domain/industry/employee-size when Apollo can't resolve them). Best-effort -
# the completeness step is skipped entirely if this isn't set. Per-instance
# config - each person running this backend uses their own key.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Cost-control kill switch (2026-09-10, user request: Apollo credit spend was
# running high). When False, every paid Apollo/Claude enrichment call site
# skips itself and falls through to free-tier-only behavior:
#   - domain_resolution: stops after HubSpot/Clearbit/Brandfetch/Wikidata,
#     never calls Apollo org search (gated in scripts/resolve_company_domains.py
#     itself via its own PAID_ENRICHMENT_ENABLED env read - same var name).
#   - web_completeness: Claude web-search gap-fill is skipped entirely.
#   - apollo_enrich.enrich_candidates / enrich_existing_contacts / the paid
#     tier of fill_missing_details: skipped (free bulk_match-by-email tier
#     still runs, since Apollo's own docs say that one is zero-credit).
#   - apollo_enrich.enrich_phones (phone reveal): as of 2026-09-21, also
#     skipped - cache hits still serve for free, uncached contacts get a
#     "paid enrichment disabled" note instead of a live reveal. This reverses
#     the 2026-08-10 decision below to deliberately keep phone/email reveal
#     running; the user is out of Apollo credits and wants every paid call
#     paused until they explicitly ask to resume ("use apollo").
# Apollo people search itself (search_candidates/search_candidates_by_icp) is
# NOT gated - it isn't credit-metered in this kit's usage, only the reveal
# calls are, so free search keeps running.
# Re-enable by setting PAID_ENRICHMENT_ENABLED=true (or removing it) in .env
# - or just tell Claude Code "use apollo" and it will flip this back.
PAID_ENRICHMENT_ENABLED = os.environ.get("PAID_ENRICHMENT_ENABLED", "true").strip().lower() not in ("false", "0", "no")

# GTM narrative account-profile research (value proposition, named partners,
# workforce composition, product-to-pitch, etc - see pipeline/gtm_narrative.py).
# An AWS Bedrock backend was built and live-tested here (2026-09-17) as a
# dedicated, scoped-only-to-this-feature paid tier, but Bedrock's InvokeModel
# rejects Anthropic's web_search tool outright (confirmed via a real 400 -
# see gtm_narrative.py's module docstring) - Bedrock doesn't proxy to
# Anthropic's server-side tool-execution backend. Reverted; this feature uses
# only the Claude Code CLI (free) and ANTHROPIC_API_KEY (paid) backends below.

# Runs automatically for every account processed (same trigger point as
# gtm_enrichment.enrich() just above it in runner.py) - separate from
# PAID_ENRICHMENT_ENABLED (a different, currently-off Apollo-paid-tier
# concern) since the user explicitly wants this step running by default.
GTM_NARRATIVE_ENRICHMENT_ENABLED = os.environ.get("GTM_NARRATIVE_ENRICHMENT_ENABLED", "true").strip().lower() not in ("false", "0", "no")
# If more than this many companies on one sheet aren't already cached, the
# run pauses and asks before spending a live Claude+web-search call on each
# one - same cost-conscious spirit as CLAUDE.md Critical Rule #5's 500-lead
# Apollo threshold, tuned lower since this call is heavier per unit. Adjust freely.
GTM_NARRATIVE_CONFIRM_THRESHOLD = int(os.environ.get("GTM_NARRATIVE_CONFIRM_THRESHOLD", "50"))

# Copy Agent (Claude-generated email + LinkedIn copy, the final pipeline step).
# Off by default (2026-09-18): the user found the "generate copy now?" prompt
# and the generation itself too slow to sit through on every run. When False,
# inngest_runner.py skips the question and the step outright instead of
# asking - the run ends at HubSpot import. Not deleted: re-enable per run by
# setting COPY_AGENT_ENABLED=true (or removing it) in .env once needed again.
COPY_AGENT_ENABLED = os.environ.get("COPY_AGENT_ENABLED", "false").strip().lower() not in ("false", "0", "no")

# Optional: a shared Account Mapping Sheet configured once for the whole
# hosted instance, so individual users don't need to upload it every run.
# ACCOUNT_MAPPING_SHEET_PATH pins one exact file (goes stale as new copies
# come in). ACCOUNT_MAPPING_SHEET_GLOB instead auto-picks the most recently
# modified file matching the pattern each time - the default matches the
# "Account Mapping Sheet 2026(Mapping) (N).csv" dated-copies convention this
# team already uses (see the reference_account_mapping_sheet memory), so a
# fresh weekly download just works without touching config.
ACCOUNT_MAPPING_SHEET_PATH = os.environ.get("ACCOUNT_MAPPING_SHEET_PATH", "")
ACCOUNT_MAPPING_SHEET_GLOB = os.environ.get(
    "ACCOUNT_MAPPING_SHEET_GLOB",
    str(Path.home() / "Downloads" / "Account Mapping Sheet 2026*.csv"),
)


def resolve_account_mapping_sheet_path() -> str:
    """Pinned path wins if set; otherwise picks the most recently modified
    file matching the glob. Returns '' if neither resolves to anything."""
    if ACCOUNT_MAPPING_SHEET_PATH:
        return ACCOUNT_MAPPING_SHEET_PATH
    import glob
    matches = glob.glob(ACCOUNT_MAPPING_SHEET_GLOB)
    if not matches:
        return ""
    return max(matches, key=lambda p: os.path.getmtime(p))

SCORING_CRITERIA_PATH = SMARTLEAD_KIT_DIR / "scoring-criteria.md"

# HubSpot object type IDs / association type IDs, confirmed live against the
# Xoxoday portal in this session. Association type IDs for Partner/Project are
# pinned (confirmed via the /associations/.../labels endpoint); Event's is
# looked up on demand in hubspot_import.py since we haven't confirmed it live.
HUBSPOT_PROJECT_OBJECT = "0-970"
HUBSPOT_PARTNER_OBJECT = "2-17592276"
HUBSPOT_EVENT_OBJECT = "2-229555311"
HUBSPOT_ABM_PIPELINE_ID = "2078458579"
ASSOC_CONTACT_TO_PARTNER = {"associationCategory": "USER_DEFINED", "associationTypeId": 130}
ASSOC_CONTACT_TO_PROJECT = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 1243}

# For constructing a direct HubSpot static-list URL to show the user.
HUBSPOT_PORTAL_ID = os.environ.get("HUBSPOT_PORTAL_ID", "6512810")
HUBSPOT_APP_SUBDOMAIN = os.environ.get("HUBSPOT_APP_SUBDOMAIN", "app-na2.hubspot.com")

MAX_CONTACTS_PER_COMPANY_DEFAULT = 7
MAX_CONTACTS_PER_COMPANY_CAP = 10

# (label shown to the user, Apollo "min,max" organization_num_employees_ranges
# value) - Apollo has no per-use-case employee-size data of its own (confirmed:
# not in reference/Use cases & ICP.xlsx), so this is the one canonical bucket
# list the campaign-idea wizard and icp_confirm_form both offer.
EMPLOYEE_SIZE_BUCKETS = [
    ("1-10", "1,10"), ("11-20", "11,20"), ("21-50", "21,50"), ("51-100", "51,100"),
    ("101-200", "101,200"), ("201-500", "201,500"), ("501-1000", "501,1000"),
    ("1001-5000", "1001,5000"), ("5001-10000", "5001,10000"), ("10000+", "10001,"),
]

try:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def require(name: str, value: str):
    if not value:
        raise RuntimeError(f"Missing required config: {name}. Set it in wrapper/backend/.env")
    return value


def exclusion_list_url(list_id: str | None = None) -> str:
    """Direct link to a HubSpot DNU exclusion list's filters view. Defaults to
    the prospect-level list."""
    lid = list_id or HUBSPOT_EXCLUSION_LIST_ID_PROSPECT
    return (
        f"https://{HUBSPOT_APP_SUBDOMAIN}/contacts/{HUBSPOT_PORTAL_ID}"
        f"/objectLists/{lid}/filters"
    )


def exclusion_reference_label() -> str:
    """Human-readable summary of which DNU list(s) are active, shown on the
    pre-exclusion confirmation prompt."""
    if HUBSPOT_EXCLUSION_LIST_ID_COMPANY:
        return "ABM EXCLSIONS - DNU (prospect-level + company-level lists)"
    return "ABM EXCLSIONS - DNU (prospect-level list only; company-level not yet configured)"
