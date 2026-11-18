import { useCallback, useEffect, useRef, useState } from "react";
import type { OpenProfileJob, OpenProfilePreview } from "../lib/types";
import {
  cancelOpenProfileJob, createOpenProfileJob, downloadOpenProfileFile, getMe, getOpenProfileJob,
  listOpenProfileJobs, previewOpenProfileList,
} from "../lib/api";
import "./OpenProfileCheck.css";

const STEPS = ["In line", "Reading search", "Checking profiles", "Building lists", "Ready"];
const STAGE_INDEX: Record<string, number> = { queued: 0, sizing: 1, importing: 2, merging: 3, done: 4 };
const CHIP: Record<string, string> = { queued: "In line", running: "Running", done: "Ready", failed: "Needs attention", cancelled: "Cancelled" };
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

const num = (n: number) => (n >= 0 && n <= 9 ? WORDS[n] : n.toLocaleString());
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function eta(min: number | null): string {
  if (min == null) return "";
  if (min < 2) return "Almost there";
  if (min < 60) return `About ${num(Math.round(min))} minutes left`;
  const h = Math.max(1, Math.round(min / 60));
  return `About ${num(h)} ${h === 1 ? "hour" : "hours"} left`;
}

type UrlCheck = { state: "empty" | "ok" | "bad"; msg?: string };

function checkUrl(raw: string): UrlCheck {
  const v = raw.trim();
  if (!v) return { state: "empty" };
  let u: URL;
  try { u = new URL(v); } catch { return { state: "bad", msg: "That does not look like a link. Copy the full address from your browser." }; }
  if (!/(^|\.)linkedin\.com$/.test(u.hostname)) return { state: "bad", msg: "This is not a LinkedIn link." };
  if (u.pathname.startsWith("/sales/lists")) return { state: "bad", msg: "This is a saved list. Open a people search instead, then copy its link." };
  if (!u.pathname.startsWith("/sales/search/people")) return { state: "bad", msg: "We need a Sales Navigator people search link. It starts with linkedin.com/sales/search/people." };
  if (!u.searchParams.get("query") && !u.searchParams.get("savedSearchId")) return { state: "bad", msg: "This link has no filters. Apply your filters in Sales Navigator, then copy the link." };
  return { state: "ok" };
}

