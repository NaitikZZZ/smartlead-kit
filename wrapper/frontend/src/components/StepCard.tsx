import { useState } from "react";
import type { PendingQuestion } from "../lib/types";
import { answerQuestion } from "../lib/api";
import LocationMultiSelect from "./LocationMultiSelect";
import AddCustomChip from "./AddCustomChip";

const KIND_LABEL: Record<string, string> = { project: "Project", partner: "Partner", event: "Event" };

export default function StepCard({
  runId, question, onAnswered,
}: { runId: string; question: PendingQuestion; onAnswered: () => void }) {
  const [text, setText] = useState(question.default ?? "");
  const [multi, setMulti] = useState<string[]>([]);
  const [sel, setSel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fields = question.context?.fields as Record<string, any> | undefined;
  const [formTitles, setFormTitles] = useState<string>(fields?.persona_titles?.default ?? "");
  const [formCap, setFormCap] = useState<number>(fields?.per_title_cap?.default ?? 2);
  const [formRegions, setFormRegions] = useState<string[]>(fields?.person_locations?.default ?? []);
  const [icpTitles, setIcpTitles] = useState<string[]>(fields?.job_titles?.default ?? []);
  const [icpRegions, setIcpRegions] = useState<string[]>(fields?.regions?.default ?? []);
  const [icpEmployeeSizes, setIcpEmployeeSizes] = useState<string[]>(fields?.employee_sizes?.default ?? []);

  const est = question.context?.estimate as
    | { credits: number; usd: number; units: number }
    | undefined;

  async function submit(value: any) {
    setSubmitting(true);
    setError(null);
    try {
      await answerQuestion(runId, question.key, value);
      onAnswered();
    } catch (e: any) {
      setError(e.message || "Failed to submit answer");
    } finally {
      setSubmitting(false);
    }
  }

  function toggle(opt: string) {
    setMulti((m) => (m.includes(opt) ? m.filter((x) => x !== opt) : [...m, opt]));
  }

  return (
    <div className="card" style={{ padding: 24 }}>
      <h5 style={{ marginBottom: 8 }}>Your input needed</h5>
      <h3 style={{ marginBottom: question.context?.reference_url ? 6 : 16 }}>{question.prompt}</h3>

      {question.context?.reference_url && (
        <p style={{ marginBottom: 16, fontSize: 12, color: "var(--dark-200)" }}>
          Uses{" "}
          <a href={question.context.reference_url as string} target="_blank" rel="noreferrer">
            {(question.context.reference_label as string) || "this list"} ↗
          </a>
        </p>
      )}

      {est && (
        <div className="est-box">
          Estimated Apollo cost for this step: <strong>{est.credits} credits</strong> ≈{" "}
          <strong>${est.usd.toFixed(2)}</strong> ({est.units} unit(s) at $
          {(13566 / 720000).toFixed(4)}/credit). Only charged if you say yes.
        </div>
      )}

      {question.type === "yes_no" && (
        <div style={{ display: "flex", gap: 12 }}>
          <button className="btn-primary" disabled={submitting} onClick={() => submit(true)}>Yes</button>
          <button className="btn-secondary" disabled={submitting} onClick={() => submit(false)}>No, skip</button>
        </div>
      )}

      {question.type === "choice" && question.options && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {question.options.map((opt) => (
            <button key={opt} className="pill" disabled={submitting} onClick={() => submit(opt)}>
              {opt}
            </button>
          ))}
        </div>
      )}

      {question.type === "location_multi_choice" && question.options && (
        <div>
          <div style={{ marginBottom: 16 }}>
            <LocationMultiSelect
              regions={question.options}
              countries={(question.context?.country_options as string[]) || []}
              selected={multi}
              onChange={setMulti}
              disabled={submitting}
            />
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn-primary" disabled={submitting} onClick={() => submit(multi)}>
              {multi.length ? `Continue with ${multi.length} selected` : "Continue"}
            </button>
            <button className="btn-secondary" disabled={submitting} onClick={() => submit([])}>
              Global (no filter)
            </button>
          </div>
        </div>
      )}

      {question.type === "multi_choice" && question.options && (
        <div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
            {question.options.map((opt) => (
              <button
                key={opt}
                className={`pill ${multi.includes(opt) ? "active" : ""}`}
                disabled={submitting}
                onClick={() => toggle(opt)}
              >
                {KIND_LABEL[opt] || opt}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn-primary" disabled={submitting} onClick={() => submit(multi)}>
              {multi.length ? `Continue with ${multi.length} selected` : "Continue"}
            </button>
            <button className="btn-secondary" disabled={submitting} onClick={() => submit([])}>
              None (list only)
            </button>
          </div>
        </div>
      )}

      {question.type === "dropdown" && question.options && (
        <div>
          <input
            list={`opts-${question.key}`}
            value={sel}
            onChange={(e) => setSel(e.target.value)}
            placeholder="Type to filter, then pick from the list..."
            style={{ marginBottom: 8 }}
          />
          <datalist id={`opts-${question.key}`}>
            {question.options.map((o) => <option key={o} value={o} />)}
          </datalist>
          <div style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 12 }}>
            {question.context?.count ? `${question.context.count} records loaded from HubSpot` : ""}
          </div>
          <button
            className="btn-primary"
            disabled={submitting || !question.options.includes(sel)}
            onClick={() => submit(sel)}
          >
            {submitting ? "Submitting..." : "Continue"}
          </button>
        </div>
      )}

      {question.type === "icp_confirm_form" && fields && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {(question.context?.economic_buyer || question.context?.champion || question.context?.influencer) && (
            <div className="card" style={{ padding: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dark-200)", marginBottom: 6, textTransform: "uppercase" }}>
                ICP Snapshot
              </div>
              {question.context?.economic_buyer && (
                <div style={{ fontSize: 13, marginBottom: 2 }}><strong>Economic Buyer:</strong> {question.context.economic_buyer}</div>
              )}
              {question.context?.champion && (
                <div style={{ fontSize: 13, marginBottom: 2 }}><strong>Champion:</strong> {question.context.champion}</div>
              )}
              {question.context?.influencer && (
                <div style={{ fontSize: 13 }}><strong>Influencer:</strong> {question.context.influencer}</div>
              )}
            </div>
          )}

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {fields.job_titles?.label}
            </label>
            {(fields.job_titles?.options as string[] || []).length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {(fields.job_titles?.options as string[]).map((t) => (
                  <label key={t} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={icpTitles.includes(t)}
                      onChange={() => setIcpTitles((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]))}
                      style={{ width: "auto" }}
                    />
                    {t}
                  </label>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: 12, color: "var(--dark-200)" }}>No titles mapped from the sheet - add your own below.</p>
            )}
            <AddCustomChip
              placeholder="Add a title not listed above..."
              disabled={submitting}
              onAdd={(t) => setIcpTitles((cur) => (cur.includes(t) ? cur : [...cur, t]))}
            />
          </div>

          {fields.employee_sizes && (
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                {fields.employee_sizes.label}
              </label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                {(fields.employee_sizes.options as string[] || []).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`pill ${icpEmployeeSizes.includes(s) ? "active" : ""}`}
                    disabled={submitting}
                    onClick={() =>
                      setIcpEmployeeSizes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]))
                    }
                  >
                    {s}
                  </button>
                ))}
              </div>
              <AddCustomChip
                placeholder="Add a custom range, e.g. 200-400 or 5000+"
                disabled={submitting}
                onAdd={(v) => setIcpEmployeeSizes((cur) => (cur.includes(v) ? cur : [...cur, v]))}
              />
            </div>
          )}

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {fields.regions?.label}
            </label>
            <LocationMultiSelect
              regions={(fields.regions?.options as string[]) || []}
              countries={(fields.regions?.country_options as string[]) || []}
              selected={icpRegions}
              onChange={setIcpRegions}
              disabled={submitting}
            />
            <AddCustomChip
              placeholder="Add a region/country not listed above..."
              disabled={submitting}
              onAdd={(r) => setIcpRegions((cur) => (cur.includes(r) ? cur : [...cur, r]))}
            />
          </div>

          <div>
            <button
              className="btn-primary"
              disabled={submitting}
              onClick={() => submit({ job_titles: icpTitles, regions: icpRegions, employee_sizes: icpEmployeeSizes })}
            >
              {submitting ? "Submitting..." : "Continue"}
            </button>
          </div>

          {question.context?.icp_sheet_url && (
            <p style={{ fontSize: 12, color: "var(--dark-200)" }}>
              Source:{" "}
              <a href={question.context.icp_sheet_url as string} target="_blank" rel="noreferrer">
                Check the ICP sheet ↗
              </a>
            </p>
          )}
        </div>
      )}

      {question.type === "discovery_form" && fields && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {fields.persona_titles?.label}
            </label>
            <input
              type="text"
              value={formTitles}
              onChange={(e) => setFormTitles(e.target.value)}
              placeholder={fields.persona_titles?.placeholder || ""}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {fields.per_title_cap?.label}
            </label>
            <input
              type="number"
              min={fields.per_title_cap?.min ?? 1}
              max={fields.per_title_cap?.max ?? 3}
              value={formCap}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                setFormCap(Number.isNaN(v) ? (fields.per_title_cap?.default ?? 2) : v);
              }}
              style={{ width: 100 }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
              {fields.person_locations?.label}
            </label>
            <LocationMultiSelect
              regions={(fields.person_locations?.options as string[]) || []}
              countries={(fields.person_locations?.country_options as string[]) || []}
              selected={formRegions}
              onChange={setFormRegions}
              disabled={submitting}
            />
          </div>

          <div>
            <button
              className="btn-primary"
              disabled={submitting}
              onClick={() =>
                submit({
                  persona_titles: formTitles,
                  per_title_cap: formCap,
                  person_locations: formRegions,
                })
              }
            >
              {submitting ? "Submitting..." : "Continue"}
            </button>
          </div>
        </div>
      )}

      {question.type === "text" && (
        <div>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={question.default || ""}
            style={{ marginBottom: 12 }}
            onKeyDown={(e) => { if (e.key === "Enter" && !submitting) submit(text); }}
          />
          <button className="btn-primary" disabled={submitting} onClick={() => submit(text)}>
            {submitting ? "Submitting..." : "Continue"}
          </button>
        </div>
      )}

      {error && <p style={{ color: "var(--red-300)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
