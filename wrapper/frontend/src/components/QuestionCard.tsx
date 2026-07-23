import { useState } from "react";
import type { PendingQuestion } from "../lib/types";
import { answerQuestion } from "../lib/api";

export default function QuestionCard({
  runId, question, onAnswered,
}: { runId: string; question: PendingQuestion; onAnswered: () => void }) {
  const [text, setText] = useState(question.default ?? "");
  const [selected, setSelected] = useState<string[]>(
    question.default ? String(question.default).split(",").map(s => s.trim()) : []
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <div className="card" style={{ padding: 24 }}>
      <h5 style={{ marginBottom: 8 }}>Question</h5>
      <h3 style={{ marginBottom: 20 }}>{question.prompt}</h3>

      {question.type === "yes_no" && (
        <div style={{ display: "flex", gap: 12 }}>
          <button className="btn-primary" disabled={submitting} onClick={() => submit(true)}>Yes</button>
          <button className="btn-secondary" disabled={submitting} onClick={() => submit(false)}>No</button>
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
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {question.options.map((opt) => (
              <button
                key={opt}
                className={selected.includes(opt) ? "pill pill-selected" : "pill"}
                disabled={submitting}
                onClick={() => {
                  setSelected(
                    selected.includes(opt)
                      ? selected.filter(s => s !== opt)
                      : [...selected, opt]
                  );
                }}
              >
                {selected.includes(opt) ? "✓ " : ""}{opt}
              </button>
            ))}
          </div>
          <button
            className="btn-primary"
            disabled={submitting}
            onClick={() => submit(selected.join(", "))}
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
