import type { components, paths } from "./generated/schema";
import {
  ACCEPT_HEADER,
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  DEFAULT_API_BASE_URL,
  DEFAULT_REQUEST_TIMEOUT_MS,
  REQUEST_ID_HEADER,
} from "./constants";

type HealthResponse =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];
type ProjectDataResponse = components["schemas"]["ProjectDataResponse"];
type ProjectListResponse = components["schemas"]["ProjectListResponse"];
type GeneratedErrorBody = components["schemas"]["ErrorBody"];
type GeneratedErrorDetails = components["schemas"]["ErrorDetails"];
type GeneratedErrorResponse = components["schemas"]["ErrorResponse"];
type FetchImplementation = (input: string | URL, init?: RequestInit) => Promise<Response>;
type MutationMethod = "DELETE" | "PATCH" | "POST" | "PUT";

export type CreateProjectInput = components["schemas"]["CreateProjectRequest"];
export type ProjectResource = components["schemas"]["ProjectResponse"];

export type ApiError = Omit<GeneratedErrorBody, "request_id"> & {
  requestId: GeneratedErrorBody["request_id"];
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
const PROJECT_ID_PATTERN =
  /^prj_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SAFE_MESSAGE_PATTERN = /^[^\u0000-\u001F\u007F]{1,512}$/;
const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}$/;
const MUTATION_METHODS: ReadonlySet<string> = new Set<MutationMethod>([
  "DELETE",
  "PATCH",
  "POST",
  "PUT",
]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);
const PROJECT_STATUSES = new Set<ProjectResource["status"]>([
  "CREATED",
  "IMPORTING",
  "ANALYZING",
  "WAITING_FOR_SETTINGS",
  "EXTRACTING",
  "OCR_PROCESSING",
  "TERMS_DETECTED",
  "WAITING_FOR_GLOSSARY",
  "TRANSLATING",
  "READY_FOR_REVIEW",
  "REVIEWING",
  "RECONSTRUCTING",
  "READY_FOR_EXPORT",
  "COMPLETED",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "ARCHIVED",
  "DELETION_QUEUED",
]);
const DOCUMENT_TYPES = new Set<ProjectResource["document_type"]>([
  "ACADEMIC_PAPER",
  "ACADEMIC_BOOK",
  "TECHNICAL_BOOK",
  "USER_MANUAL",
  "BUSINESS_REPORT",
  "LEGAL_DOCUMENT",
  "FICTION_BOOK",
  "NONFICTION_BOOK",
  "PRESENTATION_EXPORT",
  "BROCHURE",
  "FORM",
  "COMIC_OR_GRAPHIC_BOOK",
  "GENERAL_DOCUMENT",
  "UNKNOWN",
]);
const TRANSLATION_STYLES = new Set<ProjectResource["translation_style"]>([
  "LITERAL",
  "PROFESSIONAL",
  "ACADEMIC",
  "NATURAL",
]);
const RECONSTRUCTION_MODES = new Set<ProjectResource["reconstruction_mode"]>([
  "OVERLAY",
  "REFLOW",
  "HYBRID",
]);

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

function isErrorDetailValue(value: unknown): boolean {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.every(isErrorDetailValue);
  }
  return isRecord(value) && Object.values(value).every(isErrorDetailValue);
}

function isErrorDetails(value: unknown): value is GeneratedErrorDetails {
  return isRecord(value) && Object.values(value).every(isErrorDetailValue);
}

function isErrorResponse(value: unknown): value is GeneratedErrorResponse {
  if (!isRecord(value) || !isRecord(value.error)) {
    return false;
  }

  const error = value.error;
  return (
    typeof error.code === "string" &&
    ERROR_CODE_PATTERN.test(error.code) &&
    typeof error.message === "string" &&
    SAFE_MESSAGE_PATTERN.test(error.message) &&
    isErrorDetails(error.details) &&
    typeof error.request_id === "string" &&
    REQUEST_ID_PATTERN.test(error.request_id)
  );
}

