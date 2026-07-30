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
  const [product, setProduct] = useState<string | null>(null);
  const [useCase, setUseCase] = useState<string | null>(null);
  const [useCaseOther, setUseCaseOther] = useState("");
  const [otherMode, setOtherMode] = useState(false);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [jobTitleOptions, setJobTitleOptions] = useState<string[]>([]);
  const [employeeSizes, setEmployeeSizes] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mappingLoading, setMappingLoading] = useState(false);

  async function pickUseCase(p: string, uc: string) {
    setProduct(p);
    setUseCase(uc);
    setOtherMode(false);
    setMappingLoading(true);
    try {
      const mapping = await getIcpMapping(p, uc);
      setJobTitleOptions(mapping.job_titles || []);
      setJobTitles(mapping.job_titles || []);
      if (mapping.regions?.length) setRegions(mapping.regions);
    } catch {
      // Best-effort prefill - the user can still pick everything manually.
      setJobTitleOptions([]);
    } finally {
      setMappingLoading(false);
    }
  }

  function pickOther() {
    setProduct(null);
    setUseCase(null);
    setJobTitleOptions([]);
    setOtherMode(true);
  }

  function next() { setStep((s) => Math.min(s + 1, STEP_TITLES.length - 1)); }
  function back() { setStep((s) => Math.max(s - 1, 0)); }

  async function submitWizard() {
    setSubmitting(true);
    setError(null);
    try {
      const effectiveUseCase = useCase || useCaseOther.trim();
      const wizardTargeting: WizardTargeting = {
        product: product || undefined,
        use_case: effectiveUseCase || undefined,
        job_titles: jobTitles,
        employee_sizes: employeeSizes,
        regions,
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
              <p style={{ fontSize: 13, marginBottom: 12 }}>Which use case is closest to what you're running?</p>
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
                            className={`pill ${product === p && useCase === uc ? "active" : ""}`}
                            disabled={mappingLoading}
                            onClick={() => pickUseCase(p, uc)}
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
            </div>
          )}

          {step === 5 && (
            <div>
              <div className="card" style={{ padding: 14, marginBottom: 12 }}>
                <table className="kv-table">
                  <tbody>
                    <tr><td style={{ fontWeight: 600, width: 120 }}>Use case</td><td>{useCase || useCaseOther || "(not set - defaults apply)"}</td></tr>
                    <tr><td style={{ fontWeight: 600 }}>Job titles</td><td>{jobTitles.length ? jobTitles.join(", ") : "Default HR/People-leader list"}</td></tr>
                    <tr><td style={{ fontWeight: 600 }}>Employee size</td><td>{employeeSizes.length ? employeeSizes.join(", ") : "No filter"}</td></tr>
                    <tr><td style={{ fontWeight: 600 }}>Region</td><td>{regions.length ? regions.join(", ") : "Global"}</td></tr>
                  </tbody>
                </table>
              </div>
              <FileField
                label="Optional: attach a company list (CSV/Excel) - otherwise you'll be asked for company names to search"
                file={csvFile} onChange={setCsvFile} accept=".csv,.xlsx,.xls"
              />
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
