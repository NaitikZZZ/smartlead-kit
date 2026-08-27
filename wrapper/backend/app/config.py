"""Central config/env loading for the ABM wrapper backend.

Loads secrets from a .env file. Never log or return these values in API
responses - only use them internally when calling Apollo/HubSpot/GitHub.
"""
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

# Exclusion source: When the user chooses to run exclusion checks, they MUST use the
# HubSpot "ABM EXCLSIONS - DNU" contacts list (28280).
# Portal: https://app-na2.hubspot.com/contacts/6512810/objectLists/28280/filters
#
# This list contains ~120k existing clients. When exclusion is enabled, it's mandatory.
# Do NOT change this ID without explicit authorization.
# Its members' email domains/names/LinkedIn URLs are the do-not-use set. The list is huge (~120k),
# so its data set is cached on disk and refreshed live every run - see pipeline/hubspot_exclusion.py.
#
# See EXCLUSION_LIST_MANDATORY.md for full documentation.
HUBSPOT_EXCLUSION_LIST_ID = os.environ.get("HUBSPOT_EXCLUSION_LIST_ID", "28280")
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


def exclusion_list_url() -> str:
    """Direct link to the HubSpot DNU exclusion list's filters view."""
    return (
        f"https://{HUBSPOT_APP_SUBDOMAIN}/contacts/{HUBSPOT_PORTAL_ID}"
        f"/objectLists/{HUBSPOT_EXCLUSION_LIST_ID}/filters"
    )
