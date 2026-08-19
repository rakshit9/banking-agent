"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type RunStatus } from "@/lib/api";
import { getKnownRunIds } from "@/lib/runStore";
import { StatusBadge } from "@/components/ui";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunStatus[]>([]);

  useEffect(() => {
    async function load() {
      const results = await Promise.allSettled(getKnownRunIds().map((id) => api.run(id)));
      setRuns(results.filter((r): r is PromiseFulfilledResult<RunStatus> => r.status === "fulfilled").map((r) => r.value));
    }
    load();
    const interval = window.setInterval(load, 2000);
    window.addEventListener("known-runs-changed", load);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("known-runs-changed", load);
    };
  }, []);

  return (
    <main className="page stack">
      <div>
        <h1 className="page-title">Runs</h1>
        <p className="subtitle">The backend exposes run detail by ID, but no list-runs endpoint. This page tracks runs started in this browser session.</p>
      </div>
      <section className="card">
        {runs.length ? (
          <table className="table">
            <thead><tr><th>Run ID</th><th>Mode</th><th>Capability</th><th>Status</th><th>Control Owner</th><th>Result</th><th>Started</th></tr></thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td className="mono">{run.intervention_id ? <Link className="blue" href={`/interventions/${run.intervention_id}`}>{run.run_id}</Link> : run.run_id}</td>
                  <td><span className={`badge ${run.mode === "discovery" ? "ai" : "deterministic"}`}>{run.mode}</span></td>
                  <td className="mono">{run.capability_id}</td>
                  <td><StatusBadge status={run.status} mode={run.mode} /></td>
                  <td className="mono">{run.control_owner}</td>
                  <td className="mono">{run.outcome_code || Object.keys(run.outputs || {}).join(", ") || run.error || "--"}</td>
                  <td className="mono">{new Date(run.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty">No known runs yet. Start discovery or replay to populate this page.</div>}
      </section>
    </main>
  );
}
