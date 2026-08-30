import { useCallback, useEffect, useRef, useState } from "react";
import "./theme.css";
import { getConfig, getIcpOptions, getRun, retryRun, fileUrl } from "./lib/api";
import type { AppConfig, IcpOptions, RunStatus } from "./lib/types";
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
const POLL_STOP = new Set(["done", "failed", "normalized_stopped"]);

export default function App() {
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [icpOptions, setIcpOptions] = useState<IcpOptions | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    getConfig().then(setAppConfig).catch(() => setAppConfig(null));
    getIcpOptions().then(setIcpOptions).catch(() => setIcpOptions(null));
  }, []);

  // Pulled out of the effect (rather than inlined) so retryRun's handler can
  // restart polling directly - runId doesn't change on a retry (same run_id
  // reused), so re-running the effect isn't an option there.
  const poll = useCallback((id: string) => {
    if (pollRef.current) window.clearTimeout(pollRef.current);
    async function tick() {
      try {
        const status = await getRun(id);
        setRun(status);
        if (!POLL_STOP.has(status.stage)) pollRef.current = window.setTimeout(tick, 1200);
      } catch {
        pollRef.current = window.setTimeout(tick, 3000);
      }
    }
    tick();
  }, []);

  useEffect(() => {
    if (!runId) return;
    poll(runId);
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
  }, [runId, poll]);

  const refresh = () => runId && getRun(runId).then(setRun);

  async function handleRetry() {
    if (!runId) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const status = await retryRun(runId);
      setRun(status);
      poll(runId);
    } catch (e: any) {
      setRetryError(e.message || "Failed to retry the run");
    } finally {
      setRetrying(false);
    }
  }

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
        {run && !REVIEW_STAGES.has(run.stage) && run.output_files.length > 0 && <MidRunDownloads run={run} />}

        {!runId && <SourceForm onStarted={setRunId} appConfig={appConfig} icpOptions={icpOptions} />}

        {run && run.stage === "awaiting_answer" && run.pending_question && (
          <StepCard
            key={run.pending_question.key}
            runId={run.run_id}
            question={run.pending_question}
            onAnswered={refresh}
          />
        )}

        {run && !REVIEW_STAGES.has(run.stage) && run.stage !== "failed" && run.stage !== "normalized_stopped" &&
          !(run.stage === "awaiting_answer" && run.pending_question) && (
            <div className="card" style={{ padding: 24 }}>
              <h3>{run.message}</h3>
              <p style={{ marginTop: 8 }}>Working... this panel updates automatically.</p>
            </div>
          )}

        {run && REVIEW_STAGES.has(run.stage) && <ReviewUpload run={run} onImported={refresh} />}

        {run && run.stage === "normalized_stopped" && (
          <div className="card" style={{ padding: 24 }}>
            <h3>Normalization done</h3>
            <p style={{ marginTop: 8 }}>{run.message}</p>
            <button className="btn-secondary" style={{ marginTop: 16 }} onClick={() => { setRunId(null); setRun(null); }}>
              Start a new run
            </button>
          </div>
        )}

        {run && run.stage === "failed" && (
          <div className="card" style={{ padding: 24, borderColor: "var(--red-300)" }}>
            <h3 style={{ color: "var(--red-300)" }}>Run failed</h3>
            <p style={{ marginTop: 8 }}>{run.error}</p>
            {retryError && <p style={{ marginTop: 8, color: "var(--red-300)" }}>{retryError}</p>}
            <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
              <button className="btn-primary" disabled={retrying} onClick={handleRetry}>
                {retrying ? "Retrying..." : "Retry"}
              </button>
              <button className="btn-secondary" onClick={() => { setRunId(null); setRun(null); }}>
                Start a new run
              </button>
            </div>
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

function MidRunDownloads({ run }: { run: RunStatus }) {
  return (
    <div className="card" style={{ padding: 16, marginBottom: 20 }}>
      <h5 style={{ marginBottom: 8 }}>Downloads so far</h5>
      <p style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 12 }}>
        Available now, while the rest of the run continues - handy if you want to search any of these manually.
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {run.output_files.map((f) => (
          <a key={f} href={fileUrl(run.run_id, f)} className="btn-secondary" style={{ textDecoration: "none", fontSize: 13 }}>
            ⬇ {f}
          </a>
        ))}
      </div>
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
