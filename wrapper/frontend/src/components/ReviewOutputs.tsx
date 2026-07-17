import { useState } from "react";
import type { RunStatus } from "../lib/types";
import { confirmImport, fileUrl } from "../lib/api";

export default function ReviewOutputs({ run, onImported }: { run: RunStatus; onImported: () => void }) {
  const [checked, setChecked] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const exclusion = run.stats?.exclusion;
  const domainRes = run.stats?.domain_resolution;
  const enrich = run.stats?.apollo_enrich;
  const phone = run.stats?.apollo_phone;
  const search = run.stats?.apollo_search;
  const completeness = run.stats?.completeness;
  const readyCount = run.stats?.hubspot_ready_count;
  const alreadyImported = run.stage === "done" && run.stats?.hubspot_import;

  async function handleImport() {
    setImporting(true);
    setError(null);
    try {
      const result = await confirmImport(run.run_id);
      setImportResult(result);
      onImported();
    } catch (e: any) {
      setError(e.message || "Import failed");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ padding: 24 }}>
        <h2 style={{ marginBottom: 16 }}>Run complete - review before importing</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          <StatCard label="Accounts" value={exclusion?.total} sub={exclusion?.skipped ? "exclusion skipped" : `${exclusion?.excluded ?? 0} excluded`} />
          <StatCard label="Domains resolved" value={domainRes?.resolved} sub={domainRes?.skipped ? "enrichment skipped" : `of ${domainRes?.total ?? "-"}`} />
          <StatCard label="Contacts found" value={search?.candidates_found} sub={search?.skipped ? "-" : `across ${search?.companies_searched ?? "-"} accounts`} />
          <StatCard label="With email" value={enrich?.has_email} sub={enrich?.skipped ? "-" : `${enrich?.contacts_enriched ?? "-"} enriched`} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 12 }}>
          <StatCard label="With phone" value={phone?.phones_found} sub={phone?.skipped ? "-" : `of ${phone?.total ?? "-"}`} />
          <StatCard label="HubSpot-ready" value={readyCount} sub="verified email only" />
          {completeness && !completeness.skipped && (
            <StatCard label="Completeness fills" value={completeness.filled} sub="via web search" />
          )}
        </div>

        {search?.zero_match_companies?.length > 0 && (
          <p style={{ marginTop: 16, fontSize: 12 }}>
            <span className="tag-warning">No matches</span> — {search.zero_match_companies.length} account(s) had zero Apollo contacts: {search.zero_match_companies.join(", ")}
          </p>
        )}

        <div style={{ marginTop: 20, display: "flex", gap: 12, flexWrap: "wrap" }}>
          {run.output_files.map((f) => (
            <a key={f} href={fileUrl(run.run_id, f)} className="btn-secondary" style={{ textDecoration: "none", fontSize: 13 }}>
              ⬇ {f}
            </a>
          ))}
        </div>

        {run.pr_url ? (
          <p style={{ marginTop: 16 }}>
            <a href={run.pr_url} target="_blank" rel="noreferrer" style={{ color: "var(--blue-300)", fontWeight: 600 }}>
              View pull request →
            </a>
            {" "}— merge it yourself, or email <a href="mailto:naitik.chavda@xoxoday.com">naitik.chavda@xoxoday.com</a> if you can't.
          </p>
        ) : (
          <p style={{ marginTop: 16, fontSize: 12, color: "var(--dark-200)" }}>
            No PR opened (GitHub isn't configured on this server) - output files are still saved and downloadable above.
          </p>
        )}
      </div>

      {!alreadyImported && (
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ marginBottom: 4 }}>Import to HubSpot</h3>
          <p style={{ marginBottom: 16, fontSize: 13 }}>
            This writes {readyCount} contact(s) into HubSpot per the association you chose earlier. Nothing is written until you confirm.
          </p>

          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
            <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} style={{ width: "auto" }} />
            I've reviewed the output files and want to write these {readyCount} contacts into HubSpot.
          </label>

          {error && <p style={{ color: "var(--red-300)", marginTop: 12 }}>{error}</p>}

          <button
            className="btn-danger-confirm"
            style={{ marginTop: 16 }}
            disabled={!checked || importing}
            onClick={handleImport}
          >
            {importing ? "Importing..." : "Confirm & import to HubSpot"}
          </button>
        </div>
      )}

      {(importResult || alreadyImported) && (
        <div className="card" style={{ padding: 24, borderColor: "var(--green-300)" }}>
          <h3 style={{ marginBottom: 8 }}>
            <span className="tag-success">Imported</span>
          </h3>
          {run.hubspot_list_url && (
            <p style={{ marginBottom: 12 }}>
              <a href={run.hubspot_list_url} target="_blank" rel="noreferrer" style={{ color: "var(--blue-300)", fontWeight: 600 }}>
                View the HubSpot list →
              </a>
            </p>
          )}
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(importResult || run.stats?.hubspot_import, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: any; sub?: string }) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <h5>{label}</h5>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--dark-200)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}
