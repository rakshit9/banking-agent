"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Intervention, type RunStatus } from "@/lib/api";
import { ControlOwnership, RunResult, StatusBadge } from "@/components/ui";

export default function InterventionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [intervention, setIntervention] = useState<Intervention | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const next = await api.intervention(id);
      setIntervention(next);
      setRun(await api.run(next.run_id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load intervention.");
    }
  }

  useEffect(() => {
    // Polling keeps the handoff state synced with the in-memory FastAPI coordinator.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    const interval = window.setInterval(load, 1500);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function takeControl() {
    setBusy("take");
    setError(null);
    try {
      const result = await api.takeControl(id);
      setMessage(result.message);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Take control failed.");
    } finally {
      setBusy(null);
    }
  }

  async function resume() {
    setBusy("resume");
    setError(null);
    setMessage("VALIDATING CURRENT STATE");
    try {
      const result = await api.resume(id, "Operator completed manual verification in the live browser session.");
      setMessage(`CHECKPOINT VERIFIED | Control returned to AUTOMATION | ${String(result.status || "Replay Resumed")}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resume failed.");
    } finally {
      setBusy(null);
    }
  }

  if (error && !intervention) return <main className="page"><div className="card error-text">{error}</div></main>;
  if (!intervention) return <main className="page"><div className="empty">Loading intervention...</div></main>;

  const owner = run?.control_owner || intervention.control_owner;
  const status = run?.status || intervention.status;

  return (
    <main className="page stack">
      <div>
        <div className="label">Interventions / {intervention.run_id}</div>
        <h1 className="page-title">Human Intervention</h1>
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      {message ? <div className="card blue">{message}</div> : null}
      <section className="card" style={{ borderLeft: "4px solid var(--amber)" }}>
        <div className="row wrap">
          <div>
            <div className="row wrap" style={{ justifyContent: "flex-start" }}>
              <span className="badge warning">Human Intervention Required</span>
              <h2 className="section-title" style={{ margin: 0 }}>{intervention.reason}</h2>
            </div>
            <p className="subtitle">{intervention.human_readable_summary}</p>
          </div>
          <StatusBadge status={status} />
        </div>
        <div className="grid grid-3" style={{ marginTop: 16 }}>
          <div className="card"><div className="label">Run ID</div><div className="mono">{intervention.run_id}</div></div>
          <div className="card"><div className="label">Capability</div><div className="mono">{intervention.capability_id}</div></div>
          <div className="card"><div className="label">Current Step</div><div className="mono">{intervention.step_id || run?.current_step || "--"}</div></div>
        </div>
        <div className="grid grid-2" style={{ marginTop: 16 }}>
          <div className="card"><div className="label">Expected State</div><div className="mono green">{intervention.expected_state || "Manual roadblock cleared; member profile visible."}</div></div>
          <div className="card"><div className="label">Observed State</div><div className="mono amber">{intervention.observed_state || intervention.reason}</div></div>
        </div>
      </section>
      <section className="card">
        <div className="card-header"><strong>Control Ownership</strong><span className="mono">{owner}</span></div>
        <ControlOwnership owner={owner} status={status} />
      </section>
      <div className="grid grid-12">
        <section className="card span-5">
          <div className="card-header">
            <strong>{owner === "HUMAN" ? "MANUAL CONTROL ACTIVE" : "Operator Actions"}</strong>
            <span className="badge human">Owner: {owner}</span>
          </div>
          <p className="subtitle">
            Automation is paused while the operator completes verification in the existing browser session.
            Do not simulate verification in React; use the headed Playwright browser session.
          </p>
          <div className="card" style={{ marginTop: 16 }}>
            <div className="label">Target Checkpoint</div>
            <div className="mono green">Member Detail visible or savings workflow available</div>
          </div>
          <div className="row wrap" style={{ marginTop: 16, justifyContent: "flex-start" }}>
            <button className="btn primary" onClick={takeControl} disabled={busy !== null || intervention.status !== "PENDING"}>{busy === "take" ? "Claiming..." : "Take Control"}</button>
            <button className="btn primary" onClick={resume} disabled={busy !== null || owner !== "HUMAN"}>{busy === "resume" ? "Validating..." : "Resume Automation"}</button>
          </div>
        </section>
        <section className="span-7">
          <RunResult run={run} />
        </section>
      </div>
    </main>
  );
}
