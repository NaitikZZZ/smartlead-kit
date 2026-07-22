import { useEffect, useRef, useState } from "react";
import "./theme.css";
import { getConfig, getRun } from "./lib/api";
import type { AppConfig, RunStatus } from "./lib/types";
import SourceForm from "./components/SourceForm";
import StepSidebar from "./components/StepSidebar";
import StepCard from "./components/StepCard";
import CostBar from "./components/CostBar";
import ReviewUpload from "./components/ReviewUpload";
import ActivityLog from "./components/ActivityLog";
import Tooltip from "./components/Tooltip";

const REVIEW_STAGES = new Set(["awaiting_import_confirmation", "importing_to_hubspot", "done"]);
// Only stop polling at truly terminal states. We must KEEP polling through
// "awaiting_answer" and the processing stages between questions - otherwise
// after you answer one question the UI never sees the next one appear.
const POLL_STOP = new Set(["done", "failed"]);

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
        {run && <ProjectInfo run={run} />}

        {!runId && <SourceForm onStarted={setRunId} appConfig={appConfig} />}

        {run && run.stage === "awaiting_answer" && run.pending_question && (
          <StepCard
            key={run.pending_question.key}
            runId={run.run_id}
            question={run.pending_question}
            onAnswered={refresh}
          />
        )}

        {run && !REVIEW_STAGES.has(run.stage) && run.stage !== "failed" &&
          !(run.stage === "awaiting_answer" && run.pending_question) && (
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

        {run && <ActivityLog run={run} />}
      </main>
    </div>
  );
}

function ProjectInfo({ run }: { run: RunStatus }) {
  const p = run.stats?.project_meta as Record<string, any> | undefined;
  if (!p || !p.project_id) return null;
  const rows: [string, any][] = [
    ["ICP", p.icp],
    ["Region", p.region],
    ["Employee size", p.employee_size],
    ["Request type", p.request_type],
    ["Concept", p.campaign_concept],
    ["List link", p.target_list_link],
  ];
  return (
    <div className="card" style={{ padding: 16, marginBottom: 20 }}>
      <h5 style={{ marginBottom: 8 }}>HubSpot Project — {p.name || p.project_id}</h5>
      <table className="kv-table">
        <tbody>
          {rows.filter(([, v]) => v).map(([k, v]) => (
            <tr key={k}>
              <td style={{ fontWeight: 600, width: 130 }}>{k}</td>
              <td>{String(v).startsWith("http") ? <a href={v} target="_blank" rel="noreferrer">{v}</a> : String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfigBadges({ appConfig }: { appConfig: AppConfig | null }) {
  if (!appConfig) return null;
  const items: [string, boolean, string][] = [
    ["Apollo", appConfig.apollo_configured, "Apollo is connected - domain, email, and phone enrichment work."],
    ["HubSpot read", appConfig.hubspot_read_configured, "Can read HubSpot (projects, exclusion list, associations)."],
    ["HubSpot write", appConfig.hubspot_write_configured, "Can upload contacts and create lists in HubSpot."],
  ];
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {items.map(([label, ok, tip]) => (
        <Tooltip key={label} text={tip}>
          <span className={ok ? "tag-success" : "tag-warning"}>{label}</span>
        </Tooltip>
      ))}
    </div>
  );
}
