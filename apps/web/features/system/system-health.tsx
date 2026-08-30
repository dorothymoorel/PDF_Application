"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const API_HEALTH_URL = "http://127.0.0.1:8000/health";
export const HEALTH_TIMEOUT_MS = 5_000;

type FetchHealth = (input: string, init: RequestInit) => Promise<Response>;

export type HealthCheckResult =
  | { kind: "healthy"; version: string }
  | { kind: "degraded" }
  | { kind: "unavailable"; reason: "network" | "timeout" }
  | { kind: "invalid" }
  | { kind: "error" }
  | { kind: "cancelled" };

export type HealthViewState =
  | { kind: "loading" }
  | (Exclude<HealthCheckResult, { kind: "cancelled" }> & { checkedAt: number });

const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}$/;

function isHealthResponse(value: unknown): value is {
  status: "ok";
  service: "transloka-api";
  version: string;
} {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const response = value as Record<string, unknown>;
  return (
    response.status === "ok" &&
    response.service === "transloka-api" &&
    typeof response.version === "string" &&
    VERSION_PATTERN.test(response.version)
  );
}

export async function checkApiHealth(
  fetchHealth: FetchHealth = fetch,
  parentSignal?: AbortSignal,
  timeoutMs = HEALTH_TIMEOUT_MS,
): Promise<HealthCheckResult> {
  if (parentSignal?.aborted) {
    return { kind: "cancelled" };
  }

  const controller = new AbortController();
  let timedOut = false;
  const cancelRequest = () => controller.abort();
  parentSignal?.addEventListener("abort", cancelRequest, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetchHealth(API_HEALTH_URL, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    if (!response.ok) {
      return { kind: "degraded" };
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      return { kind: "invalid" };
    }

    return isHealthResponse(payload)
      ? { kind: "healthy", version: payload.version }
      : { kind: "invalid" };
  } catch (error: unknown) {
    if (parentSignal?.aborted) {
      return { kind: "cancelled" };
    }
    if (timedOut) {
      return { kind: "unavailable", reason: "timeout" };
    }
    if (error instanceof TypeError) {
      return { kind: "unavailable", reason: "network" };
    }
    return { kind: "error" };
  } finally {
    clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", cancelRequest);
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

const plannedComponents = ["Worker", "Database", "Filesystem", "Ollama", "OCR"] as const;

function apiStatus(state: HealthViewState): { label: string; detail: string } {
  switch (state.kind) {
    case "loading":
      return { label: "Checking", detail: "Waiting for the local API." };
    case "healthy":
      return { label: "Healthy", detail: `FastAPI ${state.version} is responding.` };
    case "degraded":
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
      return {
        label: "Error",
        detail: "The health check could not be completed safely.",
      };
  }
}

function overallStatus(state: HealthViewState): string {
  switch (state.kind) {
    case "loading":
      return "Checking";
    case "healthy":
      return "Healthy";
    case "degraded":
      return "Degraded";
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
        <span className="font-medium text-slate-800">{status}</span>
        <span className="mt-1 block text-sm leading-6 text-slate-600">{detail}</span>
      </dd>
    </div>
  );
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
        {plannedComponents.map((name) => (
          <StatusRow
            detail="No health probe is implemented for this component yet."
            key={name}
            name={name}
            status="Not implemented"
          />
        ))}
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
