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
 * failed or why. Retrying is worth it here since these are typically
 * transient; only a real (non-network) error propagates immediately.
 * Cellular connections drop mid-request far more often than wifi (tower
 * handoffs, signal dips) during the several seconds a multi-MB PUT takes, so
 * a single quick retry isn't enough headroom there - back off exponentially
 * across a few attempts instead of retrying once. */
async function fetchWithRetry(url: string, init: RequestInit, label: string, retries = 3): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetch(url, init);
    } catch (e) {
      if (attempt >= retries) {
        throw new Error(`Network error ${label} - check your connection and try again.`);
      }
      await new Promise((r) => setTimeout(r, 800 * 2 ** attempt));
    }
  }
}

async function mintUploadToken(file: File): Promise<any> {
  const tokenRes = await fetchWithRetry(`${API_BASE}/api/runs/upload-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, content_type: file.type || "text/csv" }),
  }, "requesting an upload token");
  if (!tokenRes.ok) {
    const body = await tokenRes.json().catch(() => ({}));
    throw new Error(body.detail || `Could not start upload (${tokenRes.status})`);
  }
  return tokenRes.json();
}

/** PUTs straight from the browser to Vercel Blob, bypassing our own backend.
 * Vercel caps a serverless function's request body at 4.5MB (hard, not
 * configurable), so POSTing a real Apollo export to /api/runs 413s at the
 * edge - this is what makes arbitrary-size uploads possible at all. Header
 * set is exact and was established empirically - see
 * vercel_blob.create_client_token's docstring. x-vercel-blob-access is
 * required (the store is private); omitting it fails the PUT. */
async function putDirectToBlob(file: File, t: any): Promise<void> {
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
}

/** Uploads a CSV straight from the browser to Vercel Blob. Returns what
 * startRun() needs to point the pipeline at the uploaded file. Prefer
 * resolveCsvUpload() for anything user-facing - it falls back when this
 * fails. */
export async function uploadCsvDirect(file: File): Promise<UploadedCsv> {
  const t = await mintUploadToken(file);
  await putDirectToBlob(file, t);
  return { runId: t.run_id, pathname: t.pathname };
}

// Small enough that one piece surviving a flaky mobile connection is likely,
// large enough to keep the round-trip count reasonable for a real Apollo
// export.
const UPLOAD_CHUNK_BYTES = 1_000_000;

/** Fallback for when the direct-to-Blob PUT can't reach vercel-storage.com at
 * all - a third-party domain relative to the app's own origin that some
 * mobile carriers (and corporate proxies/VPNs/antivirus SSL-inspection
 * setups) block outright, which is why retrying the direct PUT doesn't help
 * (confirmed: retrying with backoff didn't fix it on the affected mobile
 * network). Uploads the same bytes to our own backend origin in small
 * pieces instead - same-origin, so it sidesteps whatever blocked the direct
 * path - then has the backend do the one PUT to Blob itself, server-side,
 * where the mobile network can't interfere. Works for a file of any size. */
async function uploadCsvChunked(file: File, runId: string, pathname: string, contentType: string): Promise<void> {
  const totalChunks = Math.max(1, Math.ceil(file.size / UPLOAD_CHUNK_BYTES));
  for (let i = 0; i < totalChunks; i++) {
    const chunk = file.slice(i * UPLOAD_CHUNK_BYTES, (i + 1) * UPLOAD_CHUNK_BYTES);
    const params = new URLSearchParams({ run_id: runId, chunk_index: String(i) });
    const res = await fetchWithRetry(`${API_BASE}/api/runs/upload-chunk?${params.toString()}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: chunk,
    }, `uploading part ${i + 1} of ${totalChunks}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Upload failed on part ${i + 1} of ${totalChunks} (${res.status})`);
    }
  }
  const finalizeRes = await fetchWithRetry(`${API_BASE}/api/runs/upload-finalize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, pathname, total_chunks: totalChunks, content_type: contentType }),
  }, "finishing the upload");
  if (!finalizeRes.ok) {
    const body = await finalizeRes.json().catch(() => ({}));
    throw new Error(body.detail || `Could not finish upload (${finalizeRes.status})`);
  }
}

// Last-resort fallback (see resolveCsvUpload) - stays safely under Vercel's
// hard 4.5MB serverless function body cap once the other multipart form
// fields (project id, targeting JSON, etc.) are added on top of the raw file
// bytes.
const DIRECT_UPLOAD_FALLBACK_MAX_BYTES = 4 * 1024 * 1024;

export interface ResolvedCsvUpload {
  csvFile?: File;
  csvBlobPathname?: string;
  runId?: string;
}

/** Three tiers, each covering what the one before it can't:
 * 1. Direct-to-Blob PUT from the browser - works for a file of any size.
 * 2. If that fails (blocked third-party domain), the same bytes chunked
 *    through our own origin - still works for a file of any size, since our
 *    own backend does the actual Blob PUT server-side.
 * 3. If that also fails (e.g. Blob/Redis isn't configured on this server at
 *    all, such as local dev) and the file is small enough, send it inline
 *    through startRun()'s own multipart body - same-origin, but capped by
 *    Vercel's ~4.5MB function body limit. */
export async function resolveCsvUpload(file: File): Promise<ResolvedCsvUpload> {
  try {
    const t = await mintUploadToken(file);
    try {
      await putDirectToBlob(file, t);
    } catch (e) {
      await uploadCsvChunked(file, t.run_id, t.pathname, t.content_type);
    }
    return { csvBlobPathname: t.pathname, runId: t.run_id };
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

export async function retryRun(runId: string): Promise<RunStatus> {
  const r = await fetch(`${API_BASE}/api/runs/${runId}/retry`, { method: "POST" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to retry run (${r.status})`);
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
