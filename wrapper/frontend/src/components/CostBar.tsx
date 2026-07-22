import type { CostInfo, RunStatus } from "../lib/types";
import Tooltip from "./Tooltip";

export function costByOp(run: RunStatus | null): Record<string, { credits: number; usd: number }> {
  const bd = (run?.stats?.cost as CostInfo | undefined)?.breakdown ?? [];
  const agg: Record<string, { credits: number; usd: number }> = {};
  for (const b of bd) {
    const a = agg[b.operation] ?? { credits: 0, usd: 0 };
    a.credits += b.credits;
    a.usd = Math.round((a.usd + b.usd) * 100) / 100;
    agg[b.operation] = a;
  }
  return agg;
}

export default function CostBar({ run }: { run: RunStatus | null }) {
  const cost = run?.stats?.cost as CostInfo | undefined;
  const stats = run?.stats ?? {};
  const excl = stats.exclusion ?? {};
  const agg = costByOp(run);
  const email = agg.email_reveal ?? { credits: 0, usd: 0 };
  const calling = agg.mobile_phone ?? { credits: 0, usd: 0 };

  const metrics: [string, string | number, string][] = [
    ["Email $", `$${email.usd.toFixed(2)}`, "Cost of revealing verified work emails (~1 Apollo credit each). Cached contacts are free."],
    ["Calling $", `$${calling.usd.toFixed(2)}`, "Cost of revealing phone numbers (~8 Apollo credits each). This is your calling-data spend."],
    ["Total $", `$${(cost?.usd ?? 0).toFixed(2)}`, "Total Apollo spend so far this run (domain + email + phone)."],
    ["Credits", cost?.credits ?? 0, "Apollo credits used so far. 1 credit ≈ $0.019 on your plan."],
    ["OK", excl.ok_to_reach_out ?? "-", "Accounts allowed to reach out (passed the exclusion check)."],
    ["Excluded", excl.excluded ?? "-", "Accounts removed because they're on the HubSpot do-not-use (DNU) list."],
  ];

  return (
    <div className="card cost-bar">
      {metrics.map(([k, v, tip]) => (
        <div key={k} className="cost-metric">
          <div className="v">{v}</div>
          <div className="k">
            {k}
            <Tooltip text={tip} />
          </div>
        </div>
      ))}
    </div>
  );
}
