import { useState } from "react";
import type { DefaultWorkflow, SalesNav, SmartleadSchedule } from "../lib/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function DefaultWorkflowPanel({
  channels, defaults, loadError, useDefault, onUseDefault, schedule, onSchedule, salesNav, onSalesNav,
}: {
  channels: string[];
  defaults: DefaultWorkflow | null;
  loadError: string | null;
  useDefault: boolean;
  onUseDefault: (v: boolean) => void;
  schedule: SmartleadSchedule | null;
  onSchedule: (s: SmartleadSchedule) => void;
  salesNav: SalesNav;
  onSalesNav: (v: SalesNav) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasSmartlead = channels.includes("smartlead");
  const hasHeyreach = channels.includes("heyreach");
  if (!hasSmartlead && !hasHeyreach) return null;

  const setField = <K extends keyof SmartleadSchedule>(k: K, v: SmartleadSchedule[K]) =>
    schedule && onSchedule({ ...schedule, [k]: v });

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16 }}>
      <h5 style={{ marginBottom: 10 }}>Use the default workflow?</h5>
      <div style={{ display: "flex", gap: 20, fontSize: 14, marginBottom: 10 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="radio" checked={useDefault} onChange={() => onUseDefault(true)} /> Yes, use the default
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input type="radio" checked={!useDefault} onChange={() => onUseDefault(false)} /> No, customize
        </label>
      </div>

      {hasHeyreach && useDefault && (
        <div style={{ margin: "4px 0 14px", padding: "12px 14px", background: "var(--blue-100)", borderRadius: 8 }}>
          <b style={{ fontSize: 14 }}>Does the LinkedIn account have Sales Navigator?</b>
          <div style={{ display: "flex", gap: 18, fontSize: 14, margin: "8px 0 4px", flexWrap: "wrap" }}>
            {([["no", "No"], ["yes", "Yes"], ["both", "Some do, some don't"]] as [SalesNav, string][]).map(([v, label]) => (
              <label key={v} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="radio" checked={salesNav === v} onChange={() => onSalesNav(v)} /> {label}
              </label>
            ))}
          </div>
          <p style={{ fontSize: 12, margin: 0 }}>
            {salesNav === "no"
              ? "Standard cadence: connection request, then 4 DMs."
              : "Open Profile cadence: open profiles get 2 InMails first, everyone else follows the standard path. This is an unvalidated draft, so check the draft in HeyReach before starting it."}
          </p>
        </div>
      )}

      <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 10px" }} onClick={() => setOpen(!open)}>
        {open ? "Hide" : "See"} what the default workflow looks like
      </button>
      {loadError && <p style={{ fontSize: 13, marginTop: 8 }}><span className="tag-warning">Couldn't load</span> {loadError}</p>}

      {open && defaults && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 14 }}>
          {hasSmartlead && (
            <div>
              <h5 style={{ marginBottom: 6 }}>Smartlead</h5>
              <ul style={{ fontSize: 13, paddingLeft: 18, margin: 0 }}>
                <li>Created PAUSED, nothing sends until you start it</li>
                <li>Sequence: your emails, on the delays in your file (day {defaults.smartlead.cadence_days.join(", ")} if it gives none)</li>
                <li>
                  Schedule: {defaults.smartlead.schedule.days_of_the_week.map((d) => DAYS[d - 1]).join(", ")},{" "}
                  {defaults.smartlead.schedule.start_hour}:00 to {defaults.smartlead.schedule.end_hour}:00 {defaults.smartlead.schedule.timezone},{" "}
                  {defaults.smartlead.schedule.min_time_btw_emails} min between emails, {defaults.smartlead.schedule.max_new_leads_per_day} new leads/day
                </li>
                <li>No open or click tracking, stop on reply, unsubscribe tag on</li>
                <li>ESP matching on; OOO replies ignored in reply %, leads auto-restarted after OOO with a 7-day delay</li>
                {defaults.smartlead.automated_extras.map((e) => <li key={e}>{e}</li>)}
                <li>Senders: the mailbox group or accounts you pick on the next screen</li>
              </ul>
              <p style={{ fontSize: 12, color: "var(--dark-200)", margin: "8px 0 4px" }}>
                Smartlead has no API for this one, so set it by hand in Smartlead after the push:
              </p>
              <ul style={{ fontSize: 12, paddingLeft: 18, margin: 0, color: "var(--dark-200)" }}>
                {defaults.smartlead.ui_only.map((u) => <li key={u}>{u}</li>)}
              </ul>
            </div>
          )}
          {hasHeyreach && (
            <div>
              <h5 style={{ marginBottom: 6 }}>HeyReach</h5>
              <p style={{ fontSize: 12, color: "var(--dark-200)", marginBottom: 6 }}>
                Created as a DRAFT. Connection requests carry no note. Waits are in hours (h) or days (d).
              </p>
              <pre style={{ fontSize: 12, background: "var(--blue-100)", padding: 10, borderRadius: 6, maxHeight: 320, overflow: "auto", margin: 0 }}>
                {(salesNav === "no" ? defaults.heyreach.sequence : defaults.heyreach.sequence_sales_nav).map((n) =>
                  `${"    ".repeat(n.depth)}${n.branch ? `[${n.branch}] ` : ""}${n.label}${n.wait ? ` (wait ${n.wait})` : ""}`).join("\n")}
              </pre>
            </div>
          )}
        </div>
      )}

      {!useDefault && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--blue-100)", paddingTop: 12 }}>
          {hasSmartlead && schedule && (
            <div style={{ marginBottom: hasHeyreach ? 14 : 0 }}>
              <h5 style={{ marginBottom: 8 }}>Smartlead schedule</h5>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 13, marginBottom: 8 }}>
                {DAYS.map((d, i) => (
                  <label key={d} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <input
                      type="checkbox" checked={schedule.days_of_the_week.includes(i + 1)}
                      onChange={() => setField("days_of_the_week",
                        schedule.days_of_the_week.includes(i + 1)
                          ? schedule.days_of_the_week.filter((x) => x !== i + 1)
                          : [...schedule.days_of_the_week, i + 1].sort())}
                    />
                    {d}
                  </label>
                ))}
              </div>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 13 }}>
                <label>Timezone<input type="text" value={schedule.timezone} onChange={(e) => setField("timezone", e.target.value)} /></label>
                <label>Start hour<input type="number" min={0} max={23} value={schedule.start_hour} onChange={(e) => setField("start_hour", Number(e.target.value))} /></label>
                <label>End hour<input type="number" min={1} max={24} value={schedule.end_hour} onChange={(e) => setField("end_hour", Number(e.target.value))} /></label>
                <label>Min between emails (min)<input type="number" min={1} value={schedule.min_time_btw_emails} onChange={(e) => setField("min_time_btw_emails", Number(e.target.value))} /></label>
                <label>New leads/day<input type="number" min={1} value={schedule.max_new_leads_per_day} onChange={(e) => setField("max_new_leads_per_day", Number(e.target.value))} /></label>
              </div>
            </div>
          )}
          {hasHeyreach && (
            <p style={{ fontSize: 13 }}>
              <span className="tag-warning">HeyReach</span> A custom workflow means no sequence is built automatically. The campaign
              is created as a DRAFT with the list, senders and schedule only, and you build the cadence in the HeyReach UI.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
