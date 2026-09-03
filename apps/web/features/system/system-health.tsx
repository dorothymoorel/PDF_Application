"use client";

import {
  createTransLokaClient,
  DEFAULT_API_BASE_URL,
  type SystemHealthResponse,
} from "@transloka/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

export const API_HEALTH_URL = `${DEFAULT_API_BASE_URL}/api/v1/system/health`;
export const HEALTH_TIMEOUT_MS = 5_000;

type FetchHealth = (input: string | URL, init?: RequestInit) => Promise<Response>;
type SystemComponents = SystemHealthResponse["data"]["components"];
type CompletedHealth =
  | { kind: "healthy"; components: SystemComponents }
  | { kind: "degraded"; components: SystemComponents }
  | { kind: "unhealthy"; components: SystemComponents };

export type HealthCheckResult =
  | CompletedHealth
  | { kind: "degraded-response" }
  | { kind: "unavailable"; reason: "network" | "timeout" }
  | { kind: "invalid" }
  | { kind: "error" }
  | { kind: "cancelled" };

export type HealthViewState =
  | { kind: "loading" }
  | (Exclude<HealthCheckResult, { kind: "cancelled" }> & { checkedAt: number });

export async function checkApiHealth(
  fetchHealth: FetchHealth = fetch,
  parentSignal?: AbortSignal,
  timeoutMs = HEALTH_TIMEOUT_MS,
): Promise<HealthCheckResult> {
  const client = createTransLokaClient({ fetch: fetchHealth });
  const result = await client.getSystemHealth({
    timeoutMs,
    ...(parentSignal === undefined ? {} : { signal: parentSignal }),
  });

  if (result.ok) {
    const completed = {
      components: result.data.data.components,
    };
    switch (result.data.data.status) {
      case "HEALTHY":
        return { kind: "healthy", ...completed };
      case "DEGRADED":
        return { kind: "degraded", ...completed };
      case "UNHEALTHY":
        return { kind: "unhealthy", ...completed };
    }
  }

  switch (result.error.kind) {
    case "aborted":
      return { kind: "cancelled" };
    case "network":
      return { kind: "unavailable", reason: "network" };
    case "timeout":
      return { kind: "unavailable", reason: "timeout" };
    case "invalid-response":
      return { kind: "invalid" };
    case "api":
      return { kind: "degraded-response" };
  }
}

export function createHealthRequest(fetchHealth: FetchHealth = fetch) {
  let activeRequest: {
    promise: Promise<HealthCheckResult>;
    signal: AbortSignal | undefined;
  } | null = null;

  return (signal?: AbortSignal): Promise<HealthCheckResult> => {
    if (activeRequest !== null && !activeRequest.signal?.aborted) {
      return activeRequest.promise;
    }

    const request = checkApiHealth(fetchHealth, signal);
    const clearRequest = () => {
      if (activeRequest?.promise === request) {
        activeRequest = null;
      }
    };
    activeRequest = { promise: request, signal };
    void request.then(clearRequest, clearRequest);
    return request;
  };
}

const componentNames = ["database", "filesystem", "worker", "ollama", "ocr"] as const;
const componentLabels: Record<(typeof componentNames)[number], string> = {
  database: "Database",
  filesystem: "Filesystem",
  worker: "Worker",
  ollama: "Ollama",
  ocr: "OCR",
};

function statusLabel(status: "AVAILABLE" | "DEGRADED" | "UNAVAILABLE"): string {
  switch (status) {
    case "AVAILABLE":
      return "Healthy";
    case "DEGRADED":
      return "Degraded";
    case "UNAVAILABLE":
      return "Unavailable";
  }
}

function componentDetail(
  name: (typeof componentNames)[number],
  status: "AVAILABLE" | "DEGRADED" | "UNAVAILABLE",
): string {
  if (status === "AVAILABLE") {
    return {
      database: "The SQLite database is responding.",
      filesystem: "The local data directories are available.",
      worker: "The worker heartbeat is current.",
      ollama: "The local Ollama service is responding.",
      ocr: "The local OCR runtime and model bundle are ready.",
    }[name];
  }
  if (status === "DEGRADED") {
    return `${componentLabels[name]} is responding with reduced readiness.`;
  }
  return {
    database: "The database is unavailable. Restart TransLoka and check the data directory.",
    filesystem: "The data directory is missing or not writable.",
    worker: "Start the TransLoka worker and wait for a fresh heartbeat.",
    ollama: "Start Ollama locally, then retry this health check.",
    ocr: "Install the OCR runtime and provision its local model bundle.",
  }[name];
}

