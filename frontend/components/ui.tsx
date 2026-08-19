import { formatValue, type CapabilityArtifact, type Checkpoint, type LocatorBundle, type RunStatus } from "@/lib/api";

export function StatusBadge({ status, mode }: { status?: string | null; mode?: string }) {
  const normalized = status || "UNKNOWN";
  const cls =
    normalized === "SUCCESS" ? "success" :
    normalized === "FAILED" || normalized === "CANCELLED" ? "error" :
    normalized === "HUMAN_REQUIRED" || normalized === "PAUSED" ? "warning" :
    normalized === "BUSINESS_OUTCOME" ? "human" :
    mode === "discovery" ? "ai" : "deterministic";
  return <span className={`badge ${cls}`}>{normalized}</span>;
}

export function MetricCard({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`metric-value ${tone || ""}`}>{value}</div>
      {hint ? <div className="mono muted">{hint}</div> : null}
    </div>
  );
}

export function ArchitectureFlow() {
  const steps = [
    ["DISCOVER", "OpenAI + LangGraph", "AI explores and learns the workflow."],
    ["COMPILE", "CapabilityArtifact", "Runtime literals become typed inputs."],
    ["REPLAY", "Deterministic / 0 LLM", "Saved actions run without model decisions."],
    ["INTERVENE", "Human-in-the-Loop", "Operator resolves blocked browser states."],
  ];
  return (
    <div className="flow">
      {steps.map(([title, tech, detail]) => (
        <div className="flow-step" key={title}>
          <div className="label">{title}</div>
          <h3 className="section-title">{tech}</h3>
          <p className="subtitle">{detail}</p>
        </div>
      ))}
    </div>
  );
}

export function RunResult({ run }: { run?: RunStatus | null }) {
  if (!run) return <div className="empty">No run selected.</div>;
  const balance = run.outputs?.savings_balance;
  return (
    <div className="card">
      <div className="card-header">
        <strong>Run Result</strong>
        <StatusBadge status={run.status} mode={run.mode} />
      </div>
      <div className="stack">
        <div className="kv"><span className="label">Run ID</span><span className="mono">{run.run_id}</span></div>
        <div className="kv"><span className="label">Control Owner</span><span className="mono">{run.control_owner}</span></div>
        <div className="kv"><span className="label">Current Step</span><span className="mono">{formatValue(run.current_step)}</span></div>
        {run.status === "SUCCESS" && (
          <div className="card" style={{ borderTop: "3px solid var(--emerald)" }}>
            <div className="label">Savings Balance</div>
            <div className="metric-value green">{formatValue(balance)}</div>
            <div className="mono muted">Execution: Deterministic | LLM Calls: 0 | Evidence: Recorded</div>
          </div>
        )}
        {run.status === "BUSINESS_OUTCOME" && (
          <div className="card" style={{ borderTop: "3px solid var(--amber)" }}>
            <div className="label">Business Outcome</div>
            <div className="metric-value amber">{formatValue(run.outcome_code)}</div>
            <p className="subtitle">{businessOutcomeMessage(run.outcome_code)}</p>
          </div>
        )}
        {run.status === "HUMAN_REQUIRED" && (
          <div className="card" style={{ borderTop: "3px solid var(--amber)" }}>
            <div className="label">Human Intervention Required</div>
            <div className="metric-value amber">{formatValue(run.intervention_id)}</div>
          </div>
        )}
        {run.error ? <div className="error-text">{run.error}</div> : null}
        <pre className="card mono" style={{ overflow: "auto" }}>{JSON.stringify({ inputs: run.inputs, outputs: run.outputs }, null, 2)}</pre>
      </div>
    </div>
  );
}

export function ArtifactSteps({ artifact }: { artifact: CapabilityArtifact }) {
  return (
    <div className="timeline">
      {artifact.steps.map((step, index) => (
        <div className="timeline-item" key={step.step_id}>
          <div className={`node ${step.checkpoint?.type === "ONE_OF" ? "branch" : step.action.action_type === "extract" ? "success" : ""}`} />
          <div className="card">
            <div className="row wrap">
              <strong>{String(index + 1).padStart(2, "0")} {step.description}</strong>
              <span className="badge info">{step.action.action_type}</span>
            </div>
            <LocatorViewer locator={step.action.locator} />
            {step.checkpoint ? <CheckpointViewer checkpoint={step.checkpoint} /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function LocatorViewer({ locator }: { locator?: LocatorBundle }) {
  if (!locator) return null;
  const rows = [
    locator.role || locator.accessible_name ? ["role + accessible name", [locator.role, locator.accessible_name].filter(Boolean).join(" / ")] : null,
    locator.label ? ["label", locator.label] : null,
    locator.stable_attributes ? ["stable attributes", JSON.stringify(locator.stable_attributes)] : null,
    locator.text ? ["text", locator.text] : null,
    locator.css ? ["css fallback", locator.css] : null,
    locator.xpath ? ["xpath fallback", locator.xpath] : null,
  ].filter(Boolean) as string[][];
  return (
    <div style={{ marginTop: 12 }}>
      <span className="badge deterministic">Semantic-first targeting</span>
      {rows.map(([label, value]) => (
        <div className="kv" key={label}><span className="label">{label}</span><span className="mono">{value}</span></div>
      ))}
    </div>
  );
}

export function CheckpointViewer({ checkpoint }: { checkpoint: Checkpoint }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div className="label">Checkpoint</div>
      <div className="mono">{checkpoint.type}: {checkpoint.expected || checkpoint.description || "--"}</div>
      {checkpoint.branches?.map((branch) => (
        <div className="kv" key={`${branch.type}-${branch.expected}-${branch.outcome_code}`}>
          <span className="label">{branch.outcome_code || branch.type}</span>
          <span className="mono">{branch.expected}</span>
        </div>
      ))}
    </div>
  );
}

export function ControlOwnership({ owner, status }: { owner?: string; status?: string }) {
  const active = status === "RESUMING" ? "RESUMING" : owner === "HUMAN" ? "HUMAN" : status === "HUMAN_REQUIRED" || status === "PAUSED" ? "PAUSED" : "AUTOMATION";
  return (
    <div className="ownership">
      {["AUTOMATION", "PAUSED", "HUMAN", "RESUMING", "AUTOMATION"].map((step, index) => (
        <span className={`owner-step ${step === active ? "active" : ""}`} key={`${step}-${index}`}>{step}</span>
      ))}
    </div>
  );
}

function businessOutcomeMessage(code?: string | null) {
  if (code === "MEMBER_NOT_FOUND") return "No member found for the supplied Member ID.";
  if (code === "PERMISSION_DENIED") return "The operator lacks permission to view this member.";
  return "The run ended in a recognized non-crash business outcome.";
}
