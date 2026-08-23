import { useEffect, useState } from "react";
import type { CostInfo, RunStatus, StepInfo } from "../lib/types";
import { confirmImport, fileUrl } from "../lib/api";
import { costByOp } from "./CostBar";
import Tooltip from "./Tooltip";

const CHANNELS = [
  { key: "email", file: "email_upload.csv", label: "Email (HubSpot)", note: "Verified emails only. Uploaded to HubSpot + a static list." },
  { key: "linkedin", file: "linkedin_upload.csv", label: "LinkedIn (HeyReach)", note: "Pushed to a new HeyReach list (named after the campaign) on upload." },
  { key: "calling", file: "calling_upload.csv", label: "Calling (dialer)", note: "Contacts with a phone number, for the SDR dialer." },
];

// Minimal CSV parse (handles quoted fields) for a small on-screen preview.
function parseCsv(text: string, maxRows: number): string[][] {
  const rows: string[][] = [];
  let field = "", row: string[] = [], inQuotes = false;
  for (let i = 0; i < text.length && rows.length <= maxRows; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (field !== "" || row.length) { row.push(field); rows.push(row); row = []; field = ""; }
      if (c === "\r" && text[i + 1] === "\n") i++;
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

const EXCLUDED_PAGE_SIZE = 50;

export default function ReviewUpload({ run, onImported }: { run: RunStatus; onImported: () => void }) {
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string[][] | null>(null);
  const [excludedPage, setExcludedPage] = useState(0);

  const counts = (run.stats?.channel_counts ?? {}) as Record<string, number>;
  const imported = run.stage === "done";
  const importResult = run.stats?.hubspot_import as any;
  const assocStep = ((run.stats?.steps as StepInfo[]) ?? []).find((s) => s.key === "associations");

  const excl = (run.stats?.exclusion ?? {}) as any;
  const excludedRows = (excl.excluded_rows ?? []) as { company: string; domain: string; reason: string }[];

  useEffect(() => {
    fetch(fileUrl(run.run_id, "email_upload.csv"))
      .then((r) => (r.ok ? r.text() : ""))
      .then((t) => setPreview(t ? parseCsv(t, 6) : []))
      .catch(() => setPreview([]));
  }, [run.run_id]);

  async function doImport() {
    setImporting(true);
    setError(null);
    try {
      await confirmImport(run.run_id);
      onImported();
    } catch (e: any) {
      setError(e.message || "Import failed");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
        {imported ? "Uploaded" : "Preview before upload"}
        {!imported && <Tooltip text="Nothing is written until you press Confirm. The email file goes to HubSpot + a static list; LinkedIn goes to HeyReach. Downloads are at the bottom." />}
      </h2>
      <p style={{ marginBottom: 20 }}>
        {imported ? "Contacts are in HubSpot and a static list was created." : "Review below, then confirm the upload."}
      </p>

      {/* Channel counts (info) */}
      <div className="card cost-bar">
        {CHANNELS.map((ch) => (
          <div key={ch.key} className="cost-metric">
            <div className="v">{counts[ch.key] ?? 0}</div>
            <div className="k">
              {ch.label}
              <Tooltip text={ch.note} />
            </div>
          </div>
        ))}
      </div>

      {/* Apollo cost breakdown */}
      {(() => {
        const cost = run.stats?.cost as CostInfo | undefined;
        if (!cost || !cost.breakdown?.length) return null;
        const agg = costByOp(run);
        const rows: [string, string][] = [
          ["Domain resolution", "domain_resolution"],
          ["Email reveal", "email_reveal"],
          ["Phone (calling)", "mobile_phone"],
        ];
        return (
          <div className="card" style={{ padding: 16, marginTop: 20, overflowX: "auto" }}>
            <h5 style={{ marginBottom: 10 }}>Apollo cost breakdown</h5>
            <table className="kv-table">
              <thead><tr><th>Item</th><th>Credits</th><th>Cost</th></tr></thead>
              <tbody>
                {rows.filter(([, op]) => agg[op]).map(([label, op]) => (
                  <tr key={op}>
                    <td>{label}</td>
                    <td>{agg[op].credits}</td>
                    <td>${agg[op].usd.toFixed(2)}</td>
                  </tr>
                ))}
                <tr style={{ fontWeight: 700 }}>
                  <td>Total</td>
                  <td>{cost.credits}</td>
                  <td>${cost.usd.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
            <p style={{ fontSize: 12, color: "var(--dark-200)", marginTop: 8 }}>
              Phone (calling) reveals are ~8 credits each; email matches ~1. Cached lookups are free.
            </p>
          </div>
        );
      })()}

      {/* Why excluded */}
      {!excl.skipped && (excl.excluded ?? 0) > 0 && (
        <div className="card" style={{ padding: 16, marginTop: 20, overflowX: "auto" }}>
          <h5 style={{ marginBottom: 6 }}>Excluded accounts ({excl.excluded})</h5>
          <p style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 10 }}>
            Matched by email domain against{" "}
            {excl.dnu_list_url ? (
              <a href={excl.dnu_list_url} target="_blank" rel="noreferrer">the HubSpot DNU list ↗</a>
            ) : (
              <>the HubSpot DNU list{excl.dnu_list_id ? ` (${excl.dnu_list_id})` : ""}</>
            )}{" "}
            - these were removed and not uploaded.
          </p>
          {(() => {
            const pageCount = Math.max(1, Math.ceil(excludedRows.length / EXCLUDED_PAGE_SIZE));
            const page = Math.min(excludedPage, pageCount - 1);
            const start = page * EXCLUDED_PAGE_SIZE;
            const pageRows = excludedRows.slice(start, start + EXCLUDED_PAGE_SIZE);
            return (
              <>
                <table className="kv-table">
                  <thead><tr><th>Company</th><th>Domain</th><th>Why excluded</th></tr></thead>
                  <tbody>
                    {pageRows.map((r, i) => (
                      <tr key={start + i}><td>{r.company}</td><td>{r.domain}</td><td>{r.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
                {pageCount > 1 && (
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
                    <button
                      className="btn-secondary"
                      disabled={page === 0}
                      onClick={() => setExcludedPage((p) => Math.max(0, p - 1))}
                    >
                      ← Prev
                    </button>
                    <span style={{ fontSize: 12, color: "var(--dark-200)" }}>
                      Page {page + 1} of {pageCount} (rows {start + 1}-{start + pageRows.length} of {excludedRows.length})
                    </span>
                    <button
                      className="btn-secondary"
                      disabled={page >= pageCount - 1}
                      onClick={() => setExcludedPage((p) => Math.min(pageCount - 1, p + 1))}
                    >
                      Next →
                    </button>
                  </div>
                )}
              </>
            );
          })()}
          {excl.excluded > excludedRows.length && (
            <p style={{ fontSize: 12, marginTop: 8 }}>+{excl.excluded - excludedRows.length} more excluded (full list in the run summary).</p>
          )}
        </div>
      )}

      {assocStep?.summary && (
        <p style={{ marginTop: 16, fontSize: 13 }}>
          <span className="tag-success">Associations</span> {assocStep.summary}
        </p>
      )}

      {preview && preview.length > 1 && (
        <div className="card" style={{ padding: 16, marginTop: 20, overflowX: "auto" }}>
          <h5 style={{ marginBottom: 10 }}>Email file preview (first {preview.length - 1} rows)</h5>
          <table className="kv-table">
            <thead>
              <tr>{preview[0].slice(0, 6).map((h, i) => <th key={i}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {preview.slice(1).map((r, ri) => (
                <tr key={ri}>{r.slice(0, 6).map((c, ci) => <td key={ci}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {imported && importResult && (
        <div className="card" style={{ padding: 16, marginTop: 20 }}>
          <h5 style={{ marginBottom: 8 }}>HubSpot result</h5>
          <p style={{ fontSize: 13 }}>
            {importResult.total} contact(s): {importResult.new} new, {importResult.updated} updated.
          </p>
          {importResult.list?.list_url && (
            <p style={{ fontSize: 13, marginTop: 6 }}>
              List: <a href={importResult.list.list_url} target="_blank" rel="noreferrer">{importResult.list.list_url}</a>
            </p>
          )}
          {importResult.dropped_invalid_email > 0 && (
            <p style={{ fontSize: 13, marginTop: 6 }}>
              <span className="tag-warning">Skipped</span>{" "}
              {importResult.dropped_invalid_email} contact(s) HubSpot rejected as invalid emails
              (everything else imported):{" "}
              {(importResult.rejected_invalid_email || [])
                .map((x: any) => x.email)
                .join(", ")}
            </p>
          )}
          {importResult.heyreach && importResult.heyreach.status !== "skipped" && (
            <p style={{ fontSize: 13, marginTop: 6 }}>
              {importResult.heyreach.status === "pushed" ? (
                <>
                  <span className="tag-success">HeyReach</span> {importResult.heyreach.pushed} LinkedIn lead(s) pushed to list
                  {" "}"{importResult.heyreach.list_name}" (id {importResult.heyreach.list_id}).
                </>
              ) : (
                <>
                  <span className="tag-warning">HeyReach</span> {importResult.heyreach.message || importResult.heyreach.status}
                </>
              )}
            </p>
          )}
        </div>
      )}

      {!imported && (
        <>
          {error && <p style={{ color: "var(--red-300)", marginTop: 16 }}>{error}</p>}
          <button className="btn-danger-confirm" style={{ marginTop: 20 }} disabled={importing} onClick={doImport}>
            {importing ? "Uploading to HubSpot..." : `Confirm & upload ${counts.email ?? 0} email contact(s) to HubSpot`}
          </button>
        </>
      )}

      {/* Downloads - at the very end */}
      <div className="card" style={{ padding: 16, marginTop: 28 }}>
        <h5 style={{ marginBottom: 10 }}>Downloads</h5>
        {CHANNELS.map((ch) => (
          <div key={ch.key} className="file-card" style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontWeight: 600 }}>{ch.label}</span>
              <span style={{ color: "var(--dark-200)", fontWeight: 400 }}>({counts[ch.key] ?? 0})</span>
              <Tooltip text={ch.note} />
            </div>
            <a className="btn-secondary" href={fileUrl(run.run_id, ch.file)} style={{ textDecoration: "none" }}>Download</a>
          </div>
        ))}
        <a
          className="btn-secondary"
          href={fileUrl(run.run_id, "SUMMARY.md")}
          style={{ textDecoration: "none", fontSize: 12, marginTop: 12, display: "inline-block" }}
        >
          Download run summary (includes full exclusion list)
        </a>
      </div>
    </div>
  );
}
