import { useEffect, useRef } from "react";
import type { RunStatus } from "../lib/types";

function fmt(s: number): string {
  if (s == null) return "";
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
}

export default function ActivityLog({ run }: { run: RunStatus | null }) {
  const log = (run?.stats?.log as { elapsed_s: number; msg: string }[] | undefined) ?? [];
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [log.length]);

  if (!run) return null;
  const elapsed = run.stats?.elapsed_s as number | undefined;

  return (
    <div className="card" style={{ padding: 16, marginTop: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h5>Activity log</h5>
        {elapsed != null && <span className="tag-success">Total elapsed {fmt(elapsed)}</span>}
      </div>
      <div className="log-box">
        {log.length === 0 && <div className="log-line" style={{ opacity: 0.6 }}>Waiting for activity...</div>}
        {log.map((l, i) => {
          const prev = i > 0 ? log[i - 1].elapsed_s : 0;
          const delta = Math.max(0, l.elapsed_s - prev);
          return (
            <div key={i} className="log-line">
              <span className="log-t">{fmt(l.elapsed_s).padStart(6)}</span>
              <span className="log-d">+{delta.toFixed(1)}s</span>
              {l.msg}
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
    </div>
  );
}
