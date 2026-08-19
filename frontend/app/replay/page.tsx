"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, isTerminal, type CapabilitySummary, type RunStatus } from "@/lib/api";
import { rememberRun } from "@/lib/runStore";
import { ControlOwnership, RunResult, StatusBadge } from "@/components/ui";

const shortcuts = [
  ["M-10428", "Success"],
  ["M-00000", "Member Not Found"],
  ["M-99999", "Permission Denied"],
  ["M-88888", "Human Intervention"],
  ["M-77777", "Slow Load"],
];

export default function ReplayPage() {
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [capabilityId, setCapabilityId] = useState("member.get_savings_balance");
  const [memberId, setMemberId] = useState("M-10428");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.capabilities().then((caps) => {
      setCapabilities(caps);
      if (caps[0]) setCapabilityId(caps[0].capability_id);
    }).catch((e) => setError(e instanceof Error ? e.message : "Unable to load capabilities."));
  }, []);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    async function poll() {
      try {
        const next = await api.run(runId!);
        if (!cancelled) setRun(next);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Unable to poll run.");
      }
    }
    poll();
    const interval = window.setInterval(() => {
      if (!run || !isTerminal(run.status)) poll();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [runId, run]);

  async function start() {
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      const started = await api.startReplay(capabilityId, { member_id: memberId });
      setRunId(started.run_id);
      rememberRun(started.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start replay.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page stack">
      <div className="row wrap">
        <div>
          <h1 className="page-title">Deterministic Replay</h1>
          <p className="subtitle">Learn with AI. Replay deterministically. OpenAI does not decide replay actions.</p>
        </div>
        {run?.intervention_id ? <Link className="btn primary" href={`/interventions/${run.intervention_id}`}>Open Intervention</Link> : null}
      </div>
      <div className="grid grid-4">
        <div className="card"><div className="label">Execution Mode</div><div className="metric-value green">DETERMINISTIC</div></div>
        <div className="card"><div className="label">LLM Calls</div><div className="metric-value">0</div></div>
        <div className="card"><div className="label">Policy</div><div className="metric-value blue">ENFORCED</div></div>
        <div className="card"><div className="label">Control Owner</div><div className="metric-value">{run?.control_owner || "AUTOMATION"}</div></div>
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      <div className="grid grid-12">
        <section className="span-7 card">
          <div className="card-header"><strong>Run Capability</strong><span className="badge deterministic">READ ONLY</span></div>
          <div className="grid grid-2">
            <div>
              <label className="label" htmlFor="capability">Capability</label>
              <select id="capability" className="select" value={capabilityId} onChange={(e) => setCapabilityId(e.target.value)}>
                {capabilities.map((cap) => <option key={`${cap.capability_id}-${cap.name}`} value={cap.capability_id}>{cap.capability_id} ({cap.version})</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="member">Runtime Input: Member ID</label>
              <input id="member" className="input mono" value={memberId} onChange={(e) => setMemberId(e.target.value)} />
            </div>
          </div>
          <div style={{ marginTop: 16 }}>
            <div className="label">Demo Shortcuts</div>
            <div className="row wrap" style={{ justifyContent: "flex-start", marginTop: 8 }}>
              {shortcuts.map(([id, label]) => <button className="btn" key={id} onClick={() => setMemberId(id)}><span className="mono">{id}</span>{label}</button>)}
            </div>
          </div>
          <div className="row" style={{ marginTop: 18 }}>
            <span className="mono muted">Shortcuts populate the real input only; they do not fake results.</span>
            <button className="btn primary" disabled={busy || !capabilityId} onClick={start}>{busy ? "Starting..." : "Run Capability"}</button>
          </div>
          {run ? (
            <div style={{ marginTop: 18 }}>
              <div className="card-header" style={{ margin: "0 0 16px", padding: "0 0 12px", background: "transparent" }}>
                <strong>{run.run_id}</strong>
                <span className="mono muted">0 LLM Calls | Deterministic Mode</span>
              </div>
              <ControlOwnership owner={run.control_owner} status={run.status} />
              <div className="timeline" style={{ marginTop: 18 }}>
                <div className="timeline-item"><div className="node" /><strong>Run Started</strong><p className="mono muted">Capability runner accepted the request.</p></div>
                <div className="timeline-item"><div className="node" /><strong>Input Validated</strong><p className="mono muted">member_id: {String(run.inputs?.member_id || "redacted")}</p></div>
                <div className="timeline-item"><div className="node branch" /><strong>Policy Check</strong><p className="mono muted">Policy enforced before browser execution.</p></div>
                <div className="timeline-item"><div className={`node ${isTerminal(run.status) ? "success" : run.status === "HUMAN_REQUIRED" ? "human" : ""}`} /><strong>{run.status}</strong><p className="mono muted">{run.current_step || run.outcome_code || run.error || "Polling backend status."}</p></div>
              </div>
            </div>
          ) : null}
        </section>
        <div className="span-5"><RunResult run={run} /></div>
      </div>
    </main>
  );
}
