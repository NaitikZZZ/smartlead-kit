import { useEffect, useRef, useState } from "react";
import "./theme.css";
import { getConfig, getRun } from "./lib/api";
import type { AppConfig, RunStatus } from "./lib/types";
import SourceForm from "./components/SourceForm";
import StepSidebar from "./components/StepSidebar";
import StepCard from "./components/StepCard";
import CostBar from "./components/CostBar";
import ReviewUpload from "./components/ReviewUpload";

const REVIEW_STAGES = new Set(["awaiting_import_confirmation", "importing_to_hubspot", "done"]);
const POLL_STOP = new Set(["awaiting_answer", "awaiting_import_confirmation", "done", "failed"]);

export default function App() {
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    getConfig().then(setAppConfig).catch(() => setAppConfig(null));
  }, []);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    async function poll() {
      try {
        const status = await getRun(runId!);
        if (cancelled) return;
        setRun(status);
        if (!POLL_STOP.has(status.stage)) pollRef.current = window.setTimeout(poll, 1200);
      } catch {
        pollRef.current = window.setTimeout(poll, 3000);
      }
    }
    poll();
    return () => {
      cancelled = true;
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
  }, [runId]);

  const refresh = () => runId && getRun(runId).then(setRun);

  return (
    <div className="app-shell">
      <StepSidebar run={run} />

      <main className="main">
        <div className="main-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1>{run ? run.message : "New enrichment run"}</h1>
            {run && <p style={{ fontSize: 13, marginTop: 4 }}>Run {run.run_id}</p>}
          </div>
          <ConfigBadges appConfig={appConfig} />
        </div>

        {run && <CostBar run={run} />}

        {!runId && <SourceForm onStarted={setRunId} />}

        {run && run.stage === "awaiting_answer" && run.pending_question && (
          <StepCard runId={run.run_id} question={run.pending_question} onAnswered={refresh} />
        )}

        {run && !REVIEW_STAGES.has(run.stage) && run.stage !== "awaiting_answer" && run.stage !== "failed" && (
          <div className="card" style={{ padding: 24 }}>
            <h3>{run.message}</h3>
            <p style={{ marginTop: 8 }}>Working... this panel updates automatically.</p>
          </div>
        )}

        {run && REVIEW_STAGES.has(run.stage) && <ReviewUpload run={run} onImported={refresh} />}

        {run && run.stage === "failed" && (
          <div className="card" style={{ padding: 24, borderColor: "var(--red-300)" }}>
            <h3 style={{ color: "var(--red-300)" }}>Run failed</h3>
            <p style={{ marginTop: 8 }}>{run.error}</p>
            <button className="btn-secondary" style={{ marginTop: 16 }} onClick={() => { setRunId(null); setRun(null); }}>
              Start a new run
            </button>
          </div>
        )}

        {run && run.stage === "done" && (
          <button className="btn-secondary" style={{ marginTop: 20 }} onClick={() => { setRunId(null); setRun(null); }}>
            Start a new run
          </button>
        )}
      </main>
    </div>
  );
}

function ConfigBadges({ appConfig }: { appConfig: AppConfig | null }) {
  if (!appConfig) return null;
  const items: [string, boolean][] = [
    ["Apollo", appConfig.apollo_configured],
    ["HubSpot read", appConfig.hubspot_read_configured],
    ["HubSpot write", appConfig.hubspot_write_configured],
  ];
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {items.map(([label, ok]) => (
        <span key={label} className={ok ? "tag-success" : "tag-warning"}>{label}</span>
      ))}
    </div>
  );
}
