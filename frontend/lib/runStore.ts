"use client";

const KEY = "banking-agent-known-run-ids";

export function getKnownRunIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function rememberRun(runId: string) {
  if (typeof window === "undefined") return;
  const ids = [runId, ...getKnownRunIds().filter((id) => id !== runId)].slice(0, 25);
  window.localStorage.setItem(KEY, JSON.stringify(ids));
  window.dispatchEvent(new Event("known-runs-changed"));
}
