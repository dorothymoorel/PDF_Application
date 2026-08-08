import { describe, expect, it, vi } from "vitest";

import type {
  components,
  CreateProjectInput,
  JobAttemptResource,
  JobResource,
  ProjectResource,
} from "../src/index";
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
} from "../src/index";

const jsonResponse = (
  body: unknown,
  options: { requestId?: string; retryAfter?: string; status?: number } = {},
) =>
  new Response(JSON.stringify(body), {
    headers: {
      "Content-Type": "application/json",
      ...(options.requestId ? { [REQUEST_ID_HEADER]: options.requestId } : {}),
      ...(options.retryAfter ? { "Retry-After": options.retryAfter } : {}),
    },
    status: options.status ?? 200,
  });

const healthyResponse = {
  status: "ok",
  service: "transloka-api",
  version: "0.1.0",
} as const;

const project = {
  id: "prj_00000000-0000-4000-8000-000000000001",
  name: "System Design Book",
  description: null,
  status: "CREATED",
  source_language: "en",
  target_language: "id",
  document_type: "TECHNICAL_BOOK",
  translation_style: "PROFESSIONAL",
  reconstruction_mode: "HYBRID",
  progress: 0,
  active_document_id: null,
  settings: {},
  created_at: "2026-07-28T10:00:00.000Z",
  updated_at: "2026-07-28T10:00:00.000Z",
} satisfies ProjectResource;

const createProjectInput = {
  name: project.name,
  description: null,
  source_language: "en",
  target_language: "id",
  document_type: "TECHNICAL_BOOK",
  translation_style: "PROFESSIONAL",
  reconstruction_mode: "HYBRID",
} satisfies CreateProjectInput;

const job = {
  id: "job_00000000-0000-4000-8000-000000000001",
  job_type: "MAINTENANCE",
  status: "RUNNING",
  progress: 0.4,
  current_stage: "EXTRACT_TEXT",
  project_id: project.id,
  document_id: null,
  retry_count: 0,
  max_retries: 3,
  created_at: "2026-08-08T10:00:00.000Z",
  started_at: "2026-08-08T10:00:01.000Z",
  completed_at: null,
  error: null,
} satisfies JobResource;

const attempt = {
  attempt_number: 1,
  status: "COMPLETED",
  started_at: "2026-08-08T10:00:01.000Z",
  completed_at: "2026-08-08T10:00:02.000Z",
  duration_ms: 1000,
  error: null,
} satisfies JobAttemptResource;