export default function OpenProfileCheck({ onBack }: { onBack: () => void }) {
  const [jobs, setJobs] = useState<OpenProfileJob[]>([]);
  const [me, setMe] = useState<string>("");
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string>("");
  const seen = useRef<Map<string, string>>(new Map());
  const toastTimer = useRef<number | undefined>(undefined);
  const formRef = useRef<HTMLInputElement | null>(null);

  const notify = useCallback((msg: string) => {
    setToast(msg);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 3800);
  }, []);

  useEffect(() => { getMe().then((m) => m && setMe(m.name)).catch(() => {}); }, []);

  const load = useCallback(async () => {
    try {
      const next = await listOpenProfileJobs();
      for (const j of next) {
        const before = seen.current.get(j.id);
        if (before && before !== "done" && j.status === "done") notify(`${j.name} is ready to download.`);
        seen.current.set(j.id, j.status);
      }
      setJobs(next);
    } catch { /* keep the last good view; the next tick retries */ }
  }, [notify]);

  const busy = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;
    const tick = async () => {
      if (!document.hidden) await load();
      if (!stopped) timer = window.setTimeout(tick, busy ? 3000 : 15000);
    };
    tick();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [load, busy]);

  const check = checkUrl(url);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (check.state !== "ok" || submitting) return;
    setSubmitting(true);
    try {
      const { duplicate } = await createOpenProfileJob(url.trim(), title.trim());
      notify(duplicate ? "That search is already in line. Showing it below." : "Check started. We will update it here.");
      if (!duplicate) { setUrl(""); setTitle(""); }
      setFilter("all");
      await load();
    } catch (err: any) {
      notify(err.message || "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function again(j: OpenProfileJob) {
    setUrl(j.url);
    setTitle(j.name.startsWith("Check from ") ? "" : j.name);
    window.scrollTo({ top: 0, behavior: "smooth" });
    formRef.current?.focus();
    notify("Link filled in. Review it and press Start check.");
  }

  const shown = jobs.filter((j) => filter === "all" || j.requester === me);

  return (
    <div className="opc">
      <button className="btn-secondary opc-back" onClick={onBack}>Back</button>

      <section className="card opc-hero" aria-labelledby="opc-h">
        <h1 id="opc-h">Find open profiles from a Sales Navigator search</h1>
        <p className="opc-lede">Paste your search link. We split it, check every profile, and give you two lists, open profile and not open, plus a summary.</p>
        <form onSubmit={submit} noValidate>
          <label htmlFor="opc-url">Sales Navigator search link</label>
          <input id="opc-url" ref={formRef} type="url" inputMode="url" autoComplete="off" spellCheck={false}
            value={url} onChange={(e) => setUrl(e.target.value)} aria-invalid={check.state === "bad"} aria-describedby="opc-hint"
            placeholder="https://www.linkedin.com/sales/search/people?query=..." />
          <p id="opc-hint" className={`opc-hint ${check.state === "ok" ? "ok" : check.state === "bad" ? "bad" : ""}`} aria-live="polite">
            {check.state === "ok" ? "Looks good. This is a Sales Navigator people search." : check.state === "bad" ? check.msg : ""}
          </p>
          <label htmlFor="opc-title">Name this check <span className="opc-opt">optional</span></label>
          <input id="opc-title" type="text" maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. US HR leaders, Q4" />
          <div className="opc-actions">
            <button className="btn-primary" type="submit" disabled={check.state !== "ok" || submitting}>{submitting ? "Starting..." : "Start check"}</button>
            <p className="opc-expect">Takes about an hour for every 1,500 leads. Checks run one at a time, so yours may wait in line. You can close this page and come back.</p>
          </div>
        </form>
        <details className="opc-howto">
          <summary>Where do I find the link?</summary>
          <ol>
            <li>Open Sales Navigator and go to Lead search.</li>
            <li>Apply your filters until the results look right.</li>
            <li>Copy the full address from your browser's address bar and paste it above.</li>
          </ol>
        </details>
      </section>

      <section aria-labelledby="opc-checks">
        <div className="opc-head">
          <h2 id="opc-checks">Checks</h2>
          <div className="opc-seg" role="group" aria-label="Filter checks">
            <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Everyone</button>
            <button type="button" aria-pressed={filter === "mine"} onClick={() => setFilter("mine")}>Mine</button>
          </div>
        </div>
        <div className="opc-list" aria-live="polite">
          {shown.map((j) => <JobCard key={j.id} job={j} onChanged={load} onAgain={again} notify={notify} />)}
        </div>
        {shown.length === 0 && (
          <div className="opc-empty">
            <h3>{filter === "mine" ? "Nothing from you yet" : "No checks yet"}</h3>
            <p>{filter === "mine" ? "Checks you start will show up here." : "Paste a search link above and your first check will show up here."}</p>
          </div>
        )}
      </section>

      <div className={`opc-toast ${toast ? "show" : ""}`} role="status">{toast}</div>
    </div>
  );
}

