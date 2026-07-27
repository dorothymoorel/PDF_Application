import type { paths } from "./generated/schema.js";
import {
  ACCEPT_HEADER,
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  DEFAULT_API_BASE_URL,
  DEFAULT_REQUEST_TIMEOUT_MS,
  REQUEST_ID_HEADER,
} from "./constants.js";

type HealthResponse =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];
type FetchImplementation = (input: string | URL, init?: RequestInit) => Promise<Response>;
type MutationMethod = "DELETE" | "PATCH" | "POST" | "PUT";

export type ApiError = {
  code: string;
  message: string;
  details: Record<string, unknown>;
  requestId: string;
};

export type ApiClientError =
  | ({ kind: "api" } & ApiError)
  | { kind: "invalid-response"; message: string }
  | { kind: "network"; message: string }
  | { kind: "timeout"; message: string }
  | { kind: "aborted"; message: string };

export type ApiResult<T> =
  | { ok: true; data: T; status: number; requestId: string | null }
  | {
      ok: false;
      error: ApiClientError;
      status: number | null;
      requestId: string | null;
    };

export type RequestOptions = {
  requestId?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type TransLokaClientOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
  timeoutMs?: number;
};

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;
const ERROR_CODE_PATTERN = /^[A-Z0-9_]{1,64}$/;
const SAFE_MESSAGE_PATTERN = /^[^\u0000-\u001F\u007F]{1,512}$/;
const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}$/;
const MUTATION_METHODS: ReadonlySet<string> = new Set<MutationMethod>([
  "DELETE",
  "PATCH",
  "POST",
  "PUT",
]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

function boundedTimeout(value: number): number {
  if (!Number.isInteger(value) || value < 1 || value > 60_000) {
    throw new RangeError("Request timeout must be between 1 and 60000 milliseconds.");
  }
  return value;
}

export function validateBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new TypeError("API base URL must be a valid local HTTP origin.");
  }

  if (
    url.protocol !== "http:" ||
    !LOOPBACK_HOSTS.has(url.hostname) ||
    url.username !== "" ||
    url.password !== "" ||
    url.pathname !== "/" ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new TypeError("API base URL must be a loopback-only HTTP origin.");
  }

  return url.origin;
}

function requestId(value?: string): string {
  if (value !== undefined) {
    const candidate = value.trim();
    if (REQUEST_ID_PATTERN.test(candidate)) {
      return candidate;
    }
  }
  return globalThis.crypto.randomUUID();
}

export function createRequestHeaders(method: string, suppliedRequestId?: string): Headers {
  const headers = new Headers({
    [ACCEPT_HEADER]: "application/json",
    [REQUEST_ID_HEADER]: requestId(suppliedRequestId),
  });

  if (MUTATION_METHODS.has(method.toUpperCase())) {
    headers.set(CLIENT_HEADER, CLIENT_HEADER_VALUE);
    headers.set(CLIENT_VERSION_HEADER, CLIENT_VERSION_HEADER_VALUE);
  }

  return headers;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseApiError(value: unknown): ApiError | null {
  if (!isRecord(value) || !isRecord(value.error)) {
    return null;
  }

  const error = value.error;
  if (
    typeof error.code !== "string" ||
    !ERROR_CODE_PATTERN.test(error.code) ||
    typeof error.message !== "string" ||
    !SAFE_MESSAGE_PATTERN.test(error.message) ||
    !isRecord(error.details) ||
    typeof error.request_id !== "string" ||
    !REQUEST_ID_PATTERN.test(error.request_id)
  ) {
    return null;
  }

  return {
    code: error.code,
    message: error.message,
    details: error.details,
    requestId: error.request_id,
  };
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    isRecord(value) &&
    value.status === "ok" &&
    value.service === "transloka-api" &&
    typeof value.version === "string" &&
    VERSION_PATTERN.test(value.version)
  );
}

async function parseJson(response: Response): Promise<unknown> {
  if (!response.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return undefined;
  }

  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export function createTransLokaClient(options: TransLokaClientOptions = {}) {
  const baseUrl = validateBaseUrl(options.baseUrl ?? DEFAULT_API_BASE_URL);
  const fetchImplementation = options.fetch ?? globalThis.fetch;
  const defaultTimeout = boundedTimeout(options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS);

  return {
    async getHealth(requestOptions: RequestOptions = {}): Promise<ApiResult<HealthResponse>> {
      if (requestOptions.signal?.aborted) {
        return {
          ok: false,
          error: { kind: "aborted", message: "The request was cancelled." },
          status: null,
          requestId: null,
        };
      }

      const controller = new AbortController();
      const timeoutMs = boundedTimeout(requestOptions.timeoutMs ?? defaultTimeout);
      let timedOut = false;
      const abort = () => controller.abort();
      requestOptions.signal?.addEventListener("abort", abort, { once: true });
      const timeout = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);

      try {
        const response = await fetchImplementation(`${baseUrl}/health`, {
          cache: "no-store",
          credentials: "omit",
          headers: createRequestHeaders("GET", requestOptions.requestId),
          method: "GET",
          signal: controller.signal,
        });
        const responseRequestId = response.headers.get(REQUEST_ID_HEADER);
        const payload = await parseJson(response);

        if (response.ok) {
          if (isHealthResponse(payload)) {
            return {
              ok: true,
              data: payload,
              status: response.status,
              requestId: responseRequestId,
            };
          }
          return {
            ok: false,
            error: {
              kind: "invalid-response",
              message: "The API response did not match the generated health contract.",
            },
            status: response.status,
            requestId: responseRequestId,
          };
        }

        const apiError = parseApiError(payload);
        if (apiError !== null) {
          return {
            ok: false,
            error: { kind: "api", ...apiError },
            status: response.status,
            requestId: responseRequestId ?? apiError.requestId,
          };
        }
        return {
          ok: false,
          error: {
            kind: "invalid-response",
            message: "The API returned an invalid error response.",
          },
          status: response.status,
          requestId: responseRequestId,
        };
      } catch {
        if (requestOptions.signal?.aborted) {
          return {
            ok: false,
            error: { kind: "aborted", message: "The request was cancelled." },
            status: null,
            requestId: null,
          };
        }
        if (timedOut) {
          return {
            ok: false,
            error: { kind: "timeout", message: "The local API did not respond in time." },
            status: null,
            requestId: null,
          };
        }
        return {
          ok: false,
          error: { kind: "network", message: "The local API could not be reached." },
          status: null,
          requestId: null,
        };
      } finally {
        clearTimeout(timeout);
        requestOptions.signal?.removeEventListener("abort", abort);
      }
    },
  };
}
