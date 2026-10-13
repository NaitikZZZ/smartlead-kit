from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class InputSourceType(str, Enum):
    csv = "csv"
    hubspot_project = "hubspot_project"
    # hubspot_form_link intentionally removed for now - re-add when ready,
    # the fetch logic still lives in pipeline/input_sources.py.


class RunStage(str, Enum):
    queued = "queued"
    reading_input = "reading_input"
    normalizing = "normalizing"
    normalized_stopped = "normalized_stopped"
    checking_completeness = "checking_completeness"
    resolving_domains = "resolving_domains"
    checking_exclusions = "checking_exclusions"
    enriching = "enriching"
    assembling_outputs = "assembling_outputs"
    opening_pr = "opening_pr"
    awaiting_answer = "awaiting_answer"
    awaiting_import_confirmation = "awaiting_import_confirmation"
    importing_to_hubspot = "importing_to_hubspot"
    done = "done"
    failed = "failed"


class StartRunRequest(BaseModel):
    input_source: InputSourceType
    hubspot_project_id: Optional[str] = None
    company_col: Optional[str] = None
    domain_col: Optional[str] = None
    employee_col: Optional[str] = None


class PendingQuestion(BaseModel):
    key: str  # which checkpoint this is, e.g. "exclusion_needed", "association_type"
    type: str  # "yes_no" | "text" | "choice" | "association_details"
    prompt: str
    options: Optional[list[str]] = None
    default: Optional[str] = None
    context: dict = {}  # extra data the frontend might want to render (e.g. suggested name)


class AnswerRequest(BaseModel):
    key: str
    value: Any


class ImportConfirmRequest(BaseModel):
    confirm: bool


class CopyPushChannel(str, Enum):
    smartlead = "smartlead"
    heyreach = "heyreach"
    interakt = "interakt"


class CopyPushStage(str, Enum):
    queued = "queued"
    mapping = "mapping"
    awaiting_review = "awaiting_review"
    pushing = "pushing"
    done = "done"
    failed = "failed"


class CopyPushStartRequest(BaseModel):
    channels: list[CopyPushChannel]
    campaign_name: str
    copy_text: Optional[str] = None  # pasted copy; omit when sending a file instead (multipart, handled separately)
    source_run_id: Optional[str] = None  # chains onto a completed Flow 1 run: reuses its HeyReach list_id + campaign title context
    is_cxo: bool = False  # HeyReach only - recorded as a note; the open-profile draft branch isn't built (unvalidated, see heyreach.build_sequence)
    region: Optional[str] = None  # drives the Interakt region warning (IND/PHL/IDN are standing-rule-eligible for WhatsApp)


class CopyPushConfirmRequest(BaseModel):
    confirm: bool
    edited_mapping: Optional[dict[str, dict]] = None  # per-channel corrections to the mapped copy before push
    heyreach_sender_ids: Optional[list[int]] = None
    smartlead_sender_tag_id: Optional[int] = None  # mailbox group - takes precedence over smartlead_sender_account_ids
    smartlead_sender_account_ids: Optional[list[int]] = None


class CopyPushStatus(BaseModel):
    push_id: str
    stage: CopyPushStage
    message: str = ""
    error: Optional[str] = None
    channels: list[str] = []
    warnings: list[str] = []
    mapped: dict = {}
    result: dict = {}


class RunStatus(BaseModel):
    run_id: str
    stage: RunStage
    message: str = ""
    error: Optional[str] = None
    stats: dict = {}
    output_files: list[str] = []
    pr_url: Optional[str] = None
    hubspot_list_url: Optional[str] = None
    pending_question: Optional[PendingQuestion] = None
