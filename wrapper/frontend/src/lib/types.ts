export type InputSourceType = "csv" | "hubspot_project" | "campaign_idea";
// hubspot_form_link intentionally removed for now - will come back later.

export type RunStage =
  | "queued"
  | "reading_input"
  | "normalizing"
  | "checking_completeness"
  | "resolving_domains"
  | "checking_exclusions"
  | "enriching"
  | "assembling_outputs"
  | "opening_pr"
  | "awaiting_answer"
  | "awaiting_import_confirmation"
  | "importing_to_hubspot"
  | "done"
  | "failed";

export const STAGE_ORDER: RunStage[] = [
  "queued",
  "reading_input",
  "normalizing",
  "checking_completeness",
  "checking_exclusions",
  "resolving_domains",
  "enriching",
  "assembling_outputs",
  "opening_pr",
  "awaiting_answer",
  "awaiting_import_confirmation",
  "importing_to_hubspot",
  "done",
];

export const STAGE_LABELS: Record<RunStage, string> = {
  queued: "Queued",
  reading_input: "Reading input",
  normalizing: "Normalizing names & companies",
  checking_completeness: "Checking sheet completeness",
  resolving_domains: "Resolving domains",
  checking_exclusions: "Checking exclusions",
  enriching: "Enriching via Apollo",
  assembling_outputs: "Assembling output files",
  opening_pr: "Opening PR",
  awaiting_answer: "Waiting on your input",
  awaiting_import_confirmation: "Ready for review",
  importing_to_hubspot: "Importing to HubSpot",
  done: "Done",
  failed: "Failed",
};

export interface PendingQuestion {
  key: string;
  type: "yes_no" | "text" | "choice" | "multi_choice" | string;
  prompt: string;
  options?: string[] | null;
  default?: string | null;
  context: Record<string, any>;
}

export type StepStatus = "pending" | "running" | "done" | "skipped";

export interface CostBlock {
  operation: string;
  units: number;
  credits: number;
  usd: number;
  cost_per_credit: number;
}

export interface CostInfo {
  credits: number;
  usd: number;
  breakdown: CostBlock[];
}

export interface StepInfo {
  key: string;
  title: string;
  status: StepStatus;
  summary?: string | null;
  time?: string | null;
  cost?: CostBlock | null;
}

// Canonical left-sidebar steps, kept in sync with runner.STEP_DEFS on the
// backend. Rendered even before a run starts so the whole flow is visible.
export const STEPS: { key: string; title: string; hint: string }[] = [
  { key: "source", title: "Input & Normalization", hint: "Read the list, clean names & companies" },
  { key: "domain", title: "Domain Resolution", hint: "Fill missing company domains" },
  { key: "exclusion", title: "Exclusion Check", hint: "Remove existing clients" },
  { key: "discovery", title: "People Discovery", hint: "Find decision-makers (if no contacts)" },
  { key: "reveal", title: "Email Reveal & Validation", hint: "Unlock & verify work emails" },
  { key: "phone", title: "Mobile Phone", hint: "Reveal direct/mobile numbers" },
  { key: "outputs", title: "Output Files & Name", hint: "3 channel files + campaign name" },
  { key: "associations", title: "Associations", hint: "Project / Partner / Event + list" },
  { key: "upload", title: "Preview & Upload", hint: "Review, then push to HubSpot" },
  { key: "copy_agent", title: "Copy Agent", hint: "Generate email & LinkedIn copy" },
];

export interface RunStatus {
  run_id: string;
  stage: RunStage;
  message: string;
  error?: string | null;
  stats: Record<string, any>;
  output_files: string[];
  pr_url?: string | null;
  hubspot_list_url?: string | null;
  pending_question?: PendingQuestion | null;
}

export interface AppConfig {
  account_mapping_sheet_configured: boolean;
  account_mapping_sheet_file?: string | null;
  github_pr_enabled: boolean;
  apollo_configured: boolean;
  hubspot_read_configured: boolean;
  hubspot_write_configured: boolean;
  exclusion_list_name?: string;
  exclusion_list_id?: string;
  exclusion_list_url?: string;
}

// Reference data for the campaign-idea wizard - fetched once before any run
// starts, so use-case/region/employee-size choices are real, not guessed.
export interface IcpOptions {
  use_cases: Record<string, string[]>; // product/sheet name -> its use cases
  regions: string[];
  countries: string[];
  employee_size_buckets: string[];
}

// What the campaign-idea wizard sends when the user has confirmed their own
// targeting - the backend skips Claude extraction and icp_confirm_form
// entirely when this is present (see inngest_runner._targeting_from_wizard).
export interface WizardTargeting {
  product?: string;
  use_case?: string;
  job_titles: string[];
  employee_sizes: string[];
  regions: string[];
  company_names?: string[];
}
