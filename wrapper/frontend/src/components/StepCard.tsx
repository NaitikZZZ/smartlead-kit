import { useState } from "react";
import type { PendingQuestion } from "../lib/types";
import { answerQuestion } from "../lib/api";

const KIND_LABEL: Record<string, string> = { project: "Project", partner: "Partner", event: "Event" };

export default function StepCard({
  runId, question, onAnswered,
}: { runId: string; question: PendingQuestion; onAnswered: () => void }) {
  const [text, setText] = useState(question.default ?? "");
  const [multi, setMulti] = useState<string[]>([]);
  const [sel, setSel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
