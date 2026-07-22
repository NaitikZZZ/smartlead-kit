import { useState } from "react";
import type { AppConfig } from "../lib/types";
import { startRun, previewProject, type ProjectPreview } from "../lib/api";
import Tooltip from "./Tooltip";

const SOURCES: { value: "csv" | "hubspot_project"; title: string; desc: string }[] = [
  { value: "csv", title: "CSV file / data sheet", desc: "Upload a target-account list directly" },
  { value: "hubspot_project", title: "HubSpot Project", desc: "Pull ICP/context from an ABM Campaigns pipeline record" },
];

// Canonical Apollo / Sales-Nav export header row the pipeline understands.
const TEMPLATE_HEADERS =
  "First Name,Last Name,Title,Company Name,Email,Seniority,Departments,Work Direct Phone,Mobile Phone,# Employees,Industry,Person Linkedin Url,Website,Domain,Company Linkedin Url,City,State,Country,Region,Annual Revenue,Technologies";
const EXAMPLE_ROW =
  "Jane,Doe,Head of HR,Acme Widgets,jane@acme.com,Head,Human Resources,,,1200,Retail,https://linkedin.com/in/janedoe,https://acme.com,acme.com,https://linkedin.com/company/acme,Austin,TX,United States,Americas,,";

const HEADER_GUIDE: { h: string; note: string }[] = [
  { h: "Company Name", note: "Required. Account identity (also accepts Company / Account Name)." },
  { h: "Domain", note: "If filled on every row, Domain Resolution is auto-skipped (also accepts Website)." },
  { h: "# Employees", note: "Disambiguates same-name companies; sets the HubSpot employee bucket." },
  { h: "Email", note: "If present, rows are treated as existing contacts - skips People Discovery, only gap-fills." },
  { h: "First Name / Last Name", note: "Names; used for email/phone reveal lookups." },
  { h: "Person Linkedin Url", note: "Feeds the LinkedIn / HeyReach file." },
  { h: "Work Direct Phone / Mobile Phone", note: "Feeds the Calling file." },
  { h: "Title, Industry, Seniority, Departments, Technologies, Annual Revenue", note: "Enrich HubSpot properties." },
  { h: "City, State, Country, Region", note: "HubSpot geo fields (Country/City are HubSpot-mandatory)." },
];

