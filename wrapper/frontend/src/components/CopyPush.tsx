import { useEffect, useState } from "react";
import type { CopyPushStatus, SenderAccount, SenderGroup } from "../lib/types";
import {
  confirmCopyPush, getHeyreachSenders, getSmartleadSenderGroups, getSmartleadSenders, startCopyPush,
} from "../lib/api";
import Tooltip from "./Tooltip";

const CHANNEL_OPTIONS: { key: string; label: string }[] = [
  { key: "smartlead", label: "Smartlead (Email)" },
  { key: "heyreach", label: "HeyReach (LinkedIn)" },
  { key: "interakt", label: "Interakt (WhatsApp)" },
];

const REGIONS = ["IND", "IDN", "PHL", "KSA", "GCC", "AFR", "US", "UKEU", "GLOBAL"];

export default function CopyPush({ sourceRunId, onDone }: { sourceRunId?: string; onDone: () => void }) {
  const [channels, setChannels] = useState<string[]>([]);
  const [campaignName, setCampaignName] = useState("");
  const [region, setRegion] = useState("");
  const [isCxo, setIsCxo] = useState(false);
  const [inputMode, setInputMode] = useState<"paste" | "file">("paste");
  const [copyText, setCopyText] = useState("");
  const [copyFile, setCopyFile] = useState<File | null>(null);

  const [push, setPush] = useState<CopyPushStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [heyreachSenders, setHeyreachSenders] = useState<SenderAccount[] | null>(null);
  const [heyreachSendersError, setHeyreachSendersError] = useState<string | null>(null);
  const [heyreachSearch, setHeyreachSearch] = useState("");
  const [selectedHeyreachIds, setSelectedHeyreachIds] = useState<number[]>([]);

  const [smartleadGroups, setSmartleadGroups] = useState<SenderGroup[] | null>(null);
  const [smartleadGroupsError, setSmartleadGroupsError] = useState<string | null>(null);
  const [smartleadSuggestedTagId, setSmartleadSuggestedTagId] = useState<number | null>(null);
  const [smartleadSenderMode, setSmartleadSenderMode] = useState<"group" | "individual">("group");
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [smartleadSenders, setSmartleadSenders] = useState<SenderAccount[] | null>(null);
  const [smartleadSendersError, setSmartleadSendersError] = useState<string | null>(null);
  const [smartleadSearch, setSmartleadSearch] = useState("");
  const [selectedSmartleadIds, setSelectedSmartleadIds] = useState<number[]>([]);

  function toggleChannel(key: string) {
    setChannels((cs) => (cs.includes(key) ? cs.filter((c) => c !== key) : [...cs, key]));
  }

  // Fetch sender data once the review stage is reached - no point loading it
  // before we know the copy actually parsed and these channels are relevant.
  useEffect(() => {
    if (push?.stage !== "awaiting_review") return;
    if (channels.includes("heyreach") && heyreachSenders === null) {
      getHeyreachSenders().then(({ status, items, message }) => {
        setHeyreachSenders(items);
        if (status !== "ok") setHeyreachSendersError(message || `Could not load senders (${status})`);
      });
    }
    if (channels.includes("smartlead") && smartleadGroups === null) {
      getSmartleadSenderGroups(region).then(({ status, items, suggestedTagId, message }) => {
        setSmartleadGroups(items);
        setSmartleadSuggestedTagId(suggestedTagId);
        if (suggestedTagId) setSelectedTagId(suggestedTagId);
        if (status !== "ok") setSmartleadGroupsError(message || `Could not load mailbox groups (${status})`);
      });
    }
    // Re-fires when a Retry button resets heyreachSenders/smartleadGroups to
    // null, not just when the stage first changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [push?.stage, heyreachSenders, smartleadGroups]);

  useEffect(() => {
    if (smartleadSenderMode !== "individual" || smartleadSenders !== null) return;
    getSmartleadSenders(smartleadSearch || undefined).then(({ status, items, message }) => {
      setSmartleadSenders(items);
      if (status !== "ok") setSmartleadSendersError(message || `Could not load senders (${status})`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smartleadSenderMode]);

  async function doStart() {
    setError(null);
    if (!channels.length) { setError("Pick at least one channel"); return; }
    if (!campaignName.trim()) { setError("Campaign name is required"); return; }
    if (inputMode === "paste" && !copyText.trim()) { setError("Paste your copy, or switch to file upload"); return; }
    if (inputMode === "file" && !copyFile) { setError("Choose a file to upload"); return; }

    setStarting(true);
    try {
      const status = await startCopyPush({
        channels, campaignName, region: region || undefined, isCxo,
        sourceRunId,
        copyText: inputMode === "paste" ? copyText : undefined,
        copyFile: inputMode === "file" ? copyFile ?? undefined : undefined,
      });
      setPush(status);
    } catch (e: any) {
      setError(e.message || "Failed to start copy push");
    } finally {
      setStarting(false);
    }
  }

  async function doConfirm() {
    if (!push) return;
    setError(null);
    setConfirming(true);
    try {
      const status = await confirmCopyPush(push.push_id, {
        heyreachSenderIds: channels.includes("heyreach") ? selectedHeyreachIds : undefined,
        smartleadSenderTagId: channels.includes("smartlead") && smartleadSenderMode === "group" ? selectedTagId ?? undefined : undefined,
        smartleadSenderAccountIds: channels.includes("smartlead") && smartleadSenderMode === "individual" ? selectedSmartleadIds : undefined,
      });
      setPush(status);
    } catch (e: any) {
      setError(e.message || "Push failed");
    } finally {
      setConfirming(false);
    }
  }

  if (push?.stage === "done") {
    return <CopyPushResult push={push} onDone={onDone} />;
  }

  if (push?.stage === "awaiting_review") {
    return (
      <div>
        <h2 style={{ marginBottom: 6 }}>Review before pushing</h2>
        <p style={{ marginBottom: 20 }}>Nothing is sent to any platform until you confirm below.</p>

        {push.warnings.length > 0 && (
          <div className="card" style={{ padding: 16, marginBottom: 20 }}>
            <h5 style={{ marginBottom: 8 }}>Heads up</h5>
            {push.warnings.map((w, i) => (
              <p key={i} style={{ fontSize: 13, marginTop: i ? 8 : 0 }}><span className="tag-warning">Note</span> {w}</p>
            ))}
          </div>
        )}

        {channels.map((ch) => {
          const entry = push.mapped[ch];
          return (
            <div key={ch} className="card" style={{ padding: 16, marginBottom: 16 }}>
              <h5 style={{ marginBottom: 8, textTransform: "capitalize" }}>{ch}</h5>
              {entry?.status === "done" ? (
                <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", maxHeight: 240, overflowY: "auto", background: "var(--blue-100)", padding: 10, borderRadius: 6 }}>
                  {JSON.stringify(entry.mapped, null, 2)}
                </pre>
              ) : (
                <p style={{ fontSize: 13, color: "var(--red-300)" }}>
                  <span className="tag-error">Not ready</span> {entry?.message || "Could not parse copy for this channel."}
                </p>
              )}
            </div>
          );
        })}

        {channels.includes("heyreach") && (
          <div className="card" style={{ padding: 16, marginBottom: 16 }}>
            <h5 style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
              HeyReach senders
              <Tooltip text="Required by HeyReach's API to create a campaign - pick at least one LinkedIn account to send from." />
            </h5>
            <input
              type="text" placeholder="Search by name or email..." value={heyreachSearch}
              onChange={(e) => setHeyreachSearch(e.target.value)}
              style={{ marginBottom: 10 }}
            />
            <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
              {(heyreachSenders ?? [])
                .filter((a) => !heyreachSearch || `${a.name} ${a.email}`.toLowerCase().includes(heyreachSearch.toLowerCase()))
                .map((a) => (
                  <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, opacity: a.active === false ? 0.5 : 1 }}>
                    <input
                      type="checkbox" checked={selectedHeyreachIds.includes(a.id)}
                      onChange={() => setSelectedHeyreachIds((ids) => ids.includes(a.id) ? ids.filter((i) => i !== a.id) : [...ids, a.id])}
                    />
                    {a.name} ({a.email}){a.active === false ? " - inactive" : ""}
                  </label>
                ))}
              {heyreachSenders === null && <p style={{ fontSize: 13, color: "var(--dark-200)" }}>Loading accounts...</p>}
              {heyreachSenders?.length === 0 && !heyreachSendersError && <p style={{ fontSize: 13, color: "var(--dark-200)" }}>No accounts found.</p>}
            </div>
            {heyreachSendersError && (
              <p style={{ fontSize: 13, marginTop: 8 }}>
                <span className="tag-warning">Couldn't load</span> {heyreachSendersError}{" "}
                <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 8px" }}
                  onClick={() => { setHeyreachSendersError(null); setHeyreachSenders(null); }}>Retry</button>
              </p>
            )}
          </div>
        )}

        {channels.includes("smartlead") && (
          <div className="card" style={{ padding: 16, marginBottom: 16 }}>
            <h5 style={{ marginBottom: 8 }}>Smartlead senders</h5>
            <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 13 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="radio" checked={smartleadSenderMode === "group"} onChange={() => setSmartleadSenderMode("group")} />
                Mailbox group
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="radio" checked={smartleadSenderMode === "individual"} onChange={() => setSmartleadSenderMode("individual")} />
                Search individually
              </label>
            </div>

            {smartleadSenderMode === "group" ? (
              <>
                <select value={selectedTagId ?? ""} onChange={(e) => setSelectedTagId(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">No group - attach senders later</option>
                  {(smartleadGroups ?? []).map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}{g.id === smartleadSuggestedTagId ? " (suggested for this region)" : ""}
                    </option>
                  ))}
                </select>
                {smartleadGroupsError && (
                  <p style={{ fontSize: 13, marginTop: 8 }}>
                    <span className="tag-warning">Couldn't load</span> {smartleadGroupsError}{" "}
                    <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 8px" }}
                      onClick={() => { setSmartleadGroupsError(null); setSmartleadGroups(null); }}>Retry</button>
                  </p>
                )}
              </>
            ) : (
              <>
                <input
                  type="text" placeholder="Search by name or email..." value={smartleadSearch}
                  onChange={(e) => setSmartleadSearch(e.target.value)}
                  onBlur={() => getSmartleadSenders(smartleadSearch || undefined).then(({ status, items, message }) => {
                    setSmartleadSenders(items);
                    setSmartleadSendersError(status !== "ok" ? (message || `Could not load senders (${status})`) : null);
                  })}
                  style={{ marginBottom: 10 }}
                />
                <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                  {(smartleadSenders ?? []).map((a) => (
                    <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                      <input
                        type="checkbox" checked={selectedSmartleadIds.includes(a.id)}
                        onChange={() => setSelectedSmartleadIds((ids) => ids.includes(a.id) ? ids.filter((i) => i !== a.id) : [...ids, a.id])}
                      />
                      {a.name} ({a.email})
                    </label>
                  ))}
                  {smartleadSenders === null && <p style={{ fontSize: 13, color: "var(--dark-200)" }}>Loading accounts...</p>}
                </div>
                {smartleadSendersError && (
                  <p style={{ fontSize: 13, marginTop: 8 }}>
                    <span className="tag-warning">Couldn't load</span> {smartleadSendersError}{" "}
                    <button className="btn-secondary" style={{ fontSize: 12, padding: "2px 8px" }}
                      onClick={() => { setSmartleadSendersError(null); setSmartleadSenders(null); }}>Retry</button>
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {error && <p style={{ color: "var(--red-300)", marginTop: 8 }}>{error}</p>}
        <button className="btn-danger-confirm" style={{ marginTop: 12 }} disabled={confirming} onClick={doConfirm}>
          {confirming ? "Pushing..." : "Confirm & push"}
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Push copy</h2>
      <p style={{ marginBottom: 20 }}>
        Push already-written copy - email, LinkedIn, or WhatsApp - into a campaign. No contact or lead data in this flow.
        {sourceRunId && <> Chained from run <code>{sourceRunId}</code> - the HeyReach list from that run will be reused.</>}
      </p>

      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        <h5 style={{ marginBottom: 10 }}>Which platform(s)?</h5>
        <div style={{ display: "flex", gap: 20 }}>
          {CHANNEL_OPTIONS.map((c) => (
            <label key={c.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
              <input type="checkbox" checked={channels.includes(c.key)} onChange={() => toggleChannel(c.key)} />
              {c.label}
            </label>
          ))}
        </div>
      </div>

      <label style={{ display: "block", marginBottom: 12 }}>
        <div style={{ marginBottom: 6, fontWeight: 600 }}>Campaign name</div>
        <input type="text" value={campaignName} onChange={(e) => setCampaignName(e.target.value)} placeholder="e.g. P1_EVENTS_PREEVENT_US_EMAIL_Naitik12OCT26" />
      </label>

      <div style={{ display: "flex", gap: 24, marginBottom: 12 }}>
        <label style={{ flex: 1 }}>
          <div style={{ marginBottom: 6, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
            Region
            <Tooltip text="India/Philippines/Indonesia are the standing-rule WhatsApp-eligible regions - selecting Interakt outside those shows a warning before you can push." />
          </div>
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">Select...</option>
            {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        {channels.includes("heyreach") && (
          <label style={{ flex: 1, display: "flex", alignItems: "flex-end", paddingBottom: 8 }}>
            <input type="checkbox" checked={isCxo} onChange={(e) => setIsCxo(e.target.checked)} style={{ marginRight: 8 }} />
            CXO/exec-targeted LinkedIn campaign
          </label>
        )}
      </div>

      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        <h5 style={{ marginBottom: 10 }}>Your copy</h5>
        <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 13 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input type="radio" checked={inputMode === "paste"} onChange={() => setInputMode("paste")} />
            Paste text
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input type="radio" checked={inputMode === "file"} onChange={() => setInputMode("file")} />
            Upload a file (.xlsx / .docx / .txt)
          </label>
        </div>
        {inputMode === "paste" ? (
          <textarea
            rows={12} value={copyText} onChange={(e) => setCopyText(e.target.value)}
            placeholder={"[SMARTLEAD]\nDay 0:\nSubject: ...\nBody: ...\n\n[HEYREACH]\nDM1 (connected):\nMessage: ...\nFallback: ...\n\n[INTERAKT]\nName: ...\nBody: ...\nVariables: ..."}
            style={{ width: "100%", fontFamily: "monospace", fontSize: 13 }}
          />
        ) : (
          <input type="file" accept=".xlsx,.xls,.docx,.txt" onChange={(e) => setCopyFile(e.target.files?.[0] || null)} />
        )}
        <p style={{ fontSize: 12, color: "var(--dark-200)", marginTop: 8 }}>
          Multiple channels in one file: an .xlsx needs one sheet per channel (named smartlead/heyreach/interakt); pasted
          text or a .docx/.txt needs a [CHANNEL] header before each channel's copy. A single channel doesn't need either.
        </p>
      </div>

      {error && <p style={{ color: "var(--red-300)", marginTop: 8 }}>{error}</p>}
      <button className="btn-primary" style={{ marginTop: 12 }} disabled={starting} onClick={doStart}>
        {starting ? "Parsing..." : "Parse copy & review"}
      </button>
    </div>
  );
}

function CopyPushResult({ push, onDone }: { push: CopyPushStatus; onDone: () => void }) {
  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Push attempted</h2>
      <p style={{ marginBottom: 20 }}>{push.message}</p>
      {push.channels.map((ch) => {
        const r = push.result[ch] || {};
        const ok = r.status === "pushed";
        return (
          <div key={ch} className="card" style={{ padding: 16, marginBottom: 16 }}>
            <h5 style={{ marginBottom: 8, textTransform: "capitalize", display: "flex", alignItems: "center", gap: 8 }}>
              {ch}
              <span className={ok ? "tag-success" : r.status === "approved" || r.status === "pending_approval" ? "tag-warning" : "tag-warning"}>
                {r.status}
              </span>
            </h5>
            {r.campaign_id && <p style={{ fontSize: 13 }}>Campaign ID: {r.campaign_id}</p>}
            {r.note && <p style={{ fontSize: 13, marginTop: 6 }}>{r.note}</p>}
            {r.message && <p style={{ fontSize: 13, marginTop: 6 }}>{r.message}</p>}
          </div>
        );
      })}
      <button className="btn-secondary" style={{ marginTop: 8 }} onClick={onDone}>Done</button>
    </div>
  );
}
