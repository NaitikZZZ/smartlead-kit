import type { AppConfig, IcpOptions, RunStatus, WizardTargeting } from "./types";

// Falls back to same-origin ("") in a production build even if VITE_API_BASE
// was never configured in Vercel - relying on that env var alone meant a
// missing/misscoped dashboard setting silently baked "localhost:8731" into
// the production bundle (confirmed live: it kept hitting ERR_CONNECTION_REFUSED
// on localhost from real browsers). import.meta.env.PROD is set by Vite
// itself at build time, so this no longer depends on Vercel config at all.
const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://localhost:8731");

export async function getConfig(): Promise<AppConfig> {
  const r = await fetch(`${API_BASE}/api/config`);
  if (!r.ok) throw new Error("Failed to load server config");
  return r.json();
}

export async function getIcpOptions(): Promise<IcpOptions> {
  const r = await fetch(`${API_BASE}/api/runs/icp-options`);
  if (!r.ok) throw new Error("Failed to load ICP reference data");
  return r.json();
}

export interface IcpMapping {
  job_titles?: string[];
  regions?: string[];
  economic_buyer?: string;
  champion?: string;
  influencer?: string;
}

export async function getIcpMapping(product: string, useCase: string): Promise<IcpMapping> {
  const params = new URLSearchParams({ product, use_case: useCase });
  const r = await fetch(`${API_BASE}/api/runs/icp-mapping?${params.toString()}`);
  if (!r.ok) throw new Error("Failed to load ICP mapping");
  return r.json();
}

export interface UploadedCsv {
  runId: string;
  pathname: string;
}

/** A bare fetch() rejects (rather than resolving with a non-ok response) on
 * a connection-level failure - DNS, dropped wifi, a proxy/VPN hiccup - and
 * the browser's own rejection message is the unhelpful, identical-looking
 * "Failed to fetch" in every browser, with no indication of which of the
 * two network hops (our backend vs. Vercel Blob's own storage endpoint)
 * failed or why. Retrying once after a short delay is worth it here since
 * these are typically transient; only a real (non-network) error propagates
 * immediately. */
async function fetchWithRetry(url: string, init: RequestInit, label: string, retries = 1): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetch(url, init);
    } catch (e) {
      if (attempt >= retries) {
        throw new Error(`Network error ${label} - check your connection and try again.`);
      }
      await new Promise((r) => setTimeout(r, 800));
    }
  }
}

/** Uploads a CSV straight from the browser to Vercel Blob, bypassing our own
 * backend. Vercel caps a serverless function's request body at 4.5MB (hard,
 * not configurable), so POSTing a real Apollo export to /api/runs 413s at the
 * edge. This asks the backend only for a short-lived token scoped to one
 * pathname, then PUTs the bytes directly. Returns what startRun() needs to
 * point the pipeline at the uploaded file. */
export async function uploadCsvDirect(file: File): Promise<UploadedCsv> {
  const tokenRes = await fetchWithRetry(`${API_BASE}/api/runs/upload-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, content_type: file.type || "text/csv" }),
  }, "requesting an upload token");
  if (!tokenRes.ok) {
    const body = await tokenRes.json().catch(() => ({}));
    throw new Error(body.detail || `Could not start upload (${tokenRes.status})`);
  }
  const t = await tokenRes.json();

  // Header set is exact and was established empirically - see
  // vercel_blob.create_client_token's docstring. x-vercel-blob-access is
  // required (the store is private); omitting it fails the PUT.
  const putRes = await fetchWithRetry(t.upload_url, {
    method: "PUT",
    headers: {
      authorization: `Bearer ${t.token}`,
      "x-api-version": String(t.api_version),
      "x-vercel-blob-store-id": t.store_id,
      "x-vercel-blob-access": "private",
      "x-content-type": t.content_type,
    },
    body: file,
  }, "uploading the file to storage");
  if (!putRes.ok) {
    const body = await putRes.json().catch(() => ({}));
    throw new Error(body?.error?.message || `Upload failed (${putRes.status})`);
  }
  return { runId: t.run_id, pathname: t.pathname };
}

// Stays safely under Vercel's hard 4.5MB serverless function body cap once
// the other multipart form fields (project id, targeting JSON, etc.) are
// added on top of the raw file bytes.
const DIRECT_UPLOAD_FALLBACK_MAX_BYTES = 4 * 1024 * 1024;

export interface ResolvedCsvUpload {
  csvFile?: File;
  csvBlobPathname?: string;
  runId?: string;
}

/** Tries the direct-to-Blob upload first (works for a file of any size, but
 * PUTs to vercel.com - a third-party domain relative to the app's own
 * origin, which some corporate proxies/VPNs/antivirus SSL-inspection setups
 * block even though the app's own domain works fine; confirmed this isn't a
 * bug in the upload code itself - a fresh token + PUT from a real browser on
 * this app's own origin succeeds cleanly). If the direct upload fails and
 * the file is small enough, falls back to sending it inline through
 * startRun()'s own multipart body instead - same-origin, so it sidesteps
 * whatever blocked the direct path, at the cost of only working under
 * Vercel's ~4.5MB function body limit. */
export async function resolveCsvUpload(file: File): Promise<ResolvedCsvUpload> {
  try {
    const uploaded = await uploadCsvDirect(file);
    return { csvBlobPathname: uploaded.pathname, runId: uploaded.runId };
  } catch (e) {
    if (file.size <= DIRECT_UPLOAD_FALLBACK_MAX_BYTES) {
      return { csvFile: file };
    }
    throw e;
  }
}

export interface StartRunParams {
  inputSource: "csv" | "hubspot_project" | "campaign_idea";
  csvFile?: File;
  csvBlobPathname?: string;
  runId?: string;
  hubspotProjectId?: string;
  campaignIdea?: string;
  wizardTargeting?: WizardTargeting;
  mappingSheetFile?: File;
  companyCol?: string;
  domainCol?: string;
  employeeCol?: string;
}

export async function startRun(params: StartRunParams): Promise<RunStatus> {
  const fd = new FormData();
  fd.append("input_source", params.inputSource);
  if (params.hubspotProjectId) fd.append("hubspot_project_id", params.hubspotProjectId);
  if (params.campaignIdea) fd.append("campaign_idea", params.campaignIdea);
  if (params.wizardTargeting) fd.append("targeting_json", JSON.stringify(params.wizardTargeting));
  if (params.companyCol) fd.append("company_col", params.companyCol);
  if (params.domainCol) fd.append("domain_col", params.domainCol);
  if (params.employeeCol) fd.append("employee_col", params.employeeCol);
  if (params.csvBlobPathname) fd.append("csv_blob_pathname", params.csvBlobPathname);
  if (params.runId) fd.append("run_id", params.runId);
  if (params.csvFile) fd.append("csv_file", params.csvFile);
  if (params.mappingSheetFile) fd.append("mapping_sheet_file", params.mappingSheetFile);

  const r = await fetch(`${API_BASE}/api/runs`, { method: "POST", body: fd });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to start run (${r.status})`);
  }
  return r.json();
}

export interface ProjectPreview {
  project: Record<string, any>;
  list_fetchable: boolean;
  list_scrapable: boolean;
}

export async function previewProject(projectId: string): Promise<ProjectPreview> {
  const r = await fetch(`${API_BASE}/api/runs/project-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Could not load project (${r.status})`);
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
