import { describe, expect, it, vi } from "vitest";

import {
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  createRequestHeaders,
  createTransLokaClient,
  DEFAULT_API_BASE_URL,
  REQUEST_ID_HEADER,
  validateBaseUrl,
} from "../src/index.js";

const jsonResponse = (
  body: unknown,
  options: { requestId?: string; status?: number } = {},
) =>
  new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
      ...(options.requestId ? { [REQUEST_ID_HEADER]: options.requestId } : {}),
    },
    status: options.status ?? 200,
  });

const healthyResponse = {
  status: "ok",
  service: "transloka-api",
  version: "0.1.0",
} as const;

describe("API base URL", () => {
  it.each([
    [DEFAULT_API_BASE_URL, "http://127.0.0.1:8000"],
    ["http://localhost:9000", "http://localhost:9000"],
    ["http://[::1]:8000", "http://[::1]:8000"],
  ])("accepts loopback HTTP origins", (value, expected) => {
    expect(validateBaseUrl(value)).toBe(expected);
  });

  it.each([
    "https://127.0.0.1:8000",
    "http://example.com:8000",
    "http://192.168.1.10:8000",
    "http://0.0.0.0:8000",
    "http://[::]:8000",
    "http://user:password@127.0.0.1:8000",
    "http://127.0.0.1:8000/api/v1",
    "http://127.0.0.1:8000?debug=true",
    "http://127.0.0.1:8000/#fragment",
  ])("rejects non-origin or non-loopback values", (value) => {
    expect(() => validateBaseUrl(value)).toThrow(TypeError);
  });
});

describe("request headers", () => {
  it("does not send mutation headers for GET", () => {
    const headers = createRequestHeaders("GET", "client.request-123");

    expect(headers.get(REQUEST_ID_HEADER)).toBe("client.request-123");
    expect(headers.has(CLIENT_HEADER)).toBe(false);
    expect(headers.has(CLIENT_VERSION_HEADER)).toBe(false);
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])(
    "sends exact client headers for %s",
    (method) => {
      const headers = createRequestHeaders(method);

      expect(headers.get(CLIENT_HEADER)).toBe(CLIENT_HEADER_VALUE);
      expect(headers.get(CLIENT_VERSION_HEADER)).toBe(CLIENT_VERSION_HEADER_VALUE);
      expect(headers.get(REQUEST_ID_HEADER)).toMatch(/^[A-Za-z0-9._-]{1,128}$/);
    },
  );

  it("replaces an unsafe supplied request ID", () => {
    const headers = createRequestHeaders("GET", "safe\r\nInjected: true");
    const value = headers.get(REQUEST_ID_HEADER);

    expect(value).toMatch(/^[A-Za-z0-9._-]{1,128}$/);
    expect(value).not.toContain("Injected");
  });
});

describe("health client", () => {
  it("returns a typed successful health response and response request ID", async () => {
    const fetchImplementation = vi.fn((input: string | URL, init?: RequestInit) => {
      void input;
      void init;
      return Promise.resolve(
        jsonResponse(healthyResponse, { requestId: "server-request" }),
      );
    });
    const client = createTransLokaClient({ fetch: fetchImplementation });

    await expect(client.getHealth({ requestId: "client-request" })).resolves.toEqual({
      ok: true,
      data: healthyResponse,
      status: 200,
      requestId: "server-request",
    });

    const call = fetchImplementation.mock.calls[0];
    if (call === undefined) {
      throw new Error("Expected the health client to call fetch.");
    }
    const [url, init] = call;
    expect(url).toBe("http://127.0.0.1:8000/health");
    expect(init?.credentials).toBe("omit");
    expect(new Headers(init?.headers).get(REQUEST_ID_HEADER)).toBe("client-request");
    expect(new Headers(init?.headers).has(CLIENT_HEADER)).toBe(false);
  });

  it("parses normalized API errors without exposing extra response fields", async () => {
    const fetchImplementation = vi.fn(() =>
      Promise.resolve(
        jsonResponse(
          {
            error: {
              code: "OPERATION_NOT_ALLOWED",
              message: "The request could not be completed.",
              details: {},
              request_id: "error-request",
            },
            private_debug: "must not escape",
          },
          { requestId: "header-request", status: 405 },
        ),
      ),
    );
    const client = createTransLokaClient({ fetch: fetchImplementation });

    const result = await client.getHealth();

    expect(result).toEqual({
      ok: false,
      error: {
        kind: "api",
        code: "OPERATION_NOT_ALLOWED",
        message: "The request could not be completed.",
        details: {},
        requestId: "error-request",
      },
      status: 405,
      requestId: "header-request",
    });
    expect(JSON.stringify(result)).not.toContain("must not escape");
  });

  it("reports malformed success and error responses as invalid", async () => {
    const successClient = createTransLokaClient({
      fetch: () => Promise.resolve(jsonResponse({ status: "ok" })),
    });
    const errorClient = createTransLokaClient({
      fetch: () => Promise.resolve(new Response("private body", { status: 503 })),
    });

    await expect(successClient.getHealth()).resolves.toMatchObject({
      ok: false,
      error: { kind: "invalid-response" },
      status: 200,
    });
    const errorResult = await errorClient.getHealth();
    expect(errorResult).toMatchObject({
      ok: false,
      error: { kind: "invalid-response" },
      status: 503,
    });
    expect(JSON.stringify(errorResult)).not.toContain("private body");
  });

  it("handles network failures safely", async () => {
    const client = createTransLokaClient({
      fetch: () => Promise.reject(new TypeError("private network detail")),
    });

    const result = await client.getHealth();

    expect(result).toMatchObject({
      ok: false,
      error: { kind: "network" },
      status: null,
    });
    expect(JSON.stringify(result)).not.toContain("private network detail");
  });

  it("distinguishes timeout from caller cancellation", async () => {
    const pendingFetch = (_input: string | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("aborted", "AbortError")),
          { once: true },
        );
      });

    const timeoutClient = createTransLokaClient({ fetch: pendingFetch });
    await expect(timeoutClient.getHealth({ timeoutMs: 1 })).resolves.toMatchObject({
      ok: false,
      error: { kind: "timeout" },
    });

    const controller = new AbortController();
    const cancelled = timeoutClient.getHealth({ signal: controller.signal });
    controller.abort();
    await expect(cancelled).resolves.toMatchObject({
      ok: false,
      error: { kind: "aborted" },
    });

    const alreadyAborted = new AbortController();
    alreadyAborted.abort();
    await expect(
      timeoutClient.getHealth({ signal: alreadyAborted.signal }),
    ).resolves.toMatchObject({
      ok: false,
      error: { kind: "aborted" },
    });
  });
});
