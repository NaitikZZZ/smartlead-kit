import { STAGE_LABELS, STAGE_ORDER } from "../lib/types";
import type { RunStatus } from "../lib/types";

export default function StageProgress({ run }: { run: RunStatus }) {
  const isFailed = run.stage === "failed";
  const currentIndex = STAGE_ORDER.indexOf(run.stage);
  const pct = isFailed ? 100 : Math.min(100, Math.round(((currentIndex + 1) / STAGE_ORDER.length) * 100));

  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <h3>{isFailed ? "Run failed" : STAGE_LABELS[run.stage]}</h3>
        <span style={{ fontSize: 13, color: "var(--dark-200)" }}>{pct}%</span>
      </div>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${pct}%`, background: isFailed ? "var(--red-300)" : "var(--blue-300)" }}
        />
      </div>
      <p style={{ marginTop: 12, fontSize: 13 }}>{isFailed ? run.error : run.message}</p>
    </div>
  );
}
