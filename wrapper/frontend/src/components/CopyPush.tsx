import { useEffect, useMemo, useState } from "react";
import type { CopyPushStatus, DefaultWorkflow, SalesNav, SenderAccount, SenderGroup, SmartleadSchedule } from "../lib/types";
import type { CopyPushContext } from "../lib/api";
import {
  confirmCopyPush, downloadCopyTemplate, getCopyPrompt, getCopyPushContext, getCopyPushDefaults, getHeyreachSenders,
  getSmartleadSenderGroups, getSmartleadSenders, startCopyPush,
} from "../lib/api";
import DefaultWorkflowPanel from "./DefaultWorkflowPanel";

const CHANNELS: { key: string; title: string; desc: string }[] = [
  { key: "smartlead", title: "Smartlead", desc: "Email sequence. Created paused, so nothing sends until you start it." },
  { key: "heyreach", title: "HeyReach", desc: "LinkedIn cadence. Created as a draft in your workspace." },
  { key: "interakt", title: "Interakt", desc: "WhatsApp template. Checked for approval, never auto-sent." },
];

const HEYREACH_SLOT_LABELS: Record<string, string> = {
  dm1_connected: "DM 1 (already connected)", dm1_not_connected: "DM 1 (after they accept)",
  dm2: "DM 2", dm3: "DM 3", dm4: "DM 4", inmail1: "InMail 1", inmail2: "InMail 2",
};

type StepKey = "platforms" | "workflow" | "copy" | "review";
const STEP_TITLES: Record<StepKey, string> = {
  platforms: "Platforms", workflow: "Workflow", copy: "Your copy", review: "Review & send",
};

// "P1_EVENTS_PREEVENT_US_EMAIL_Naitik12OCT26_98765432" - 7 underscore-separated parts
const nameLooksRight = (n: string) => n.trim().split("_").filter(Boolean).length >= 7;

const stripTags = (html: string) =>
  html.replace(/<\/p>\s*/gi, "\n").replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "").trim().split("\n");