export default function SourceForm({ onStarted, appConfig }: { onStarted: (runId: string) => void; appConfig: AppConfig | null }) {
  const [source, setSource] = useState<"csv" | "hubspot_project">("csv");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState("");
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [loadingProject, setLoadingProject] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showHeaders, setShowHeaders] = useState(false);
  const [companyCol, setCompanyCol] = useState("");
  const [domainCol, setDomainCol] = useState("");
  const [employeeCol, setEmployeeCol] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Require a CSV only when we can't get the data another way: not an
  // auto-fetchable spreadsheet AND not an auto-scrapable web page.
  const needsUploadForProject =
    !!preview && !preview.list_fetchable && !preview.list_scrapable && !csvFile;
  const canSubmit =
    (source === "csv" && !!csvFile) ||
    (source === "hubspot_project" && !!projectId && !needsUploadForProject);

  async function loadProject() {
    if (!projectId.trim()) return;
    setLoadingProject(true);
    setProjectError(null);
    setPreview(null);
    try {
      setPreview(await previewProject(projectId));
    } catch (e: any) {
      setProjectError(e.message || "Could not load project");
    } finally {
      setLoadingProject(false);
    }
  }

  function downloadTemplate() {
    const csv = `${TEMPLATE_HEADERS}\n${EXAMPLE_ROW}\n`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "abm_pipeline_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      // For a Project with no CSV, confirm the list is auto-fetchable BEFORE
      // starting - otherwise a behind-login list would start a doomed run.
      if (source === "hubspot_project" && !csvFile) {
        let pv = preview;
        if (!pv) {
          pv = await previewProject(projectId);
          setPreview(pv);
        }
        // Auto-scrapable web-page lists proceed (backend extracts them).
        if (!pv.list_fetchable && !pv.list_scrapable) {
          const kind = pv.project.list_link_kind;
          const msg =
            kind === "document" || kind === "presentation"
              ? "The Project's linked file is a campaign copy (document), not the account list. Upload the target-account spreadsheet (CSV/Excel), then Start."
              : kind === "webpage"
                ? "The list is on a web page, but auto-extract needs an Anthropic API key on the server. Open it, save the accounts as CSV/Excel, upload, then Start."
                : !pv.project.target_list_link
                  ? "No data source link was found in this Project. Upload the account list (CSV/Excel), then Start."
                  : "This Project's list is behind a login. Open it above, download it as CSV/Excel, upload it, then Start.";
          setError(msg);
          setSubmitting(false);
          return;
        }
      }
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
      <h2 style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
        Where's the data coming from?
        <Tooltip text="Pick a CSV or a HubSpot Project. Names are cleaned automatically; every other step (domain, exclusion, discovery, email, phone, upload) asks you first. Exclusion always checks the HubSpot DNU list." />
      </h2>
      <p style={{ marginBottom: 20 }}>Pick a source. Each step asks before it runs.</p>

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
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--dark-200)" }}>
              HubSpot Project record ID or record URL
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="text"
                value={projectId}
                placeholder="https://app-na2.hubspot.com/contacts/6512810/record/0-970/816184961752/"
                onChange={(e) => setProjectId(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); loadProject(); } }}
              />
              <button className="btn-secondary" style={{ whiteSpace: "nowrap" }} disabled={!projectId.trim() || loadingProject} onClick={loadProject}>
                {loadingProject ? "Loading..." : "Load project"}
              </button>
            </div>
          </label>

          {projectError && <p style={{ color: "var(--red-300)", fontSize: 13, marginBottom: 12 }}>{projectError}</p>}

          {preview && (
            <div className="card" style={{ padding: 14, marginBottom: 12 }}>
              <h5 style={{ marginBottom: 8 }}>{preview.project.name || preview.project.project_id}</h5>
              <table className="kv-table">
                <tbody>
                  {([["ICP", "icp"], ["Region", "region"], ["Employee size", "employee_size"], ["Concept", "campaign_concept"]] as [string, string][])
                    .filter(([, k]) => preview.project[k])
                    .map(([label, k]) => (
                      <tr key={k}><td style={{ fontWeight: 600, width: 120 }}>{label}</td><td>{String(preview.project[k])}</td></tr>
                    ))}
                </tbody>
              </table>

              {Array.isArray(preview.project.links) && preview.project.links.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", color: "var(--dark-200)", marginBottom: 4 }}>
                    Links found in this project
                  </div>
                  {(preview.project.links as { url: string; kind: string; field: string }[]).map((l, i) => (
                    <div key={i} style={{ fontSize: 12, marginBottom: 3 }}>
                      <span className={l.kind === "spreadsheet" ? "tag-success" : "tag-warning"} style={{ marginRight: 6 }}>{l.kind}</span>
                      <a href={l.url} target="_blank" rel="noreferrer">{l.url.length > 58 ? l.url.slice(0, 58) + "…" : l.url}</a>
                      <span style={{ color: "var(--dark-200)" }}> · {l.field}</span>
                    </div>
                  ))}
                </div>
              )}

              {preview.list_fetchable ? (
                <p style={{ marginTop: 10, fontSize: 13 }}>
                  <span className="tag-success">Spreadsheet list</span> will be auto-pulled from the Project - no upload needed.
                </p>
              ) : (() => {
                const kind = preview.project.list_link_kind as string | undefined;
                const link = preview.project.target_list_link as string | undefined;
                const copy = preview.project.campaign_copy_link as string | undefined;
                const isDoc = kind === "document" || kind === "presentation";
                const isWeb = kind === "webpage";
                const noLink = !link;
                const listHref = (isWeb || (!isDoc && link)) ? link : null;   // spreadsheet-behind-login or webpage source
                const docHref = isDoc ? link : copy || null;                  // the doc / campaign copy
                return (
                  <div style={{ marginTop: 12, padding: 12, background: "var(--amber-100)", borderRadius: 8 }}>
                    {isDoc ? (
                      <p style={{ fontSize: 13, marginBottom: 8 }}>
                        <strong>The linked file is a {kind} (campaign copy), not the account list.</strong>{" "}
                        Documents hold the messaging; the target accounts must be a spreadsheet. Upload the
                        account list (CSV/Excel) below to enrich.
                      </p>
                    ) : isWeb && preview.list_scrapable ? (
                      <p style={{ fontSize: 13, marginBottom: 8 }}>
                        <strong>The list is on a web page</strong> (found in the project). The app will
                        auto-extract the accounts from it when you click Start (review recommended). You can
                        also upload a CSV/Excel below to override.
                      </p>
                    ) : isWeb ? (
                      <p style={{ fontSize: 13, marginBottom: 8 }}>
                        <strong>The list is on a web page</strong>, but auto-extract needs an Anthropic API key
                        on the server (not set). Open it, save the accounts as CSV/Excel, then upload below.
                      </p>
                    ) : noLink ? (
                      <p style={{ fontSize: 13, marginBottom: 8 }}>
                        <strong>No data-source link was found in this project.</strong> Upload the account
                        list (CSV/Excel) below.
                      </p>
                    ) : (
                      <p style={{ fontSize: 13, marginBottom: 8 }}>
                        <strong>This spreadsheet is behind a login</strong> (SharePoint/Drive), so it can't be pulled
                        automatically. Open it, download it as CSV/Excel, then upload it here.
                      </p>
                    )}
                    {listHref && (
                      <p style={{ marginBottom: 6 }}>
                        <a href={listHref} target="_blank" rel="noreferrer">{isWeb ? "Open the list source ↗" : "Open the list ↗"}</a>
                      </p>
                    )}
                    {docHref && (
                      <p style={{ marginBottom: 10, fontSize: 12 }}>
                        Campaign copy (reference): <a href={docHref} target="_blank" rel="noreferrer">open ↗</a>
                      </p>
                    )}
                    <FileField label="Upload the target-account list (CSV/Excel)" file={csvFile} onChange={setCsvFile} accept=".csv,.xlsx,.xls" />
                  </div>
                );
              })()}
            </div>
          )}

          {!preview && !loadingProject && (
            <p style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 8 }}>
              Paste the record link and click <strong>Load project</strong> - the app reads its campaign properties
              (ICP, region, list link, concept). If the list is behind a login you'll be prompted to download and upload it.
            </p>
          )}
        </>
      )}

      <p style={{ marginTop: 16, fontSize: 12, color: "var(--dark-200)" }}>
        <span className="tag-success">Exclusion</span> runs automatically against{" "}
        {appConfig?.exclusion_list_url ? (
          <a href={appConfig.exclusion_list_url} target="_blank" rel="noreferrer">
            {appConfig.exclusion_list_name || "the HubSpot DNU list"} ↗
          </a>
        ) : (
          <strong>{appConfig?.exclusion_list_name || "the HubSpot DNU list"}</strong>
        )}{" "}
        (matched by email domain). You'll confirm before it runs.
      </p>

      {source === "csv" && (
        <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={() => setShowHeaders(!showHeaders)} className="btn-secondary" style={{ fontSize: 12, padding: "6px 12px" }}>
            {showHeaders ? "Hide expected headers" : "Expected headers"}
          </button>
          <button onClick={downloadTemplate} className="btn-secondary" style={{ fontSize: 12, padding: "6px 12px" }}>
            Download CSV template
          </button>
        </div>
      )}

      {source === "csv" && showHeaders && (
        <div className="card" style={{ marginTop: 12, padding: 16 }}>
          <p style={{ fontSize: 12, marginBottom: 10 }}>
            The tool reads Apollo / Sales-Nav export headers (case-insensitive). Two triggers:
            a filled <strong>Domain</strong> column skips Domain Resolution; an <strong>Email</strong> column
            means rows are treated as existing contacts (skips People Discovery). Minimum to run: just <strong>Company Name</strong>.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table className="kv-table">
              <thead><tr><th>Header</th><th>What it controls</th></tr></thead>
              <tbody>
                {HEADER_GUIDE.map((g) => (
                  <tr key={g.h}><td style={{ fontWeight: 600 }}>{g.h}</td><td>{g.note}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {source === "csv" && (
        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            style={{ fontSize: 12, background: "none", border: "none", padding: 0, color: "var(--dark-200)", textDecoration: "underline" }}
          >
            {showAdvanced ? "Hide column overrides" : "Columns auto-detected — override if needed"}
          </button>
          {showAdvanced && (
            <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
              <TextField label="Company column name (auto-detected if blank)" value={companyCol} onChange={setCompanyCol} />
              <TextField label="Domain column name (auto-detected if blank)" value={domainCol} onChange={setDomainCol} />
              <TextField label="Employee-count column name" value={employeeCol} onChange={setEmployeeCol} />
            </div>
          )}
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