function parseApiError(value: unknown): ApiError | null {
  if (!isErrorResponse(value)) {
    return null;
  }

  const error = value.error;
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

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isProjectResource(value: unknown): value is ProjectResource {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    PROJECT_ID_PATTERN.test(value.id) &&
    typeof value.name === "string" &&
    value.name.length > 0 &&
    isNullableString(value.description) &&
    typeof value.status === "string" &&
    PROJECT_STATUSES.has(value.status as ProjectResource["status"]) &&
    typeof value.source_language === "string" &&
    value.source_language.length > 0 &&
    typeof value.target_language === "string" &&
    value.target_language.length > 0 &&
    typeof value.document_type === "string" &&
    DOCUMENT_TYPES.has(value.document_type as ProjectResource["document_type"]) &&
    typeof value.translation_style === "string" &&
    TRANSLATION_STYLES.has(
      value.translation_style as ProjectResource["translation_style"],
    ) &&
    typeof value.reconstruction_mode === "string" &&
    RECONSTRUCTION_MODES.has(
      value.reconstruction_mode as ProjectResource["reconstruction_mode"],
    ) &&
    typeof value.progress === "number" &&
    Number.isFinite(value.progress) &&
    value.progress >= 0 &&
    value.progress <= 1 &&
    isNullableString(value.active_document_id) &&
    isRecord(value.settings) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isResponseMeta(
  value: unknown,
): value is Record<string, unknown> & components["schemas"]["ResponseMeta"] {
  return (
    isRecord(value) &&
    typeof value.request_id === "string" &&
    REQUEST_ID_PATTERN.test(value.request_id)
  );
}

function isProjectDataResponse(value: unknown): value is ProjectDataResponse {
  return isRecord(value) && isProjectResource(value.data) && isResponseMeta(value.meta);
}

function isProjectListResponse(value: unknown): value is ProjectListResponse {
  if (
    !isRecord(value) ||
    !Array.isArray(value.data) ||
    !value.data.every(isProjectResource) ||
    !isRecord(value.meta) ||
    !isRecord(value.meta.pagination) ||
    !isResponseMeta(value.meta)
  ) {
    return false;
  }

  const pagination = value.meta.pagination;
  return (
    typeof pagination.limit === "number" &&
    Number.isInteger(pagination.limit) &&
    pagination.limit >= 1 &&
    typeof pagination.offset === "number" &&
    Number.isInteger(pagination.offset) &&
    pagination.offset >= 0 &&
    typeof pagination.total === "number" &&
    Number.isInteger(pagination.total) &&
    pagination.total >= 0 &&
    typeof pagination.has_more === "boolean"
  );
}

function projectPath(projectId: string, action: "archive" | "unarchive"): string {
  if (!PROJECT_ID_PATTERN.test(projectId)) {
    throw new TypeError("Project ID must use the canonical prefixed UUID format.");
  }
  return `/api/v1/projects/${projectId}/${action}`;
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

type ClientRequest<T> = {
  body?: unknown;
  invalidResponseMessage: string;
  method: "GET" | MutationMethod;
  path: string;
  validate: (value: unknown) => value is T;
};

export function createTransLokaClient(options: TransLokaClientOptions = {}) {
  const baseUrl = validateBaseUrl(options.baseUrl ?? DEFAULT_API_BASE_URL);
  const fetchImplementation = options.fetch ?? globalThis.fetch;
  const defaultTimeout = boundedTimeout(options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS);

  async function request<T>(
    definition: ClientRequest<T>,
    requestOptions: RequestOptions,
  ): Promise<ApiResult<T>> {
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
      const headers = createRequestHeaders(definition.method, requestOptions.requestId);
      const init: RequestInit = {
        cache: "no-store",
        credentials: "omit",
        headers,
        method: definition.method,
        signal: controller.signal,
      };
      if (definition.body !== undefined) {
        headers.set("Content-Type", "application/json");
        init.body = JSON.stringify(definition.body);
      }

      const response = await fetchImplementation(`${baseUrl}${definition.path}`, init);
      const responseRequestId = response.headers.get(REQUEST_ID_HEADER);
      const payload = await parseJson(response);

      if (response.ok) {
        if (definition.validate(payload)) {
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
            message: definition.invalidResponseMessage,
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
  }

  return {
    getHealth(requestOptions: RequestOptions = {}): Promise<ApiResult<HealthResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated health contract.",
          method: "GET",
          path: "/health",
          validate: isHealthResponse,
        },
        requestOptions,
      );
    },

    listProjects(
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<ProjectListResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated project list contract.",
          method: "GET",
          path: "/api/v1/projects?sort=updated_at&order=desc&limit=100&offset=0",
          validate: isProjectListResponse,
        },
        requestOptions,
      );
    },

    createProject(
      input: CreateProjectInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<ProjectDataResponse>> {
      return request(
        {
          body: input,
          invalidResponseMessage:
            "The API response did not match the generated project contract.",
          method: "POST",
          path: "/api/v1/projects",
          validate: isProjectDataResponse,
        },
        requestOptions,
      );
    },

    archiveProject(
      projectId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<ProjectDataResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated project contract.",
          method: "POST",
          path: projectPath(projectId, "archive"),
          validate: isProjectDataResponse,
        },
        requestOptions,
      );
    },

    unarchiveProject(
      projectId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<ProjectDataResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated project contract.",
          method: "POST",
          path: projectPath(projectId, "unarchive"),
          validate: isProjectDataResponse,
        },
        requestOptions,
      );
    },
  };
}