const normalizedError = {
  error: {
    code: "VALIDATION_ERROR",
    message: "The request contains invalid values.",
    details: {
      fields: [{ message: "Invalid value.", path: "body.quantity", type: "greater_than" }],
    },
    request_id: "error-request",
  },
} satisfies components["schemas"]["ErrorResponse"];

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
  it("exports the generated normalized backend error type", () => {
    expect(normalizedError.error.request_id).toBe("error-request");
  });

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
              details: normalizedError.error.details,
              request_id: "error-request",
              private_debug: "must not escape",
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
        details: normalizedError.error.details,
        requestId: "error-request",
      },
      status: 405,
      requestId: "header-request",
    });
    expect(JSON.stringify(result)).not.toContain("must not escape");
  });

  it.each([
    ["missing code", { message: "Safe.", details: {}, request_id: "error-request" }],
    ["missing message", { code: "INVALID", details: {}, request_id: "error-request" }],
    ["missing request ID", { code: "INVALID", message: "Safe.", details: {} }],
    [
      "invalid request ID type",
      { code: "INVALID", message: "Safe.", details: {}, request_id: 123 },
    ],
    [
      "nullable details outside the contract",
      { code: "INVALID", message: "Safe.", details: null, request_id: "error-request" },
    ],
    [
      "non-object details",
      { code: "INVALID", message: "Safe.", details: [], request_id: "error-request" },
    ],
  ])("rejects malformed normalized errors: %s", async (_name, error) => {
    const client = createTransLokaClient({
      fetch: () => Promise.resolve(jsonResponse({ error }, { status: 400 })),
    });

    await expect(client.getHealth()).resolves.toMatchObject({
      ok: false,
      error: { kind: "invalid-response" },
      status: 400,
    });
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

describe("project client", () => {
  it("returns only a valid generated project list envelope", async () => {
    const payload = {
      data: [project],
      meta: {
        request_id: "project-list",
        pagination: { limit: 100, offset: 0, total: 1, has_more: false },
      },
    } satisfies components["schemas"]["ProjectListResponse"];
    const fetchImplementation = vi.fn(
      (input: string | URL, init?: RequestInit) => {
        void input;
        void init;
        return Promise.resolve(jsonResponse(payload, { requestId: "project-list" }));
      },
    );
    const client = createTransLokaClient({ fetch: fetchImplementation });

    await expect(client.listProjects()).resolves.toEqual({
      ok: true,
      data: payload,
      status: 200,
      requestId: "project-list",
    });

    const call = fetchImplementation.mock.calls[0];
    if (call === undefined) {
      throw new Error("Expected the project client to call fetch.");
    }
    expect(call[0]).toBe(
      "http://127.0.0.1:8000/api/v1/projects?sort=updated_at&order=desc&limit=100&offset=0",
    );
    expect(new Headers(call[1]?.headers).has(CLIENT_HEADER)).toBe(false);
  });

  it("creates and archives projects with protected mutation requests", async () => {
    const payload = {
      data: project,
      meta: { request_id: "project-mutation" },
    } satisfies components["schemas"]["ProjectDataResponse"];
    const fetchImplementation = vi.fn(
      (input: string | URL, init?: RequestInit) => {
        void input;
        void init;
        return Promise.resolve(
          jsonResponse(payload, { requestId: "project-mutation" }),
        );
      },
    );
    const client = createTransLokaClient({ fetch: fetchImplementation });

    await client.createProject(createProjectInput);
    await client.archiveProject(project.id);

    const createCall = fetchImplementation.mock.calls[0];
    const archiveCall = fetchImplementation.mock.calls[1];
    if (createCall === undefined || archiveCall === undefined) {
      throw new Error("Expected create and archive requests.");
    }
    const createHeaders = new Headers(createCall[1]?.headers);
    expect(createCall[0]).toBe("http://127.0.0.1:8000/api/v1/projects");
    expect(createCall[1]?.body).toBe(JSON.stringify(createProjectInput));
    expect(createHeaders.get("Content-Type")).toBe("application/json");
    expect(createHeaders.get(CLIENT_HEADER)).toBe(CLIENT_HEADER_VALUE);
    expect(createHeaders.get(CLIENT_VERSION_HEADER)).toBe(
      CLIENT_VERSION_HEADER_VALUE,
    );
    expect(archiveCall[0]).toBe(
      `http://127.0.0.1:8000/api/v1/projects/${project.id}/archive`,
    );
  });

  it("rejects malformed project payloads and non-canonical project IDs", async () => {
    const client = createTransLokaClient({
      fetch: () =>
        Promise.resolve(
          jsonResponse({
            data: [{ ...project, progress: 4 }],
            meta: {
              request_id: "invalid-project",
              pagination: { limit: 100, offset: 0, total: 1, has_more: false },
            },
          }),
        ),
    });

    await expect(client.listProjects()).resolves.toMatchObject({
      ok: false,
      error: { kind: "invalid-response" },
    });
    expect(() => client.archiveProject("../../private")).toThrow(TypeError);
  });
});

describe("job client", () => {
  it("gets, lists, and reads attempts using generated response contracts", async () => {
    const payloads = [
      { data: job, meta: { request_id: "job-get" } },
      {
        data: [job],
        meta: {
          request_id: "job-list",
          pagination: { limit: 1, next_cursor: null, has_more: false },
        },
      },
      { data: [attempt], meta: { request_id: "job-attempts" } },
    ];
    const fetchImplementation = vi.fn(
      (input: string | URL, init?: RequestInit) => {
        void input;
        void init;
        const payload = payloads.shift();
        return Promise.resolve(
          jsonResponse(payload, payloads.length === 2 ? { retryAfter: "2" } : {}),
        );
      },
    );
    const client = createTransLokaClient({ fetch: fetchImplementation });

    await expect(client.getJob(job.id)).resolves.toMatchObject({
      ok: true,
      retryAfterSeconds: 2,
    });
    await expect(
      client.listJobs({
        limit: 1,
        projectId: project.id,
        jobType: "MAINTENANCE",
        status: "RUNNING",
      }),
    ).resolves.toMatchObject({ ok: true });
    await expect(client.getJobAttempts(job.id)).resolves.toMatchObject({ ok: true });

    expect(fetchImplementation.mock.calls.map(([url]) => url)).toEqual([
      `http://127.0.0.1:8000/api/v1/jobs/${job.id}`,
      `http://127.0.0.1:8000/api/v1/jobs?limit=1&project_id=${project.id}&job_type=MAINTENANCE&status=RUNNING`,
      `http://127.0.0.1:8000/api/v1/jobs/${job.id}/attempts`,
    ]);
  });

  it("rejects malformed job data and invalid identifiers before requests", async () => {
    const client = createTransLokaClient({
      fetch: () =>
        Promise.resolve(
          jsonResponse({ data: { ...job, progress: 4 }, meta: { request_id: "bad" } }),
        ),
    });

    await expect(client.getJob(job.id)).resolves.toMatchObject({
      ok: false,
      error: { kind: "invalid-response" },
    });
    expect(() => client.getJob("../../private")).toThrow(TypeError);
    expect(() => client.listJobs({ projectId: "../../private" })).toThrow(TypeError);
    expect(() => client.listJobs({ limit: 101 })).toThrow(RangeError);
  });
});