export default function CopyPush({ sourceRunId, onDone }: { sourceRunId?: string; onDone: () => void }) {
  const [step, setStep] = useState<StepKey>("platforms");
  const [channels, setChannels] = useState<string[]>([]);
  const [campaignName, setCampaignName] = useState("");
  const [inputMode, setInputMode] = useState<"file" | "paste">("file");
  const [copyText, setCopyText] = useState("");
  const [copyFile, setCopyFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [salesNav, setSalesNav] = useState<SalesNav>("no");
  const [promptCopied, setPromptCopied] = useState(false);

  const [ctx, setCtx] = useState<CopyPushContext | null>(null);
  const [defaults, setDefaults] = useState<DefaultWorkflow | null>(null);
  const [defaultsError, setDefaultsError] = useState<string | null>(null);
  const [useDefault, setUseDefault] = useState<boolean | null>(null); // null until the user answers the prompt
  const [schedule, setSchedule] = useState<SmartleadSchedule | null>(null);

  const [push, setPush] = useState<CopyPushStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [hrSenders, setHrSenders] = useState<SenderAccount[] | null>(null);
  const [hrError, setHrError] = useState<string | null>(null);
  const [hrSearch, setHrSearch] = useState("");
  const [hrSelected, setHrSelected] = useState<number[]>([]);

  const [slGroups, setSlGroups] = useState<SenderGroup[] | null>(null);
  const [slGroupsError, setSlGroupsError] = useState<string | null>(null);
  const [slSuggested, setSlSuggested] = useState<number | null>(null);
  const [slMode, setSlMode] = useState<"group" | "individual">("group");
  const [slTag, setSlTag] = useState<number | null>(null);
  const [slAccounts, setSlAccounts] = useState<SenderAccount[] | null>(null);
  const [slAccountsError, setSlAccountsError] = useState<string | null>(null);
  const [slSearch, setSlSearch] = useState("");
  const [slSelected, setSlSelected] = useState<number[]>([]);

  const hasWorkflow = channels.includes("smartlead") || channels.includes("heyreach");
  const steps: StepKey[] = useMemo(
    () => ["platforms", ...(hasWorkflow ? ["workflow" as StepKey] : []), "copy", "review"], [hasWorkflow]);
  const stepIdx = steps.indexOf(step);

  useEffect(() => {
    getCopyPushContext().then(setCtx).catch(() => setCtx(null));
    getCopyPushDefaults()
      .then((d) => { setDefaults(d); setSchedule(d.smartlead.schedule); })
      .catch((e) => setDefaultsError(e.message || "Could not load the default workflow"));
  }, []);

  // Senders load only once the copy has parsed - no point before that.
  useEffect(() => {
    if (step !== "review" || !push) return;
    if (channels.includes("heyreach") && hrSenders === null) {
      getHeyreachSenders().then(({ status, items, message }) => {
        setHrSenders(items);
        setHrError(status !== "ok" ? message || `Could not load senders (${status})` : null);
      });
    }
    if (channels.includes("smartlead") && slGroups === null) {
      getSmartleadSenderGroups().then(({ status, items, suggestedTagId, message }) => {
        setSlGroups(items);
        setSlSuggested(suggestedTagId);
        if (suggestedTagId) setSlTag((t) => t ?? suggestedTagId);
        setSlGroupsError(status !== "ok" ? message || `Could not load mailbox groups (${status})` : null);
      });
    }
  }, [step, push, channels, hrSenders, slGroups]);

  useEffect(() => {
    if (slMode !== "individual" || slAccounts !== null) return;
    getSmartleadSenders().then(({ status, items, message }) => {
      setSlAccounts(items);
      setSlAccountsError(status !== "ok" ? message || `Could not load senders (${status})` : null);
    });
  }, [slMode, slAccounts]);

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  function validate(from: StepKey): string | null {
    if (from === "platforms") {
      if (!channels.length) return "Pick at least one platform.";
      if (!campaignName.trim()) return "Give the campaign a name.";
    }
    if (from === "workflow" && useDefault === null) return "Choose whether to use the default workflow.";
    if (from === "copy") {
      if (inputMode === "file" && !copyFile) return "Upload your copy file, or switch to pasting it.";
      if (inputMode === "paste" && !copyText.trim()) return "Paste your copy, or switch to uploading a file.";
    }
    return null;
  }

  async function next() {
    setError(null);
    const problem = validate(step);
    if (problem) { setError(problem); return; }
    const following = steps[stepIdx + 1];
    if (following !== "review") { setStep(following); return; }
    setBusy(true);
    try {
      setPush(await startCopyPush({
        channels, campaignName, sourceRunId, salesNav: channels.includes("heyreach") && useDefault ? salesNav : "no",
        copyText: inputMode === "paste" ? copyText : undefined,
        copyFile: inputMode === "file" ? copyFile ?? undefined : undefined,
      }));
      setStep("review");
    } catch (e: any) {
      setError(e.message || "Could not read your copy");
    } finally {
      setBusy(false);
    }
  }

  function back() {
    setError(null);
    if (step === "review") setPush(null); // re-parse on the way forward so edits to the copy are picked up
    if (stepIdx > 0) setStep(steps[stepIdx - 1]);
  }

  const effectiveNav: SalesNav = channels.includes("heyreach") && useDefault ? salesNav : "no";

  async function copyPrompt() {
    setError(null);
    try {
      await navigator.clipboard.writeText(await getCopyPrompt(channels, effectiveNav));
      setPromptCopied(true);
      setTimeout(() => setPromptCopied(false), 2500);
    } catch (e: any) {
      setError(e.message || "Could not copy the prompt");
    }
  }

  const parsedOk = (ch: string) => push?.mapped[ch]?.status === "done";
  const anyParsed = channels.some(parsedOk);
  const needsHrSender = channels.includes("heyreach") && parsedOk("heyreach") && hrSelected.length === 0;

  const emailCount = push?.mapped.smartlead?.mapped?.sequences?.length ?? 0;
  const dmCount = push?.mapped.heyreach?.mapped
    ? ["dm2", "dm3", "dm4"].filter((k) => push.mapped.heyreach.mapped[k]).length + 1
    : 0;
  const defaultEmails = defaults?.smartlead.cadence_days.length ?? 5;
  const shorter = [
    emailCount && emailCount < defaultEmails ? `${emailCount} emails (the default is ${defaultEmails})` : "",
    dmCount && dmCount < 4 ? `${dmCount} DM${dmCount > 1 ? "s" : ""} (the default is 4)` : "",
  ].filter(Boolean);
  const workflowNote = useDefault === false
    ? "Your own schedule and settings are used, and HeyReach gets no automatic sequence."
    : shorter.length
      ? `Your copy has ${shorter.join(" and ")}, so each cadence simply ends after your last message. Everything else follows the default.`
      : "Your copy fills the whole default cadence.";

  async function doConfirm() {
    if (!push) return;
    setError(null);
    setBusy(true);
    try {
      setPush(await confirmCopyPush(push.push_id, {
        heyreachSenderIds: channels.includes("heyreach") ? hrSelected : undefined,
        smartleadSenderTagId: channels.includes("smartlead") && slMode === "group" ? slTag ?? undefined : undefined,
        smartleadSenderAccountIds: channels.includes("smartlead") && slMode === "individual" ? slSelected : undefined,
        useDefaultWorkflow: useDefault !== false,
        smartleadSchedule: useDefault === false && channels.includes("smartlead") && schedule ? schedule : undefined,
      }));
    } catch (e: any) {
      setError(e.message || "Push failed");
    } finally {
      setBusy(false);
    }
  }

  if (push?.stage === "done") return <Result push={push} onDone={onDone} />;

  return (
    <div className="cp-wrap">
      <h1 style={{ marginBottom: 4 }}>Push copy</h1>
      <p style={{ marginBottom: 20 }}>
        Your list and copy are ready. This sends the copy into campaigns, with no contact data involved.
        {sourceRunId && <> Continuing from run <code>{sourceRunId}</code>, whose HeyReach list will be reused.</>}
      </p>

      {ctx && (
        <div className="cp-chips">
          <span className="cp-chip">Signed in as {ctx.user}</span>
          <span className="cp-chip">HeyReach workspace: {ctx.workspace_label}</span>
          <span className="cp-chip">Region: {ctx.region}</span>
        </div>
      )}

      <ol className="cp-steps">
        {steps.map((k, i) => (
          <li key={k} className={`cp-step ${i < stepIdx ? "done" : i === stepIdx ? "active" : ""}`}>
            <span className="n">{i < stepIdx ? "✓" : i + 1}</span>
            <span className="t">{STEP_TITLES[k]}</span>
            {i < steps.length - 1 && <span className="bar" />}
          </li>
        ))}
      </ol>

      {step === "platforms" && (
        <>
          <h3 style={{ marginBottom: 10 }}>Where should this go?</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
            {CHANNELS.map((c) => {
              const on = channels.includes(c.key);
              return (
                <button key={c.key} type="button" className={`cp-opt ${on ? "on" : ""}`} onClick={() => setChannels((cs) => toggle(cs, c.key))}>
                  <span className="check">{on ? "✓" : ""}</span>
                  <div>
                    <b>{c.title}</b>
                    <span className="d">{c.desc}</span>
                    {c.key === "interakt" && ctx && !ctx.whatsapp_eligible && (
                      <span className="d" style={{ display: "block", color: "var(--orange-300)", marginTop: 2 }}>
                        WhatsApp is normally for India, Philippines and Indonesia. Your region is {ctx.region}, so you'll get a heads-up before pushing.
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          <h3 style={{ marginBottom: 6 }}>Campaign name</h3>
          <input
            type="text" value={campaignName} onChange={(e) => setCampaignName(e.target.value)}
            placeholder="P1_EVENTS_PREEVENT_US_EMAIL_Naitik12OCT26_98765432"
          />
          <p style={{ fontSize: 12, marginTop: 6, color: campaignName && !nameLooksRight(campaignName) ? "var(--orange-300)" : "var(--dark-200)" }}>
            {campaignName && !nameLooksRight(campaignName)
              ? "This doesn't look like the standard name yet. Expected: PRIORITY_TEAM_USECASE_REGION_CHANNEL_POCNAME+DATE_PROJECTID."
              : "Format: PRIORITY_TEAM_USECASE_REGION_CHANNEL_POCNAME+DATE_PROJECTID"}
          </p>
        </>
      )}

      {step === "copy" && (
        <>
          <h3 style={{ marginBottom: 6 }}>Add your copy</h3>
          <div className="card" style={{ padding: 16, marginBottom: 14 }}>
            <b style={{ fontSize: 14 }}>Use our layout</b>
            <p style={{ fontSize: 13, margin: "2px 0 10px" }}>
              Files that follow the template upload with no changes. Other layouts will not be read. Leave the signature off: no sign-off or name at the end of any message, the platform adds the sender's own.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn-secondary" onClick={() => downloadCopyTemplate(channels, "xlsx", effectiveNav).catch((e) => setError(e.message))}>Excel template</button>
              <button className="btn-secondary" onClick={() => downloadCopyTemplate(channels, "txt", effectiveNav).catch((e) => setError(e.message))}>Text template</button>
            </div>
          </div>
          <div className="card" style={{ padding: 16, marginBottom: 20 }}>
            <b style={{ fontSize: 14 }}>Don't have copy yet?</b>
            <p style={{ fontSize: 13, margin: "2px 0 10px" }}>
              Copy this brief into Claude. It has your workflow, the rules and the exact output layout, so what it writes uploads straight back here.
            </p>
            <button className="btn-secondary" onClick={copyPrompt}>{promptCopied ? "Copied" : "Copy the prompt for Claude"}</button>
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button className={inputMode === "file" ? "pill pill-selected" : "pill"} onClick={() => setInputMode("file")}>Upload a file</button>
            <button className={inputMode === "paste" ? "pill pill-selected" : "pill"} onClick={() => setInputMode("paste")}>Paste text</button>
          </div>

          {inputMode === "file" ? (
            <label
              className={`cp-drop ${dragOver ? "over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); setCopyFile(e.dataTransfer.files?.[0] ?? null); }}
              style={{ display: "block" }}
            >
              <input type="file" accept=".xlsx,.xls,.docx,.txt" style={{ display: "none" }} onChange={(e) => setCopyFile(e.target.files?.[0] ?? null)} />
              {copyFile ? (
                <><b>{copyFile.name}</b><p style={{ fontSize: 12, margin: "4px 0 0" }}>{(copyFile.size / 1024).toFixed(0)} KB. Click to choose a different file.</p></>
              ) : (
                <><b>Drop your file here, or click to browse</b><p style={{ fontSize: 12, margin: "4px 0 0" }}>.xlsx, .docx or .txt</p></>
              )}
            </label>
          ) : (
            <textarea
              rows={14} value={copyText} onChange={(e) => setCopyText(e.target.value)} style={{ width: "100%", fontFamily: "monospace", fontSize: 13 }}
              placeholder={"[SMARTLEAD]\nDay 0:\nSubject: ...\nBody:\n...\n\n[HEYREACH]\nDM1 (connected):\nMessage: ...\n\n[INTERAKT]\nName: ...\nBody: ...\nVariables: ..."}
            />
          )}
          {channels.length > 1 && (
            <p style={{ fontSize: 12, marginTop: 8 }}>
              One file for several platforms: use one sheet per platform in Excel, or a [SMARTLEAD] / [HEYREACH] / [INTERAKT] heading before each block in text.
            </p>
          )}
        </>
      )}

      {step === "workflow" && (
        <>
          <h3 style={{ marginBottom: 6 }}>How should it run?</h3>
          <DefaultWorkflowPanel
            channels={channels} defaults={defaults} loadError={defaultsError}
            useDefault={useDefault} onUseDefault={setUseDefault} schedule={schedule} onSchedule={setSchedule}
            salesNav={salesNav} onSalesNav={setSalesNav}
          />
        </>
      )}

      {step === "review" && push && (
        <>
          <h3 style={{ marginBottom: 4 }}>Review before anything is sent</h3>
          <p style={{ marginBottom: 16, fontSize: 13 }}>
            Campaign <b>{campaignName}</b>. {useDefault === false ? "Custom workflow." : "Default workflow."} Nothing reaches a platform until you press the button at the bottom.
          </p>

          {hasWorkflow && (
            <div className="card" style={{ padding: 12, fontSize: 13, marginBottom: 12, display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
              <span>
                <b>{useDefault === false ? "Custom workflow" : "Default workflow"}.</b> {workflowNote}
              </span>
              <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 10px", whiteSpace: "nowrap" }}
                onClick={() => { setPush(null); setStep("workflow"); }}>Change</button>
            </div>
          )}

          {push.warnings.map((w, i) => (
            <p key={i} className="card" style={{ padding: 12, fontSize: 13, marginBottom: 10 }}><span className="tag-warning">Heads up</span> {w}</p>
          ))}

          {channels.map((ch) => (
            <div key={ch} className="card" style={{ padding: 16, marginBottom: 14 }}>
              <h4 style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center" }}>
                {CHANNELS.find((c) => c.key === ch)?.title}
                {parsedOk(ch) ? <span className="tag-success">Copy read</span> : <span className="tag-error">Can't push yet</span>}
              </h4>
              {parsedOk(ch) ? <CopyPreview channel={ch} mapped={push.mapped[ch].mapped} /> : (
                <p style={{ fontSize: 13, color: "var(--red-300)" }}>
                  {push.mapped[ch]?.message || "Could not read the copy for this platform."} Go back, fix the file, and try again. The template shows the expected layout.
                </p>
              )}

              {ch === "heyreach" && parsedOk(ch) && (
                <div style={{ marginTop: 14 }}>
                  <h5 style={{ marginBottom: 4 }}>LinkedIn senders{ctx ? ` in ${ctx.workspace_label}` : ""}</h5>
                  <p style={{ fontSize: 12, marginBottom: 8 }}>Pick who sends. HeyReach needs at least one account.</p>
                  <input type="text" placeholder="Search by name or email" value={hrSearch} onChange={(e) => setHrSearch(e.target.value)} style={{ marginBottom: 8 }} />
                  <div className="cp-list">
                    {(hrSenders ?? [])
                      .filter((a) => !hrSearch || `${a.name} ${a.email}`.toLowerCase().includes(hrSearch.toLowerCase()))
                      .map((a) => (
                        <label key={a.id} style={{ opacity: a.active === false ? 0.5 : 1 }}>
                          <input type="checkbox" checked={hrSelected.includes(a.id)} onChange={() => setHrSelected(toggle(hrSelected, a.id))} />
                          {a.name} <span style={{ color: "var(--dark-200)" }}>{a.email}{a.active === false ? " (inactive)" : ""}</span>
                        </label>
                      ))}
                    {hrSenders === null && <p style={{ fontSize: 13, margin: 4 }}>Loading accounts...</p>}
                    {hrSenders?.length === 0 && !hrError && <p style={{ fontSize: 13, margin: 4 }}>No accounts found in this workspace.</p>}
                  </div>
                  {hrError && <p style={{ fontSize: 13, marginTop: 8 }}><span className="tag-warning">Couldn't load</span> {hrError}{" "}
                    <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => { setHrError(null); setHrSenders(null); }}>Retry</button></p>}
                  <p style={{ fontSize: 12, marginTop: 6 }}>{hrSelected.length} selected</p>
                </div>
              )}

              {ch === "smartlead" && parsedOk(ch) && (
                <div style={{ marginTop: 14 }}>
                  <h5 style={{ marginBottom: 8 }}>Email senders</h5>
                  <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                    <button className={slMode === "group" ? "pill pill-selected" : "pill"} onClick={() => setSlMode("group")}>Mailbox group</button>
                    <button className={slMode === "individual" ? "pill pill-selected" : "pill"} onClick={() => setSlMode("individual")}>Pick accounts</button>
                  </div>
                  {slMode === "group" ? (
                    <>
                      <select value={slTag ?? ""} onChange={(e) => setSlTag(e.target.value ? Number(e.target.value) : null)}>
                        <option value="">No senders yet, I'll attach them later</option>
                        {(slGroups ?? []).map((g) => (
                          <option key={g.id} value={g.id}>{g.name}{g.id === slSuggested ? " (suggested for your region)" : ""}</option>
                        ))}
                      </select>
                      {slGroupsError && <p style={{ fontSize: 13, marginTop: 8 }}><span className="tag-warning">Couldn't load</span> {slGroupsError}{" "}
                        <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => { setSlGroupsError(null); setSlGroups(null); }}>Retry</button></p>}
                    </>
                  ) : (
                    <>
                      <input type="text" placeholder="Search by name or email" value={slSearch} onChange={(e) => setSlSearch(e.target.value)} style={{ marginBottom: 8 }} />
                      <div className="cp-list">
                        {(slAccounts ?? [])
                          .filter((a) => !slSearch || `${a.name} ${a.email}`.toLowerCase().includes(slSearch.toLowerCase()))
                          .map((a) => (
                            <label key={a.id}>
                              <input type="checkbox" checked={slSelected.includes(a.id)} onChange={() => setSlSelected(toggle(slSelected, a.id))} />
                              {a.name} <span style={{ color: "var(--dark-200)" }}>{a.email}</span>
                            </label>
                          ))}
                        {slAccounts === null && <p style={{ fontSize: 13, margin: 4 }}>Loading accounts...</p>}
                      </div>
                      {slAccountsError && <p style={{ fontSize: 13, marginTop: 8 }}><span className="tag-warning">Couldn't load</span> {slAccountsError}</p>}
                      <p style={{ fontSize: 12, marginTop: 6 }}>{slSelected.length} selected</p>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </>
      )}

      {error && <p style={{ color: "var(--red-300)", marginTop: 16, fontSize: 14 }}>{error}</p>}

      <div className="cp-actions">
        <button className="btn-secondary" onClick={stepIdx === 0 ? onDone : back} disabled={busy}>{stepIdx === 0 ? "Cancel" : "Back"}</button>
        {step === "review" ? (
          <div style={{ textAlign: "right" }}>
            {needsHrSender && <p style={{ fontSize: 12, margin: "0 0 6px", color: "var(--orange-300)" }}>Select at least one LinkedIn sender to continue.</p>}
            <button className="btn-danger-confirm" disabled={busy || !anyParsed || needsHrSender} onClick={doConfirm}>
              {busy ? "Pushing..." : "Create campaigns (paused / draft)"}
            </button>
          </div>
        ) : (
          <button className="btn-primary" disabled={busy} onClick={next}>
            {busy ? "Reading your copy..." : steps[stepIdx + 1] === "review" ? "Read my copy & review" : "Continue"}
          </button>
        )}
      </div>
    </div>
  );
}

function CopyPreview({ channel, mapped }: { channel: string; mapped: any }) {
  if (channel === "smartlead") {
    return (
      <div>
        {(mapped.sequences ?? []).map((s: any) => {
          const v = s.seq_variants?.[0] ?? {};
          return (
            <div key={s.seq_number} className="cp-mail">
              <div className="meta">Email {s.seq_number} · day {s.seq_delay_details?.delay_in_days}</div>
              <div className="subj">{v.subject || "(no subject)"}</div>
              {stripTags(v.email_body || "").map((l, i) => <p key={i}>{l}</p>)}
            </div>
          );
        })}
      </div>
    );
  }
  if (channel === "heyreach") {
    return (
      <div>
        {Object.entries(HEYREACH_SLOT_LABELS).filter(([slot]) => mapped[slot]).map(([slot, label]) => (
          <div key={slot} className="cp-mail">
            <div className="meta">{label}</div>
            {mapped[slot]?.subject && <div className="subj">{mapped[slot].subject}</div>}
            <div style={{ whiteSpace: "pre-wrap" }}>{mapped[slot]?.message}</div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="cp-mail">
      <div className="meta">Template: {mapped.name}</div>
      <div style={{ whiteSpace: "pre-wrap" }}>{mapped.body}</div>
      {mapped.variables?.length > 0 && <p style={{ fontSize: 12, marginTop: 6 }}>Variables: {mapped.variables.join(", ")}</p>}
    </div>
  );
}

function Result({ push, onDone }: { push: CopyPushStatus; onDone: () => void }) {
  const label = (s: string) => ({ pushed: "Created", approved: "Approved", pending_approval: "Awaiting approval" } as Record<string, string>)[s] ?? s.replace(/_/g, " ");
  return (
    <div className="cp-wrap">
      <h1 style={{ marginBottom: 4 }}>Done</h1>
      <p style={{ marginBottom: 20 }}>Here is what happened on each platform. Nothing has started sending.</p>
      {push.channels.map((ch) => {
        const r = push.result[ch] || {};
        const ok = r.status === "pushed" || r.status === "approved";
        return (
          <div key={ch} className="card" style={{ padding: 16, marginBottom: 14 }}>
            <h4 style={{ marginBottom: 6, display: "flex", gap: 8, alignItems: "center", textTransform: "capitalize" }}>
              {ch} <span className={ok ? "tag-success" : "tag-warning"}>{label(r.status || "skipped")}</span>
            </h4>
            {r.campaign_id && <p style={{ fontSize: 13 }}>Campaign ID <code>{r.campaign_id}</code></p>}
            {r.note && <p style={{ fontSize: 13, marginTop: 4 }}>{r.note}</p>}
            {r.message && <p style={{ fontSize: 13, marginTop: 4 }}>{r.message}</p>}
            {(r.extras ?? []).some((e: string) => e.includes("FAILED")) && (
              <p style={{ fontSize: 13, marginTop: 4, color: "var(--orange-300)" }}>Some settings could not be applied automatically. Set them by hand in Smartlead.</p>
            )}
          </div>
        );
      })}
      <div className="cp-actions"><span /><button className="btn-primary" onClick={onDone}>Back to start</button></div>
    </div>
  );
}
