import { useState } from "react";
import type { IcpOptions, WizardTargeting } from "../lib/types";
import { startRun, uploadCsvDirect, getIcpMapping } from "../lib/api";
import { FileField } from "./SourceForm";
import LocationMultiSelect from "./LocationMultiSelect";
import AddCustomChip from "./AddCustomChip";

const _OTHER = "Other - not listed";

type Mode = "wizard" | "ai_infer";
const STEP_TITLES = ["Idea", "Use case", "Job titles", "Employee size", "Region", "Review"];

export default function CampaignIdeaWizard({
  icpOptions, onStarted,
}: { icpOptions: IcpOptions | null; onStarted: (runId: string) => void }) {
  const [mode, setMode] = useState<Mode>("wizard");

  // ---- AI-infer mode: unchanged single-box flow ----
  const [aiIdea, setAiIdea] = useState("");
  const [aiCsvFile, setAiCsvFile] = useState<File | null>(null);
  const [aiSubmitting, setAiSubmitting] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  async function submitAiInfer() {
    setAiSubmitting(true);
    setAiError(null);
    try {
      const uploaded = aiCsvFile ? await uploadCsvDirect(aiCsvFile) : undefined;
      const run = await startRun({
        inputSource: "campaign_idea", campaignIdea: aiIdea.trim(),
        csvBlobPathname: uploaded?.pathname, runId: uploaded?.runId,
      });
      onStarted(run.run_id);
    } catch (e: any) {
      setAiError(e.message || "Failed to start run");
    } finally {
      setAiSubmitting(false);
    }
  }

  // ---- Wizard mode: paginated, instant back/forward, nothing hits the
  // backend until the final Start (except one cheap ICP-mapping lookup when
  // a use case is picked, to prefill sensible defaults). ----
  const [step, setStep] = useState(0);
  const [idea, setIdea] = useState("");
  const [selectedUseCases, setSelectedUseCases] = useState<{ product: string; useCase: string }[]>([]);
  const [useCaseOther, setUseCaseOther] = useState("");
  const [otherMode, setOtherMode] = useState(false);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [jobTitleOptions, setJobTitleOptions] = useState<string[]>([]);
  const [includeLookalikes, setIncludeLookalikes] = useState(false);
  const [employeeSizes, setEmployeeSizes] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [hqLocationsText, setHqLocationsText] = useState("");
  const [companyNames, setCompanyNames] = useState<string[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mappingLoading, setMappingLoading] = useState(false);

  // Toggling a use case on/off, not replacing the selection - the user can
  // target more than one use case (e.g. two Empuls angles) at once. Picking
  // a new use case merges its job titles/regions into what's already there
  // rather than overwriting it, so earlier picks (and any manual edits made
  // to them) survive.
  async function toggleUseCase(p: string, uc: string) {
    const isSelected = selectedUseCases.some((s) => s.product === p && s.useCase === uc);
    if (isSelected) {
      setSelectedUseCases((cur) => cur.filter((s) => !(s.product === p && s.useCase === uc)));
      return;
    }
    setSelectedUseCases((cur) => [...cur, { product: p, useCase: uc }]);
    setOtherMode(false);
    setMappingLoading(true);
    try {
      const mapping = await getIcpMapping(p, uc);
      const newTitles = mapping.job_titles || [];
      setJobTitleOptions((cur) => Array.from(new Set([...cur, ...newTitles])));
      setJobTitles((cur) => Array.from(new Set([...cur, ...newTitles])));
      if (mapping.regions?.length) {
        const newRegions = mapping.regions;
        setRegions((cur) => Array.from(new Set([...cur, ...newRegions])));
      }
    } catch {
      // Best-effort prefill - the user can still pick everything manually.
    } finally {
      setMappingLoading(false);
    }
  }

  function pickOther() {
    setSelectedUseCases([]);
    setJobTitleOptions([]);
    setOtherMode(true);
  }

  function next() { setStep((s) => Math.min(s + 1, STEP_TITLES.length - 1)); }
  function back() { setStep((s) => Math.max(s - 1, 0)); }

  async function submitWizard() {
    setSubmitting(true);
    setError(null);
    try {
      const effectiveUseCase = selectedUseCases.map((s) => s.useCase).join(", ") || useCaseOther.trim();
      const effectiveProduct = Array.from(new Set(selectedUseCases.map((s) => s.product))).join(", ");
      // Split on ";" or newline, not "," - a single HQ location is often
      // itself a "City, State" pair, so a comma can't double as the
      // between-locations separator here (unlike the region/country field).
      const hqLocations = hqLocationsText.split(/[;\n]+/).map((s) => s.trim()).filter(Boolean);
      const wizardTargeting: WizardTargeting = {
        product: effectiveProduct || undefined,
        use_case: effectiveUseCase || undefined,
        job_titles: jobTitles,
        include_lookalikes: includeLookalikes,
        employee_sizes: employeeSizes,
        regions,
        organization_locations: hqLocations,
        company_names: csvFile ? undefined : companyNames,
      };
      const campaignIdea = idea.trim() || effectiveUseCase || "Campaign idea (targeting set via wizard)";
      const uploaded = csvFile ? await uploadCsvDirect(csvFile) : undefined;
      const run = await startRun({
        inputSource: "campaign_idea",
        campaignIdea,
        wizardTargeting,
        csvBlobPathname: uploaded?.pathname,
        runId: uploaded?.runId,
      });
      onStarted(run.run_id);
    } catch (e: any) {
      setError(e.message || "Failed to start run");
    } finally {
      setSubmitting(false);
    }
  }

  const useCases = icpOptions?.use_cases || {};
  const hasUseCaseData = Object.keys(useCases).length > 0;

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <button
          type="button"
          className={`pill ${mode === "wizard" ? "active" : ""}`}
          onClick={() => setMode("wizard")}
        >
          I'll pick it myself
        </button>
        <button
          type="button"
          className={`pill ${mode === "ai_infer" ? "active" : ""}`}
          onClick={() => setMode("ai_infer")}
        >
          Just let AI figure it out
        </button>
      </div>

      {mode === "ai_infer" && (
        <div>
          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--dark-200)" }}>
              Describe your campaign
            </span>
            <textarea
              rows={4}
              value={aiIdea}
              placeholder="e.g. Customer Advocacy Platforms - target Product Managers and Partnership Heads for our advocacy use case, US/Canada"
              onChange={(e) => setAiIdea(e.target.value)}
            />
          </label>
          <FileField
            label="Optional: attach a company list (CSV/Excel) - otherwise you'll be asked for company names to search"
            file={aiCsvFile} onChange={setAiCsvFile} accept=".csv,.xlsx,.xls"
          />
          <p style={{ fontSize: 12, color: "var(--dark-200)", marginTop: -4, marginBottom: 12 }}>
            Claude matches your description to a Xoxoday use case and shows you the matched job titles/regions to
            confirm or edit before anything runs.
          </p>
          {aiError && <p style={{ color: "var(--red-300)", marginBottom: 12 }}>{aiError}</p>}
          <button className="btn-primary" style={{ width: "100%" }} disabled={!aiIdea.trim() || aiSubmitting} onClick={submitAiInfer}>
            {aiSubmitting ? "Starting..." : "Start"}
          </button>
        </div>
      )}

      {mode === "wizard" && (
        <div>
          <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
            {STEP_TITLES.map((t, i) => (
              <span
                key={t}
                style={{
                  fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 999,
                  color: i === step ? "var(--white)" : "var(--dark-200)",
                  background: i === step ? "var(--blue-300)" : i < step ? "var(--blue-100)" : "transparent",
                }}
              >
                {i + 1}. {t}
              </span>
            ))}
          </div>

          {step === 0 && (
            <div>
              <label style={{ display: "block", marginBottom: 12 }}>
                <span style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--dark-200)" }}>
                  Campaign idea (optional - just for context, e.g. in generated copy)
                </span>
                <textarea
                  rows={3}
                  value={idea}
                  placeholder="e.g. Reaching out to partnership teams about a co-marketing play"
                  onChange={(e) => setIdea(e.target.value)}
                />
              </label>
            </div>
          )}

          {step === 1 && (
            <div>
              <p style={{ fontSize: 13, marginBottom: 12 }}>
                Which use case(s) are closest to what you're running? Pick as many as apply.
              </p>
              {hasUseCaseData ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 12 }}>
                  {Object.entries(useCases).map(([p, cases]) => (
                    <div key={p}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dark-200)", marginBottom: 6, textTransform: "uppercase" }}>
                        {p}
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {cases.map((uc) => (
                          <button
                            key={uc}
                            type="button"
                            className={`pill ${selectedUseCases.some((s) => s.product === p && s.useCase === uc) ? "active" : ""}`}
                            disabled={mappingLoading}
                            onClick={() => toggleUseCase(p, uc)}
                          >
                            {uc}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 12 }}>
                  ICP reference sheet not available - describe your use case below instead.
                </p>
              )}
              <button
                type="button"
                className={`pill ${otherMode ? "active" : ""}`}
                onClick={pickOther}
                style={{ marginBottom: 8 }}
              >
                {_OTHER}
              </button>
              {otherMode && (
                <input
                  type="text"
                  value={useCaseOther}
                  placeholder="Describe your use case in your own words"
                  onChange={(e) => setUseCaseOther(e.target.value)}
                  style={{ marginTop: 4 }}
                />
              )}
              {mappingLoading && <p style={{ fontSize: 12, color: "var(--dark-200)", marginTop: 8 }}>Loading suggested titles/regions...</p>}
            </div>
          )}

          {step === 2 && (
            <div>
              <p style={{ fontSize: 13, marginBottom: 12 }}>
                Job titles to target - uncheck any to exclude, or add your own. Leave all unchecked for the default HR/People-leader list.
              </p>
              {jobTitleOptions.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
                  {jobTitleOptions.map((t) => (
                    <label key={t} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={jobTitles.includes(t)}
                        onChange={() => setJobTitles((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]))}
                        style={{ width: "auto" }}
                      />
                      {t}
                    </label>
                  ))}
                </div>
              )}
              {jobTitles.filter((t) => !jobTitleOptions.includes(t)).map((t) => (
                <div key={t} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 4 }}>
                  <span className="pill active" style={{ cursor: "pointer" }} onClick={() => setJobTitles((cur) => cur.filter((x) => x !== t))}>
                    {t} ✕
                  </span>
                </div>
              ))}
              <AddCustomChip
                placeholder="Add a job title..."
                onAdd={(t) => setJobTitles((cur) => (cur.includes(t) ? cur : [...cur, t]))}
              />
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginTop: 12, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={includeLookalikes}
                  onChange={(e) => setIncludeLookalikes(e.target.checked)}
                  style={{ width: "auto" }}
                />
                Include similar/lookalike titles (broader match - e.g. "Total Rewards Manager" when you asked
                for "Total Rewards Head"). Leave unchecked to match these titles exactly.
              </label>
            </div>
          )}

          {step === 3 && (
            <div>
              <p style={{ fontSize: 13, marginBottom: 12 }}>Employee size (optional - leave blank for no filter).</p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                {(icpOptions?.employee_size_buckets || []).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`pill ${employeeSizes.includes(s) ? "active" : ""}`}
                    onClick={() => setEmployeeSizes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <AddCustomChip
                placeholder="Add a custom range, e.g. 200-400 or 5000+"
                onAdd={(v) => setEmployeeSizes((cur) => (cur.includes(v) ? cur : [...cur, v]))}
              />
            </div>
          )}

          {step === 4 && (
            <div>
              <p style={{ fontSize: 13, marginBottom: 12 }}>Region / country (optional - blank = Global).</p>
              <LocationMultiSelect
                regions={icpOptions?.regions || []}
                countries={icpOptions?.countries || []}
                selected={regions}
                onChange={setRegions}
              />
              <AddCustomChip
                placeholder="Add a region/country not listed above..."
                onAdd={(r) => setRegions((cur) => (cur.includes(r) ? cur : [...cur, r]))}
              />

              <p style={{ fontSize: 13, margin: "20px 0 8px" }}>
                Company HQ location (optional) - for targeting companies headquartered somewhere
                specific (city, state, or country), regardless of where the contact themselves sits.
                Semicolon-separated for more than one.
              </p>
              <input
                type="text"
                value={hqLocationsText}
                onChange={(e) => setHqLocationsText(e.target.value)}
                placeholder="e.g. Austin, Texas; Bengaluru, India"
              />
            </div>
          )}

          {step === 5 && (
            <div>
              <div className="card" style={{ padding: 14, marginBottom: 12 }}>
                <table className="kv-table">
                  <tbody>
                    <tr>
                      <td style={{ fontWeight: 600, width: 120 }}>Use case</td>
                      <td>{selectedUseCases.length ? selectedUseCases.map((s) => s.useCase).join(", ") : (useCaseOther || "(not set - defaults apply)")}</td>
                    </tr>
                    <tr>
                      <td style={{ fontWeight: 600 }}>Job titles</td>
                      <td>
                        {jobTitles.length ? jobTitles.join(", ") : "Default HR/People-leader list"}
                        {jobTitles.length > 0 && (
                          <span style={{ color: "var(--dark-200)" }}>
                            {" "}({includeLookalikes ? "includes similar titles" : "exact match only"})
                          </span>
                        )}
                      </td>
                    </tr>
                    <tr><td style={{ fontWeight: 600 }}>Employee size</td><td>{employeeSizes.length ? employeeSizes.join(", ") : "No filter"}</td></tr>
                    <tr><td style={{ fontWeight: 600 }}>Region</td><td>{regions.length ? regions.join(", ") : "Global"}</td></tr>
                    <tr><td style={{ fontWeight: 600 }}>Company HQ location</td><td>{hqLocationsText.trim() ? hqLocationsText : "No filter"}</td></tr>
                  </tbody>
                </table>
              </div>
              <FileField
                label="Optional: attach a company list (CSV/Excel) - otherwise add target companies below"
                file={csvFile} onChange={setCsvFile} accept=".csv,.xlsx,.xls"
              />
              {!csvFile && (
                <div style={{ marginTop: 16 }}>
                  <p style={{ fontSize: 13, marginBottom: 8 }}>
                    Target companies to search (add them now so you're not asked again once the run starts).
                  </p>
                  {companyNames.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                      {companyNames.map((c) => (
                        <span
                          key={c}
                          className="pill active"
                          style={{ cursor: "pointer" }}
                          onClick={() => setCompanyNames((cur) => cur.filter((x) => x !== c))}
                        >
                          {c} ✕
                        </span>
                      ))}
                    </div>
                  )}
                  <AddCustomChip
                    placeholder="Add a company name, or paste a comma-separated list..."
                    onAdd={(c) => setCompanyNames((cur) => (cur.includes(c) ? cur : [...cur, c]))}
                  />
                </div>
              )}
            </div>
          )}

          {error && <p style={{ color: "var(--red-300)", marginTop: 12 }}>{error}</p>}

          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button className="btn-secondary" disabled={step === 0} onClick={back}>
              ← Back
            </button>
            {step < STEP_TITLES.length - 1 ? (
              <button className="btn-primary" style={{ flex: 1 }} onClick={next}>
                Next →
              </button>
            ) : (
              <button className="btn-primary" style={{ flex: 1 }} disabled={submitting} onClick={submitWizard}>
                {submitting ? "Starting..." : "Start"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
