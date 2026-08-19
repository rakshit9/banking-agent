"use client";

import { useEffect, useState } from "react";
import { api, isTerminal, type CapabilitySummary, type Health, type Intervention, type RunStatus } from "@/lib/api";
import { getKnownRunIds } from "@/lib/runStore";
import { ArchitectureFlow, MetricCard, StatusBadge } from "@/components/ui";

export default function DashboardPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [h, caps, intvs] = await Promise.all([api.health(), api.capabilities(), api.interventions()]);
        setHealth(h);
        setCapabilities(caps);
        setInterventions(intvs);
        const known = await Promise.allSettled(getKnownRunIds().map((id) => api.run(id)));
        setRuns(known.filter((r): r is PromiseFulfilledResult<RunStatus> => r.status === "fulfilled").map((r) => r.value));
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unable to load dashboard data.");
      }
    }
    load();
    const interval = window.setInterval(load, 3000);
    window.addEventListener("known-runs-changed", load);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("known-runs-changed", load);
    };
  }, []);

  const activeRuns = runs.filter((run) => !isTerminal(run.status)).length;
  const pendingInterventions = interventions.filter((i) => ["PENDING", "IN_PROGRESS"].includes(i.status)).length;

  return (
    <main className="page stack">
      <div>
        <h1 className="page-title">Banking Agent</h1>
        <p className="subtitle">Computer-Use Capability Platform</p>
      </div>
      {error ? <div className="card error-text">Backend unavailable: {error}</div> : null}
      <div className="grid grid-4">
        <MetricCard label="Backend Health" value={health?.status?.toUpperCase() || "UNKNOWN"} hint={health?.service || "FastAPI not reached"} tone={health ? "green" : "amber"} />
        <MetricCard label="Registered Capabilities" value={capabilities.length} hint={capabilities[0]?.capability_id || "No capabilities returned"} />
        <MetricCard label="Known Active Runs" value={activeRuns} hint="From current browser session" />
        <MetricCard label="Pending Interventions" value={pendingInterventions} hint={pendingInterventions ? "Operator action required" : "All queues clear"} tone={pendingInterventions ? "amber" : "green"} />
      </div>
      <section className="card">
        <div className="card-header"><strong>Pipeline Architecture</strong><span className="badge deterministic">Replay = 0 LLM</span></div>
        <ArchitectureFlow />
      </section>
      <section className="card">
        <div className="card-header"><strong>Recent Known Runs</strong><span className="mono muted">No backend list-runs endpoint; using current frontend session</span></div>
        {runs.length ? (
          <table className="table">
            <thead><tr><th>Run ID</th><th>Mode</th><th>Capability</th><th>Status</th><th>Control Owner</th><th>Result</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td className="mono">{run.run_id}</td>
                  <td><span className={`badge ${run.mode === "discovery" ? "ai" : "deterministic"}`}>{run.mode}</span></td>
                  <td className="mono">{run.capability_id}</td>
                  <td><StatusBadge status={run.status} mode={run.mode} /></td>
                  <td className="mono">{run.control_owner}</td>
                  <td className="mono">{run.outcome_code || Object.keys(run.outputs || {}).join(", ") || run.error || "--"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty">No known runs in this browser session yet.</div>}
      </section>
    </main>
  );
}