function JobCard({ job: j, onChanged, onAgain, notify }: {
  job: OpenProfileJob; onChanged: () => void; onAgain: (j: OpenProfileJob) => void; notify: (m: string) => void;
}) {
  const [previews, setPreviews] = useState<Record<string, OpenProfilePreview | string>>({});
  const [events, setEvents] = useState<OpenProfileJob["events"] | string>();
  const [downloading, setDownloading] = useState<string>("");
  const active = j.status === "queued" || j.status === "running";
  const stageIdx = j.status === "done" ? 4 : STAGE_INDEX[j.stage] ?? 0;
  const pct = j.status === "queued" ? 0 : Math.round(j.percent);

  async function download(kind: string) {
    setDownloading(kind);
    try { await downloadOpenProfileFile(j.id, kind); } catch (e: any) { notify(e.message); } finally { setDownloading(""); }
  }

  async function togglePreview(kind: "open-profile" | "not-open", open: boolean) {
    if (!open || previews[kind]) return;
    try { const data = await previewOpenProfileList(j.id, kind); setPreviews((p) => ({ ...p, [kind]: data })); }
    catch (e: any) { setPreviews((p) => ({ ...p, [kind]: e.message })); }
  }

  async function toggleActivity(open: boolean) {
    if (!open || events) return;
    try { setEvents((await getOpenProfileJob(j.id)).events ?? []); } catch (e: any) { setEvents(e.message); }
  }

  async function cancel() {
    if (!window.confirm("Cancel this check? Work already done is kept, but you will need to start again for results.")) return;
    try { await cancelOpenProfileJob(j.id); notify("Cancelling. This takes a minute."); onChanged(); } catch (e: any) { notify(e.message); }
  }

  const cov = j.expected_total && j.unique_leads != null ? Math.round((j.unique_leads / j.expected_total) * 100) : null;

  const renderPreview = (kind: "open-profile" | "not-open") => {
    const p = previews[kind];
    if (!p) return <p>Loading...</p>;
    if (typeof p === "string") return <p>{p}</p>;
    if (!p.rows.length) return <p>This list is empty.</p>;
    return (
      <table>
        <thead><tr>{p.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{p.rows.map((r, i) => (
          <tr key={i}>{p.columns.map((c) => (
            <td key={c}>{c === "Profile" && r[c] ? <a href={r[c]} target="_blank" rel="noopener noreferrer">Open</a> : r[c]}</td>
          ))}</tr>
        ))}</tbody>
      </table>
    );
  };

  return (
    <article className="card opc-job">
      <div className="opc-job-head">
        <div>
          <h3>{j.name}</h3>
          <p className="opc-meta">{j.requester} · {when(j.created_at)}</p>
        </div>
        <span className={`opc-chip ${j.status}`}>{CHIP[j.status]}</span>
      </div>

      {active && (
        <>
          <ol className="opc-steps" aria-label="Progress">
            {STEPS.map((s, i) => <li key={s} className={i < stageIdx ? "done" : i === stageIdx ? "now" : ""}><span>{s}</span></li>)}
          </ol>
          <div className="opc-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: `${pct}%` }} /></div>
          <div className="opc-status">
            <span>
              {j.status === "queued"
                ? `${j.queue_ahead > 0 ? `${cap(num(j.queue_ahead))} ${j.queue_ahead === 1 ? "check is" : "checks are"} ahead of yours.` : "You are next."} We will start as soon as the line clears.`
                : j.cancelling ? "Stopping safely. This takes a minute." : j.message || "Working"}
            </span>
            <span><strong>{pct}%</strong>{j.eta_minutes != null ? ` · ${eta(j.eta_minutes)}` : ""}</span>
          </div>
          {!j.cancelling && <div className="opc-foot"><button className="btn-secondary opc-small" onClick={cancel}>Cancel check</button></div>}
        </>
      )}

      {j.status === "done" && (
        <>
          <div className="opc-stats">
            <div className="open"><b>{(j.open_count ?? 0).toLocaleString()}</b><span>Open profile</span></div>
            <div><b>{(j.not_open_count ?? 0).toLocaleString()}</b><span>Not open</span></div>
            <div><b>{(j.unique_leads ?? 0).toLocaleString()}</b><span>Total leads</span></div>
          </div>
          {cov != null && (
            <p className="opc-cov">Found {cov}% of the {j.expected_total!.toLocaleString()} leads Sales Navigator reported. A few can go missing when imports end early. Run the check again to fill gaps.</p>
          )}
          <div className="opc-downloads">
            <button className="btn-primary" onClick={() => download("open-profile")} disabled={!!downloading}>{downloading === "open-profile" ? "Preparing..." : "Open profile list"}</button>
            <button className="btn-secondary" onClick={() => download("not-open")} disabled={!!downloading}>{downloading === "not-open" ? "Preparing..." : "Not open list"}</button>
            {j.files.includes("summary") && <button className="btn-secondary" onClick={() => download("summary")} disabled={!!downloading}>Summary</button>}
            {j.files.includes("master") && <button className="btn-secondary" onClick={() => download("master")} disabled={!!downloading}>{downloading === "master" ? "Preparing..." : "All leads"}</button>}
          </div>
          <p className="opc-note">Open profile means the person has LinkedIn Premium. That is a strong signal, not a guarantee, so treat the list as likely open.</p>
          <div className="opc-more">
            <details onToggle={(e) => togglePreview("open-profile", e.currentTarget.open)}><summary>Preview open profile list</summary><div className="opc-scroll">{renderPreview("open-profile")}</div></details>
            <details onToggle={(e) => togglePreview("not-open", e.currentTarget.open)}><summary>Preview not open list</summary><div className="opc-scroll">{renderPreview("not-open")}</div></details>
            <details onToggle={(e) => toggleActivity(e.currentTarget.open)}>
              <summary>Activity</summary>
              {!events ? <p>Loading...</p> : typeof events === "string" ? <p>{events}</p> : (
                <ul className="opc-log">{events.map((ev, i) => <li key={i}><time>{when(ev.ts)}</time>{ev.message}</li>)}</ul>
              )}
            </details>
          </div>
          <div className="opc-foot"><button className="btn-secondary opc-small" onClick={() => onAgain(j)}>Run again</button></div>
        </>
      )}

      {(j.status === "failed" || j.status === "cancelled") && (
        <>
          <div className={j.status === "failed" ? "opc-error" : "opc-note"}>
            {j.status === "failed" ? `${j.error || "Something stopped this check."} Let the person who runs checks know, then start it again.` : "This check was cancelled."}
          </div>
          <div className="opc-foot"><button className="btn-secondary opc-small" onClick={() => onAgain(j)}>Start again</button></div>
        </>
      )}
    </article>
  );
}