function apiStatus(state: HealthViewState): { label: string; detail: string } {
  switch (state.kind) {
    case "loading":
      return { label: "Checking", detail: "Waiting for the local API." };
    case "healthy":
    case "degraded":
    case "unhealthy":
      return { label: "Healthy", detail: "The detailed health endpoint is responding." };
    case "degraded-response":
      return { label: "Degraded", detail: "The local API responded with an error status." };
    case "unavailable":
      return {
        label: "Unavailable",
        detail:
          state.reason === "timeout"
            ? "The local API did not respond before the timeout."
            : "Start the local API, then try again.",
      };
    case "invalid":
      return {
        label: "Invalid response",
        detail: "The local API response did not match the expected health contract.",
      };
    case "error":
      return { label: "Error", detail: "The health check could not be completed safely." };
  }
}

function overallStatus(state: HealthViewState): string {
  switch (state.kind) {
    case "loading":
      return "Checking";
    case "healthy":
      return "Healthy";
    case "degraded":
    case "degraded-response":
      return "Degraded";
    case "unhealthy":
      return "Unhealthy";
    case "unavailable":
      return "Unavailable";
    case "invalid":
    case "error":
      return "Error";
  }
}

function StatusRow({
  detail,
  name,
  status,
}: Readonly<{ detail: string; name: string; status: string }>) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <dt className="font-semibold text-slate-950">{name}</dt>
      <dd className="mt-2">
        <span className="font-medium text-slate-800">Status: {status}</span>
        <span className="mt-1 block text-sm leading-6 text-slate-600">{detail}</span>
      </dd>
    </div>
  );
}

function isCompletedHealth(state: HealthViewState): state is CompletedHealth & {
  checkedAt: number;
} {
  return state.kind === "healthy" || state.kind === "degraded" || state.kind === "unhealthy";
}

export function HealthStatusView({ state }: Readonly<{ state: HealthViewState }>) {
  const api = apiStatus(state);

  return (
    <>
      <div
        aria-live="polite"
        className="mt-8 rounded-xl border border-slate-300 bg-slate-100 p-5"
        role="status"
      >
        <p className="text-sm font-medium uppercase tracking-wider text-slate-600">
          Overall status
        </p>
        <p className="mt-2 text-2xl font-semibold text-slate-950">{overallStatus(state)}</p>
        {state.kind !== "loading" ? (
          <p className="mt-2 text-sm text-slate-600">
            Last checked {new Date(state.checkedAt).toLocaleTimeString()}
          </p>
        ) : null}
      </div>

      <dl className="mt-6 grid gap-4 md:grid-cols-2">
        <StatusRow
          detail="This page is running in the local web application."
          name="Frontend"
          status="Healthy"
        />
        <StatusRow detail={api.detail} name="API" status={api.label} />
        {componentNames.map((name) => {
          const completed = isCompletedHealth(state);
          const status = completed ? state.components[name].status : "UNAVAILABLE";
          return (
            <StatusRow
              detail={
                completed
                  ? componentDetail(name, status)
                  : state.kind === "loading"
                    ? "Waiting for the detailed API health response."
                    : "Detailed status is unavailable until the API health check succeeds."
              }
              key={name}
              name={componentLabels[name]}
              status={state.kind === "loading" ? "Checking" : statusLabel(status)}
            />
          );
        })}
      </dl>
    </>
  );
}

export function SystemHealth() {
  const [state, setState] = useState<HealthViewState>({ kind: "loading" });
  const requestHealth = useRef<ReturnType<typeof createHealthRequest> | null>(null);
  const activeController = useRef<AbortController | null>(null);

  if (requestHealth.current === null) {
    requestHealth.current = createHealthRequest();
  }

  const runCheck = useCallback(async () => {
    if (activeController.current !== null) {
      return;
    }

    const controller = new AbortController();
    activeController.current = controller;
    setState({ kind: "loading" });

    try {
      const result = await requestHealth.current?.(controller.signal);
      if (result !== undefined && result.kind !== "cancelled") {
        setState({ ...result, checkedAt: Date.now() });
      }
    } finally {
      if (activeController.current === controller) {
        activeController.current = null;
      }
    }
  }, []);

  useEffect(() => {
    void runCheck();
    return () => {
      const controller = activeController.current;
      controller?.abort();
      if (activeController.current === controller) {
        activeController.current = null;
      }
    };
  }, [runCheck]);

  return (
    <section aria-labelledby="component-status-heading">
      <h2 className="sr-only" id="component-status-heading">
        Component status
      </h2>
      <HealthStatusView state={state} />
      <button
        className="mt-6 rounded-lg border border-slate-900 bg-white px-4 py-2.5 font-medium text-slate-900 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={state.kind === "loading"}
        onClick={() => void runCheck()}
        type="button"
      >
        {state.kind === "loading" ? "Checking…" : "Retry health check"}
      </button>
    </section>
  );
}
