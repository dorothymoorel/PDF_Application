// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { StrictMode, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import SystemHealthPage from "../app/settings/system/page";
import {
  API_HEALTH_URL,
  checkApiHealth,
  createHealthRequest,
  HealthStatusView,
  SystemHealth,
  type HealthViewState,
} from "../features/system/system-health";

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status,
  });

const healthyResponse = {
  data: {
    status: "HEALTHY",
    components: {
      database: { status: "AVAILABLE" },
      filesystem: { status: "AVAILABLE" },
      worker: { status: "AVAILABLE" },
      ollama: { status: "AVAILABLE" },
      ocr: { status: "AVAILABLE" },
    },
  },
  meta: { request_id: "health-request" },
} as const;

function renderState(state: HealthViewState): string {
  return renderToStaticMarkup(createElement(HealthStatusView, { state }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("system health page", () => {
  it("renders its heading and initial loading state without contacting the API", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const page = renderToStaticMarkup(createElement(SystemHealthPage));

    expect(page).toContain("System health");
    expect(page).toContain("Checking");
    expect(fetchSpy).not.toHaveBeenCalled();

    fetchSpy.mockRestore();
  });

  it("renders an accessible client status region and retry control", () => {
    const component = renderToStaticMarkup(createElement(SystemHealth));

    expect(component).toContain('role="status"');
    expect(component).toContain('aria-live="polite"');
    expect(component).toContain("<button");
    expect(component).toContain("Checking");
  });

  it("restarts the health request after a Strict Mode development remount", async () => {
    const fetchHealth = vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      if (fetchHealth.mock.calls.length === 1) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("development remount", "AbortError")),
            { once: true },
          );
        });
      }
      return Promise.resolve(jsonResponse(healthyResponse));
    });
    vi.stubGlobal("fetch", fetchHealth);

    render(createElement(StrictMode, null, createElement(SystemHealth)));

    await waitFor(() => {
      expect(screen.getByText("The worker heartbeat is current.")).toBeTruthy();
    });
    expect(fetchHealth).toHaveBeenCalledTimes(2);
  });

  it("accepts only the expected healthy API contract", async () => {
    const fetchHealth = vi.fn((input: string | URL, init?: RequestInit) => {
      void input;
      void init;
      return Promise.resolve(jsonResponse(healthyResponse));
    });

    await expect(checkApiHealth(fetchHealth)).resolves.toEqual({
      kind: "healthy",
      components: healthyResponse.data.components,
    });
    const call = fetchHealth.mock.calls[0];
    if (call === undefined) {
      throw new Error("Expected the system health check to call fetch.");
    }
    const [url, init] = call;
    expect(url).toBe(API_HEALTH_URL);
    expect(init).toMatchObject({ cache: "no-store", credentials: "omit" });
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("reports network failures as unavailable without exposing the error", async () => {
    const fetchHealth = vi.fn(() => Promise.reject(new TypeError("private network detail")));

    const result = await checkApiHealth(fetchHealth);
    const view = renderState({ ...result, checkedAt: 0 } as HealthViewState);

    expect(result).toEqual({ kind: "unavailable", reason: "network" });
    expect(view).toContain("Unavailable");
    expect(view).not.toContain("private network detail");
  });

  it.each([
    { status: "ok", service: "other-api", version: "0.1.0" },
    { status: "ok", service: "transloka-api" },
    { status: "ok", service: "transloka-api", version: "<script>" },
    ["not", "an", "object"],
  ])("reports malformed payloads as invalid responses", async (payload) => {
    const result = await checkApiHealth(
      vi.fn(() => Promise.resolve(jsonResponse(payload))),
    );

    expect(result).toEqual({ kind: "invalid" });
    expect(renderState({ kind: "invalid", checkedAt: 0 })).toContain("Invalid response");
  });

  it("handles a malformed non-success response without rendering the body", async () => {
    const response = new Response("private backend detail", { status: 503 });
    const result = await checkApiHealth(vi.fn(() => Promise.resolve(response)));
    const view = renderState({ kind: "invalid", checkedAt: 0 });

    expect(result).toEqual({ kind: "invalid" });
    expect(view).toContain("Invalid response");
    expect(view).not.toContain("private backend detail");
  });

  it("allows retry after completion", async () => {
    const fetchHealth = vi.fn(() => Promise.resolve(jsonResponse(healthyResponse)));
    const requestHealth = createHealthRequest(fetchHealth);

    await requestHealth();
    await requestHealth();

    expect(fetchHealth).toHaveBeenCalledTimes(2);
  });

  it("reuses an active request instead of creating a duplicate", async () => {
    let finishRequest: ((response: Response) => void) | undefined;
    const fetchHealth = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finishRequest = resolve;
        }),
    );
    const requestHealth = createHealthRequest(fetchHealth);

    const first = requestHealth();
    const second = requestHealth();

    expect(second).toBe(first);
    expect(fetchHealth).toHaveBeenCalledTimes(1);

    finishRequest?.(jsonResponse(healthyResponse));
    await first;
  });

  it("bounds request duration and reports timeout safely", async () => {
    const fetchHealth = vi.fn(
      (_input: string | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("private timeout detail", "AbortError")),
            { once: true },
          );
        }),
    );

    const result = await checkApiHealth(fetchHealth, undefined, 1);
    const view = renderState({ kind: "unavailable", reason: "timeout", checkedAt: 0 });

    expect(result).toEqual({ kind: "unavailable", reason: "timeout" });
    expect(view).toContain("did not respond before the timeout");
    expect(view).not.toContain("private timeout detail");
  });

  it("cancels cleanly when its owner aborts", async () => {
    const controller = new AbortController();
    const fetchHealth = vi.fn(
      (_input: string | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
        }),
    );

    const request = checkApiHealth(fetchHealth, controller.signal);
    controller.abort();

    await expect(request).resolves.toEqual({ kind: "cancelled" });
  });

  it("renders validated component states instead of placeholders", () => {
    const view = renderState({
      kind: "healthy",
      components: healthyResponse.data.components,
      checkedAt: 0,
    });

    for (const component of ["Worker", "Database", "Filesystem", "Ollama", "OCR"]) {
      expect(view).toContain(component);
    }
    expect(view).not.toContain("Not implemented");
    expect(view).toContain("The worker heartbeat is current.");
  });

  it("explains an unavailable dependency without relying on color", () => {
    const view = renderState({
      kind: "degraded",
      components: {
        ...healthyResponse.data.components,
        worker: { status: "UNAVAILABLE" },
      },
      checkedAt: 0,
    });

    expect(view).toContain("Degraded");
    expect(view).toContain("Status: Unavailable");
    expect(view).toContain("Start the TransLoka worker");
  });

  it("renders unexpected fetch failures as safe network errors", async () => {
    const result = await checkApiHealth(
      vi.fn(() => Promise.reject(new Error("private stack detail"))),
    );
    const view = renderState({ kind: "unavailable", reason: "network", checkedAt: 0 });

    expect(result).toEqual({ kind: "unavailable", reason: "network" });
    expect(view).toContain("Start the local API");
    expect(view).not.toContain("private stack detail");
  });
});
