import { useState } from "react";
import { startRun } from "../lib/api";

const SOURCES: { value: "csv" | "hubspot_project"; title: string; desc: string }[] = [
  { value: "csv", title: "CSV file / data sheet", desc: "Upload a target-account list directly" },
  { value: "hubspot_project", title: "HubSpot Project", desc: "Pull ICP/context from an ABM Campaigns pipeline record" },
];

export default function SourceForm({ onStarted }: { onStarted: (runId: string) => void }) {
  const [source, setSource] = useState<"csv" | "hubspot_project">("csv");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [companyCol, setCompanyCol] = useState("");
  const [domainCol, setDomainCol] = useState("");
  const [employeeCol, setEmployeeCol] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit =
    (source === "csv" && !!csvFile) ||
    (source === "hubspot_project" && !!projectId && !!csvFile);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const run = await startRun({
        inputSource: source,
        csvFile: csvFile || undefined,
        hubspotProjectId: projectId || undefined,
        companyCol: companyCol || undefined,
        domainCol: domainCol || undefined,
        employeeCol: employeeCol || undefined,
      });
      onStarted(run.run_id);
    } catch (e: any) {
      setError(e.message || "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card" style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 4 }}>Where's the data coming from?</h2>
      <p style={{ marginBottom: 20 }}>
        Normalization always runs. Everything else - domain resolution, exclusion, discovery, enrichment, naming, and
        how it lands in HubSpot + HeyReach - gets asked step by step. Exclusion checks against the HubSpot
        "ABM EXCLSIONS - DNU" list automatically.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12, marginBottom: 20 }}>
        {SOURCES.map((s) => (
          <button
            key={s.value}
            onClick={() => setSource(s.value)}
            className="card"
            style={{
              textAlign: "left",
              padding: 16,
              border: source === s.value ? "2px solid var(--blue-300)" : "1px solid var(--border)",
              background: source === s.value ? "var(--blue-100)" : "var(--white)",
            }}
          >
            <h4 style={{ marginBottom: 6 }}>{s.title}</h4>
            <p style={{ fontSize: 12 }}>{s.desc}</p>
          </button>
        ))}
      </div>

      {source === "csv" && (
        <FileField label="Data file / sheet" file={csvFile} onChange={setCsvFile} accept=".csv,.xlsx,.xls" />
      )}

      {source === "hubspot_project" && (
        <>
          <TextField
            label="HubSpot Project record ID"
            value={projectId}
            onChange={setProjectId}
            placeholder="e.g. 809013892828"
          />
          <FileField
            label="Target account CSV (the linked list, downloaded)"
            file={csvFile}
            onChange={setCsvFile}
            accept=".csv,.xlsx,.xls"
          />
        </>
      )}

      <p style={{ marginTop: 16, fontSize: 12 }}>
        <span className="tag-success">Exclusion</span> checks against the HubSpot{" "}
        <strong>ABM EXCLSIONS - DNU</strong> list automatically - no sheet upload needed.
      </p>

      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="btn-secondary"
        style={{ marginTop: 16, fontSize: 12, padding: "6px 12px" }}
      >
        {showAdvanced ? "Hide" : "Show"} advanced options
      </button>

      {showAdvanced && (
        <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
          <TextField label="Company column name (auto-detected if blank)" value={companyCol} onChange={setCompanyCol} />
          <TextField label="Domain column name (auto-detected if blank)" value={domainCol} onChange={setDomainCol} />
          <TextField label="Employee-count column name" value={employeeCol} onChange={setEmployeeCol} />
        </div>
      )}

      {error && <p style={{ color: "var(--red-300)", marginTop: 12 }}>{error}</p>}

      <button
        className="btn-primary"
        style={{ marginTop: 20, width: "100%" }}
        disabled={!canSubmit || submitting}
        onClick={handleSubmit}
      >
        {submitting ? "Starting..." : "Start"}
      </button>
    </div>
  );
}

function TextField({
  label, value, onChange, placeholder,
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <span style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--dark-200)" }}>{label}</span>
      <input type="text" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function FileField({
  label, file, onChange, accept,
}: { label: string; file: File | null; onChange: (f: File | null) => void; accept: string }) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <span style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--dark-200)" }}>{label}</span>
      <input type="file" accept={accept} onChange={(e) => onChange(e.target.files?.[0] || null)} />
      {file && <span style={{ fontSize: 12, color: "var(--green-300)" }}>{file.name}</span>}
    </label>
  );
}
