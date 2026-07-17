import type { AppConfig, RunStatus } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8731";

export async function getConfig(): Promise<AppConfig> {
  const r = await fetch(`${API_BASE}/api/config`);
  if (!r.ok) throw new Error("Failed to load server config");
  return r.json();
}

export interface StartRunParams {
  inputSource: "csv" | "hubspot_project";
  csvFile?: File;
  hubspotProjectId?: string;
  mappingSheetFile?: File;
  companyCol?: string;
  domainCol?: string;
  employeeCol?: string;
}

export async function startRun(params: StartRunParams): Promise<RunStatus> {
  const fd = new FormData();
  fd.append("input_source", params.inputSource);
  if (params.hubspotProjectId) fd.append("hubspot_project_id", params.hubspotProjectId);
  if (params.companyCol) fd.append("company_col", params.companyCol);
  if (params.domainCol) fd.append("domain_col", params.domainCol);
  if (params.employeeCol) fd.append("employee_col", params.employeeCol);
  if (params.csvFile) fd.append("csv_file", params.csvFile);
  if (params.mappingSheetFile) fd.append("mapping_sheet_file", params.mappingSheetFile);

  const r = await fetch(`${API_BASE}/api/runs`, { method: "POST", body: fd });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to start run (${r.status})`);
  }
  return r.json();
}

export async function getRun(runId: string): Promise<RunStatus> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}`);
  if (!r.ok) throw new Error("Failed to fetch run status");
  return r.json();
}

export async function answerQuestion(runId: string, key: string, value: any): Promise<RunStatus> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to submit answer (${r.status})`);
  }
  return r.json();
}

export function fileUrl(runId: string, filename: string): string {
  return `${API_BASE}/api/runs/${runId}/files/${filename}`;
}

export async function confirmImport(runId: string) {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Import failed (${r.status})`);
  }
  return r.json();
}
