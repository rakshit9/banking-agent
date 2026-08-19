export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001";

export type Health = { status: string; service: string };
export type CapabilitySummary = {
  capability_id: string;
  name: string;
  version: string;
  description: string;
  target_application: string;
  risk_level: string;
  read_only: boolean;
  input_keys: string[];
  output_keys: string[];
  provenance?: ProvenanceMetadata | null;
  active?: boolean;
};
export type ProvenanceMetadata = {
  source?: string | null;
  discovery_run_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  approved_at?: string | null;
  activated_at?: string | null;
  critic_status?: string | null;
};
export type LocatorBundle = {
  role?: string;
  accessible_name?: string;
  label?: string;
  text?: string;
  stable_attributes?: Record<string, string>;
  css?: string;
  xpath?: string;
  visual_hint?: string;
};
export type Action = {
  action_type: string;
  locator?: LocatorBundle;
  value?: string;
  value_from_input?: string;
  target_url?: string;
  extract_key?: string;
  timeout_ms?: number;
};
export type Checkpoint = {
  type: string;
  expected?: string;
  locator?: LocatorBundle;
  branches?: Checkpoint[];
  outcome_code?: string;
  description?: string;
};
export type CapabilityArtifact = {
  schema_version: string;
  capability_id: string;
  name: string;
  version: string;
  description: string;
  target_application: string;
  compatibility?: Record<string, unknown>;
  inputs: Record<string, { type: string; required: boolean; description?: string; sensitive?: boolean; validation_pattern?: string }>;
  outputs: Record<string, { type: string; description?: string; required?: boolean; format?: string }>;
  safety: { risk_level: string; read_only: boolean; human_approval_required: boolean };
  known_outcomes: Array<{ code: string; description: string; category: string; checkpoint: Checkpoint }>;
  steps: Array<{ step_id: string; description: string; action: Action; checkpoint?: Checkpoint; risk_level: string; optional?: boolean; recovery_hint?: string }>;
  success_condition?: Checkpoint;
  provenance?: ProvenanceMetadata | null;
  active?: boolean;
};
export type RunStatus = {
  run_id: string;
  mode: string;
  capability_id: string;
  status: string;
  current_step?: string | null;
  control_owner: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  outcome_code?: string | null;
  error?: string | null;
  intervention_id?: string | null;
  created_at: string;
  updated_at: string;
};
export type Intervention = {
  intervention_id: string;
  run_id: string;
  capability_id: string;
  capability_version?: string;
  step_id?: string | null;
  reason: string;
  human_readable_summary: string;
  expected_state?: string | null;
  observed_state?: string | null;
  control_owner: string;
  status: string;
  screenshot_path?: string | null;
  created_at: string;
  resolved_at?: string | null;
  resolution_notes?: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      // Keep HTTP status message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  capabilities: () => request<CapabilitySummary[]>("/api/capabilities"),
  capability: (id: string) => request<CapabilityArtifact>(`/api/capabilities/${encodeURIComponent(id)}`),
  startReplay: (id: string, inputs: Record<string, unknown>) =>
    request<{ run_id: string; capability_id: string; status: string }>(`/api/capabilities/${encodeURIComponent(id)}/replay`, {
      method: "POST",
      body: JSON.stringify({ inputs }),
    }),
  startDiscovery: (goal: string, target_url?: string) =>
    request<{ run_id: string; status: string; goal: string }>("/api/discovery", {
      method: "POST",
      body: JSON.stringify({ goal, target_url }),
    }),
  run: (id: string) => request<RunStatus>(`/api/runs/${encodeURIComponent(id)}`),
  interventions: () => request<Intervention[]>("/api/interventions"),
  intervention: (id: string) => request<Intervention>(`/api/interventions/${encodeURIComponent(id)}`),
  takeControl: (id: string) =>
    request<{ intervention_id: string; status: string; control_owner: string; message: string }>(
      `/api/interventions/${encodeURIComponent(id)}/take-control`,
      { method: "POST" },
    ),
  resume: (id: string, resolution_notes?: string) =>
    request<Record<string, unknown>>(`/api/interventions/${encodeURIComponent(id)}/resume`, {
      method: "POST",
      body: JSON.stringify({ resolution_notes }),
    }),
  cancel: (id: string) =>
    request<{ intervention_id: string; status: string; message: string }>(`/api/interventions/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
};

export function isTerminal(status?: string | null) {
  return ["SUCCESS", "BUSINESS_OUTCOME", "FAILED", "CANCELLED"].includes(status || "");
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "--";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function formatTimestamp(value?: string | null): string {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatSource(value?: string | null): string {
  if (!value) return "--";
  return value.split("_").map((part) => part.charAt(0) + part.slice(1).toLowerCase()).join(" ");
}
