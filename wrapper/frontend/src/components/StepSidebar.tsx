import type { RunStatus, StepInfo, StepStatus } from "../lib/types";
import { STEPS } from "../lib/types";

const DOT: Record<StepStatus, string> = { done: "✓", running: "•", skipped: "–", pending: "" };

export default function StepSidebar({ run }: { run: RunStatus | null }) {
  const byKey: Record<string, StepInfo> = {};
  for (const s of (run?.stats?.steps as StepInfo[] | undefined) ?? []) byKey[s.key] = s;
  const currentStep = run?.pending_question?.context?.step as string | undefined;

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <h1>ABM Pipeline</h1>
        <p>List → clean → enrich → HubSpot + HeyReach</p>
      </div>

      {STEPS.map((def, i) => {
        const info = byKey[def.key];
        const status: StepStatus = info?.status ?? "pending";
        const isCurrent = currentStep === def.key || (!currentStep && run == null && i === 0);
        return (
          <div key={def.key} className={`side-step ${status} ${isCurrent ? "current" : ""}`}>
            <span className={`s-dot ${status}`}>{DOT[status] || i + 1}</span>
            <div>
              <div className="s-title">{def.title}</div>
              <div className="s-hint">{info?.summary || def.hint}</div>
              {(info?.time || info?.cost) && (
                <div className="s-hint" style={{ color: "#c7d3e0", marginTop: 3 }}>
                  {info?.time ? info.time : ""}
                  {info?.cost ? `  ·  ${info.cost.credits} cr / $${info.cost.usd}` : ""}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </aside>
  );
}
