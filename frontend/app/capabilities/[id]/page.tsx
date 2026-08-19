"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, formatSource, formatTimestamp, type CapabilityArtifact } from "@/lib/api";
import { ArtifactSteps, CheckpointViewer } from "@/components/ui";

export default function CapabilityDetailPage() {
  const params = useParams<{ id: string }>();
  const capabilityId = decodeURIComponent(params.id);
  const [artifact, setArtifact] = useState<CapabilityArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.capability(capabilityId).then(setArtifact).catch((e) => setError(e instanceof Error ? e.message : "Unable to load capability."));
  }, [capabilityId]);

  if (error) return <main className="page"><div className="card error-text">{error}</div></main>;
  if (!artifact) return <main className="page"><div className="empty">Loading capability artifact...</div></main>;

  return (
    <main className="page stack">
      <div className="row wrap">
        <div>
          <h1 className="page-title">{artifact.capability_id} <span className="muted">v{artifact.version}</span></h1>
          <p className="subtitle">{artifact.description}</p>
        </div>
        <div className="row">
          <span className="badge deterministic">DETERMINISTIC | 0 LLM</span>
          <span className="badge info">Schema {artifact.schema_version}</span>
        </div>
      </div>
      <div className="grid grid-12">
        <aside className="span-4 stack">
          <section className="card">
            <div className="card-header"><strong>Provenance</strong><span className="badge info">{artifact.active ? "ACTIVE" : "--"}</span></div>
            <div className="kv"><span className="label">Source</span><span className="mono">{formatSource(artifact.provenance?.source)}</span></div>
            <div className="kv"><span className="label">Discovery Run</span><span className="mono">{artifact.provenance?.discovery_run_id || "--"}</span></div>
            <div className="kv"><span className="label">Created</span><span className="mono">{formatTimestamp(artifact.provenance?.created_at)}</span></div>
            <div className="kv"><span className="label">Approved</span><span className="mono">{formatTimestamp(artifact.provenance?.approved_at)}</span></div>
            <div className="kv"><span className="label">Activated</span><span className="mono">{formatTimestamp(artifact.provenance?.activated_at)}</span></div>
            <div className="kv"><span className="label">Status</span><span className="mono">{artifact.active ? "ACTIVE" : "--"}</span></div>
            <div className="kv"><span className="label">Critic</span><span className="mono">{artifact.provenance?.critic_status || "--"}</span></div>
          </section>
          <section className="card">
            <div className="card-header"><strong>Data Schema</strong><span className="badge info">{artifact.target_application}</span></div>
            <h3 className="label">Inputs</h3>
            {Object.entries(artifact.inputs).map(([key, input]) => (
              <div className="kv" key={key}><span className="mono blue">{key}</span><span className="mono">{input.type} {input.required ? "required" : "optional"} {input.sensitive ? "sensitive" : ""}</span></div>
            ))}
            <h3 className="label" style={{ marginTop: 16 }}>Outputs</h3>
            {Object.entries(artifact.outputs).map(([key, output]) => (
              <div className="kv" key={key}><span className="mono green">{key}</span><span className="mono">{output.type} {output.format || ""}</span></div>
            ))}
          </section>
          <section className="card">
            <div className="card-header"><strong>Safety</strong><span className="badge deterministic">{artifact.safety.read_only ? "READ ONLY" : "WRITE"}</span></div>
            <div className="kv"><span className="label">Risk</span><span className="mono">{artifact.safety.risk_level}</span></div>
            <div className="kv"><span className="label">Human Approval</span><span className="mono">{String(artifact.safety.human_approval_required)}</span></div>
          </section>
          <section className="card">
            <div className="card-header"><strong>Known Business Outcomes</strong></div>
            {artifact.known_outcomes.length ? artifact.known_outcomes.map((outcome) => (
              <div className="kv" key={outcome.code}><span className="mono amber">{outcome.code}</span><span>{outcome.description}</span></div>
            )) : <p className="subtitle">No known outcomes declared in this artifact.</p>}
          </section>
          {artifact.success_condition ? <section className="card"><CheckpointViewer checkpoint={artifact.success_condition} /></section> : null}
        </aside>
        <section className="span-8 card">
          <div className="card-header"><strong>Execution Workflow</strong><span className="mono muted">{artifact.steps.length} sequential steps</span></div>
          <ArtifactSteps artifact={artifact} />
        </section>
      </div>
    </main>
  );
}
