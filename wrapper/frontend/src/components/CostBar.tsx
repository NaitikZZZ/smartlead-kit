import type { CostInfo, RunStatus } from "../lib/types";

export default function CostBar({ run }: { run: RunStatus | null }) {
  const cost = run?.stats?.cost as CostInfo | undefined;
  const stats = run?.stats ?? {};
  const excl = stats.exclusion ?? {};
  const channels = stats.channel_counts ?? {};

  const metrics: [string, string | number][] = [
    ["Apollo credits", cost?.credits ?? 0],
    ["Apollo spend", `$${(cost?.usd ?? 0).toFixed(2)}`],
    ["OK to reach out", excl.ok_to_reach_out ?? "-"],
    ["Excluded", excl.excluded ?? "-"],
  ];
  if (channels.email != null) metrics.push(["Email-ready", channels.email]);

  return (
    <div className="card cost-bar">
      {metrics.map(([k, v]) => (
        <div key={k} className="cost-metric">
          <div className="v">{v}</div>
          <div className="k">{k}</div>
        </div>
      ))}
    </div>
  );
}
