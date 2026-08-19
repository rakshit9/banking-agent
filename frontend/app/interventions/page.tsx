"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Intervention } from "@/lib/api";

export default function InterventionsPage() {
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setInterventions(await api.interventions());
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unable to load interventions.");
      }
    }
    load();
    const interval = window.setInterval(load, 2000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <main className="page stack">
      <div>
        <h1 className="page-title">Interventions</h1>
        <p className="subtitle">Human handoff records from the real FastAPI intervention registry.</p>
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      <section className="card">
        {interventions.length ? (
          <table className="table">
            <thead><tr><th>Intervention ID</th><th>Run ID</th><th>Capability</th><th>Reason</th><th>Status</th><th>Control Owner</th><th>Created</th><th>Action</th></tr></thead>
            <tbody>
              {interventions.map((item) => (
                <tr key={item.intervention_id}>
                  <td className="mono">{item.intervention_id}</td>
                  <td className="mono">{item.run_id}</td>
                  <td className="mono">{item.capability_id}</td>
                  <td>{item.reason}</td>
                  <td><span className={`badge ${item.status === "RESOLVED" ? "success" : "warning"}`}>{item.status}</span></td>
                  <td className="mono">{item.control_owner}</td>
                  <td className="mono">{new Date(item.created_at).toLocaleString()}</td>
                  <td><Link className="btn" href={`/interventions/${item.intervention_id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty">No pending, active, or resolved interventions returned by backend.</div>}
      </section>
    </main>
  );
}
