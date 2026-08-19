"use client";

import { useEffect, useState } from "react";
import { api, isTerminal, type RunStatus } from "@/lib/api";
import { rememberRun } from "@/lib/runStore";
import { RunResult, StatusBadge } from "@/components/ui";

const defaultGoal = "Look up member M-10428 and return their current savings balance.";

export default function DiscoveryPage() {
  const [goal, setGoal] = useState(defaultGoal);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      const started = await api.startDiscovery(goal);
      setRunId(started.run_id);
      rememberRun(started.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start discovery.");
    } finally {
      setBusy(false);
    }
  }

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

  return (
    <main className="page stack">
      <div>
        <h1 className="page-title">Discovery Studio</h1>
        <p className="subtitle">AI discovery uses OpenAI + LangGraph. Replay artifacts remain deterministic afterward.</p>
      </div>
      <section className="card">
        <div className="card-header"><strong>New Discovery Run</strong><span className="badge ai">LLM calls &gt; 0</span></div>
        <label className="label" htmlFor="goal">Discovery Goal</label>
        <textarea id="goal" className="textarea" value={goal} onChange={(event) => setGoal(event.target.value)} />
        <div className="row" style={{ marginTop: 16 }}>
          <span className="mono muted">Target application: Northstar Core via backend default URL</span>
          <button className="btn primary" onClick={start} disabled={busy}>{busy ? "Starting Discovery..." : "Start Discovery"}</button>
        </div>
      </section>
      {error ? <div className="card error-text">{error}</div> : null}
      {runId ? (
        <div className="grid grid-12">
          <section className="card span-7">
            <div className="card-header">
              <strong>Execution Timeline</strong>
              <StatusBadge status={run?.status || "RUNNING"} mode="discovery" />
            </div>
            <div className="timeline">
              <div className="timeline-item"><div className="node branch" /><strong>Run submitted</strong><p className="mono muted">{runId}</p></div>
              <div className="timeline-item"><div className="node" /><strong>LangGraph discovery active</strong><p className="mono muted">Polling real /api/runs/{"{run_id}"} status.</p></div>
              {run?.status ? <div className="timeline-item"><div className={`node ${isTerminal(run.status) ? "success" : ""}`} /><strong>{run.status}</strong><p className="mono muted">{run.error || "Awaiting backend output."}</p></div> : null}
            </div>
          </section>
          <div className="span-5"><RunResult run={run} /></div>
        </div>
      ) : null}
    </main>
  );
}
