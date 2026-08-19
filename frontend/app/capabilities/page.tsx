"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, formatTimestamp, type CapabilitySummary } from "@/lib/api";

export default function CapabilitiesPage() {
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.capabilities().then(setCapabilities).catch((e) => setError(e instanceof Error ? e.message : "Unable to load capabilities."));
  }, []);

  return (
    <main className="page stack">
      <div>
        <h1 className="page-title">Capabilities</h1>
        <p className="subtitle">Registered replayable CapabilityArtifacts returned by the backend.</p>
      </div>
      {error ? <div className="card error-text">{error}</div> : null}
      <div className="grid grid-2">
        {capabilities.map((cap) => (
          <div className="card stack" key={`${cap.capability_id}-${cap.name}`}>
            <div className="row">
              <strong>{cap.name}</strong>
              <div className="row wrap" style={{ justifyContent: "flex-end" }}>
                {cap.provenance?.source === "AI_DISCOVERY" ? <span className="badge ai">AI Discovered</span> : null}
                {cap.provenance?.critic_status === "APPROVED" || cap.provenance?.approved_at ? <span className="badge success">Approved</span> : null}
                {cap.active ? <span className="badge info">Active</span> : null}
                <span className="badge deterministic">Deterministic</span>
              </div>
            </div>
            <p className="subtitle">{cap.description}</p>
            <div className="kv"><span className="label">Capability ID</span><span className="mono">{cap.capability_id}</span></div>
            <div className="kv"><span className="label">Version</span><span className="mono">{cap.version}</span></div>
            <div className="kv"><span className="label">Risk</span><span className="mono">{cap.risk_level} / {cap.read_only ? "READ ONLY" : "WRITE"}</span></div>
            <div className="kv"><span className="label">I/O</span><span className="mono">{cap.input_keys.join(", ")} {"->"} {cap.output_keys.join(", ")}</span></div>
            <div className="kv"><span className="label">Created</span><span className="mono">{formatTimestamp(cap.provenance?.created_at)}</span></div>
            <div className="kv"><span className="label">Approved</span><span className="mono">{formatTimestamp(cap.provenance?.approved_at)}</span></div>
            <div className="kv"><span className="label">Discovery Run</span><span className="mono">{cap.provenance?.discovery_run_id || "--"}</span></div>
            <div className="row wrap" style={{ justifyContent: "flex-start" }}>
              <Link className="btn" href={`/capabilities/${encodeURIComponent(cap.capability_id)}`}>View Artifact</Link>
              <Link className="btn primary" href="/replay">Replay</Link>
            </div>
          </div>
        ))}
      </div>
      {!capabilities.length && !error ? <div className="empty">No capabilities returned yet.</div> : null}
    </main>
  );
}
