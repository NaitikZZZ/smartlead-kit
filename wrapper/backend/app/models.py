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
