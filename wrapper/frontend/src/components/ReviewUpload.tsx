import { useEffect, useState } from "react";
import type { RunStatus, StepInfo } from "../lib/types";
import { confirmImport, fileUrl } from "../lib/api";

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

export default function ReviewUpload({ run, onImported }: { run: RunStatus; onImported: () => void }) {
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string[][] | null>(null);

  const counts = (run.stats?.channel_counts ?? {}) as Record<string, number>;
  const imported = run.stage === "done";
  const importResult = run.stats?.hubspot_import as any;
  const assocStep = ((run.stats?.steps as StepInfo[]) ?? []).find((s) => s.key === "associations");

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
      <h2 style={{ marginBottom: 6 }}>{imported ? "Uploaded" : "Preview before upload"}</h2>
      <p style={{ marginBottom: 20 }}>
        {imported
          ? "Contacts are in HubSpot and a static list was created."
          : "Three channel files are ready. Review, then confirm to push the email file to HubSpot. Nothing is written until you confirm."}
      </p>

      {CHANNELS.map((ch) => (
        <div key={ch.key} className="card file-card">
          <div>
            <div style={{ fontWeight: 600 }}>{ch.label}</div>
            <div style={{ fontSize: 12, color: "var(--dark-200)" }}>{ch.note}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span className="chan-count">{counts[ch.key] ?? 0}</span>
            <a className="btn-secondary" href={fileUrl(run.run_id, ch.file)} style={{ textDecoration: "none" }}>
              Download
            </a>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 16 }}>
        <a className="btn-secondary" href={fileUrl(run.run_id, "SUMMARY.md")} style={{ textDecoration: "none", fontSize: 12 }}>
          Download run summary
        </a>
      </div>

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
          {importResult.heyreach && (
            <p style={{ fontSize: 13, marginTop: 6 }}>
              {importResult.heyreach.status === "pushed" ? (
                <>
                  <span className="tag-success">HeyReach</span> {importResult.heyreach.pushed} LinkedIn lead(s) pushed to list
                  {" "}"{importResult.heyreach.list_name}" (id {importResult.heyreach.list_id}).
                </>
              ) : importResult.heyreach.status !== "skipped" ? (
                <>
                  <span className="tag-warning">HeyReach</span> {importResult.heyreach.message || importResult.heyreach.status}
                </>
              ) : null}
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
    </div>
  );
}
