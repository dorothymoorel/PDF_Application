import type { components, paths } from "./generated/schema";
import {
  ACCEPT_HEADER,
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  DEFAULT_API_BASE_URL,
  DEFAULT_REQUEST_TIMEOUT_MS,
  IDEMPOTENCY_KEY_HEADER,
  REQUEST_ID_HEADER,
} from "./constants";

type HealthResponse =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];
type JobAttemptListResponse = components["schemas"]["JobAttemptListResponse"];
type JobDataResponse = components["schemas"]["JobDataResponse"];
type JobListResponse = components["schemas"]["JobListResponse"];
type ProjectDataResponse = components["schemas"]["ProjectDataResponse"];
type ProjectListResponse = components["schemas"]["ProjectListResponse"];
type TranslationJobResponse = components["schemas"]["TranslationJobResponse"];
type TranslationReadinessResponse = components["schemas"]["TranslationReadinessResponse"];
type TranslationStatusResponse = components["schemas"]["TranslationStatusResponse"];
type GeneratedErrorBody = components["schemas"]["ErrorBody"];
type GeneratedErrorDetails = components["schemas"]["ErrorDetails"];
type GeneratedErrorResponse = components["schemas"]["ErrorResponse"];
type FetchImplementation = (input: string | URL, init?: RequestInit) => Promise<Response>;
type MutationMethod = "DELETE" | "PATCH" | "POST" | "PUT";

export type CreateProjectInput = components["schemas"]["CreateProjectRequest"];
export type CancelJobInput = components["schemas"]["CancelJobRequest"];
export type JobAttemptResource = components["schemas"]["JobAttemptResponse"];
export type JobResource = components["schemas"]["JobResponse"];
export type ProjectResource = components["schemas"]["ProjectResponse"];
export type RetryJobInput = components["schemas"]["RetryJobRequest"];
export type CancelTranslationInput = components["schemas"]["CancelTranslationRequest"];
export type RetryTranslationInput = components["schemas"]["RetryTranslationRequest"];
export type StartTranslationInput = components["schemas"]["StartTranslationRequest"];

export type JobListOptions = {
  cursor?: string;
  documentId?: string;
  jobType?: JobResource["job_type"];
  limit?: number;
  projectId?: string;
  status?: JobResource["status"];
};

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
  | {
      ok: true;
      data: T;
      status: number;
      requestId: string | null;
      retryAfterSeconds?: number;
    }
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
const DOCUMENT_ID_PATTERN =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const JOB_ID_PATTERN =
  /^job_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SAFE_MESSAGE_PATTERN = /^[^\u0000-\u001F\u007F]{1,512}$/;
const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}$/;
const MUTATION_METHODS: ReadonlySet<string> = new Set<MutationMethod>([
  "DELETE",
  "PATCH",
  "POST",
  "PUT",
]);
const MAX_IDEMPOTENCY_KEY_LENGTH = 200;
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
const JOB_TYPES = new Set<JobResource["job_type"]>([
  "IMPORT_DOCUMENT",
  "ANALYZE_DOCUMENT",
  "OCR_DOCUMENT",
  "DETECT_TERMS",
  "TRANSLATE_DOCUMENT",
  "RECONSTRUCT_DOCUMENT",
  "EXPORT_DOCUMENT",
  "BENCHMARK_MODEL",
  "BACKUP_DATABASE",
  "RESTORE_DATABASE",
  "MAINTENANCE",
]);
const JOB_STATUSES = new Set<JobResource["status"]>([
  "CREATED",
  "QUEUED",
  "RUNNING",
  "RETRYING",
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLATION_REQUESTED",
  "CANCELLED",
  "STALE",
]);
const JOB_ATTEMPT_STATUSES = new Set<JobAttemptResource["status"]>([
  "RUNNING",
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
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

function idempotencyKey(value: string): string {
  if (
    value.length < 1 ||
    value.length > MAX_IDEMPOTENCY_KEY_LENGTH ||
    value !== value.trim() ||
    !SAFE_MESSAGE_PATTERN.test(value)
  ) {
    throw new TypeError("Idempotency key is invalid.");
  }
  return value;
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

function parseRetryAfter(value: string | null): number | undefined {
  if (value === null || !/^\d{1,3}$/.test(value)) {
    return undefined;
  }
  const seconds = Number(value);
  return seconds <= 300 ? seconds : undefined;
}

function isResourceError(value: unknown): boolean {
  return (
    value === null ||
    (isRecord(value) &&
      typeof value.code === "string" &&
      ERROR_CODE_PATTERN.test(value.code) &&
      typeof value.message === "string" &&
      SAFE_MESSAGE_PATTERN.test(value.message))
  );
}

function isJobResource(value: unknown): value is JobResource {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    JOB_ID_PATTERN.test(value.id) &&
    typeof value.job_type === "string" &&
    JOB_TYPES.has(value.job_type as JobResource["job_type"]) &&
    typeof value.status === "string" &&
    JOB_STATUSES.has(value.status as JobResource["status"]) &&
    typeof value.progress === "number" &&
    Number.isFinite(value.progress) &&
    value.progress >= 0 &&
    value.progress <= 1 &&
    isNullableString(value.current_stage) &&
    (value.project_id === null ||
      (typeof value.project_id === "string" &&
        PROJECT_ID_PATTERN.test(value.project_id))) &&
    (value.document_id === null ||
      (typeof value.document_id === "string" &&
        DOCUMENT_ID_PATTERN.test(value.document_id))) &&
    Number.isInteger(value.retry_count) &&
    typeof value.retry_count === "number" &&
    value.retry_count >= 0 &&
    Number.isInteger(value.max_retries) &&
    typeof value.max_retries === "number" &&
    value.max_retries >= 0 &&
    typeof value.created_at === "string" &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isResourceError(value.error)
  );
}

function isJobAttemptResource(value: unknown): value is JobAttemptResource {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.attempt_number === "number" &&
    Number.isInteger(value.attempt_number) &&
    value.attempt_number >= 1 &&
    typeof value.status === "string" &&
    JOB_ATTEMPT_STATUSES.has(value.status as JobAttemptResource["status"]) &&
    typeof value.started_at === "string" &&
    isNullableString(value.completed_at) &&
    (value.duration_ms === null ||
      (typeof value.duration_ms === "number" &&
        Number.isInteger(value.duration_ms) &&
        value.duration_ms >= 0)) &&
    isResourceError(value.error)
  );
}

function isJobDataResponse(value: unknown): value is JobDataResponse {
  return isRecord(value) && isJobResource(value.data) && isResponseMeta(value.meta);
}

function isTranslationJobResponse(value: unknown): value is TranslationJobResponse {
  if (!isRecord(value) || !isRecord(value.data) || !isResponseMeta(value.meta)) {
    return false;
  }
  return (
    typeof value.data.job_id === "string" &&
    JOB_ID_PATTERN.test(value.data.job_id) &&
    typeof value.data.status === "string" &&
    JOB_STATUSES.has(value.data.status as JobResource["status"])
  );
}

function isTranslationReadinessResponse(value: unknown): value is TranslationReadinessResponse {
  if (
    !isRecord(value) ||
    !isRecord(value.data) ||
    !isResponseMeta(value.meta) ||
    typeof value.data.ready !== "boolean" ||
    !Array.isArray(value.data.blocking_issues) ||
    !Array.isArray(value.data.warnings) ||
    typeof value.data.segment_count !== "number" ||
    !Number.isInteger(value.data.segment_count) ||
    value.data.segment_count < 0 ||
    typeof value.data.estimated_batches !== "number" ||
    !Number.isInteger(value.data.estimated_batches) ||
    value.data.estimated_batches < 0
  ) {
    return false;
  }
  return (
    value.data.blocking_issues.every(
      (issue) =>
        isRecord(issue) &&
        typeof issue.code === "string" &&
        ERROR_CODE_PATTERN.test(issue.code) &&
        typeof issue.message === "string" &&
        SAFE_MESSAGE_PATTERN.test(issue.message),
    ) &&
    value.data.warnings.every(
      (warning) =>
        isRecord(warning) &&
        typeof warning.code === "string" &&
        ERROR_CODE_PATTERN.test(warning.code) &&
        typeof warning.count === "number" &&
        Number.isInteger(warning.count) &&
        warning.count >= 0,
    )
  );
}

function isTranslationStatusResponse(value: unknown): value is TranslationStatusResponse {
  if (!isRecord(value) || !isRecord(value.data) || !isResponseMeta(value.meta)) {
    return false;
  }
  const data = value.data;
  return (
    typeof data.status === "string" &&
    SAFE_MESSAGE_PATTERN.test(data.status) &&
    (data.active_job_id === null ||
      (typeof data.active_job_id === "string" && JOB_ID_PATTERN.test(data.active_job_id))) &&
    [
      data.total_segments,
      data.completed_segments,
      data.failed_segments,
      data.review_required_segments,
      data.current_batch,
      data.total_batches,
    ].every((item) => typeof item === "number" && Number.isInteger(item) && item >= 0) &&
    typeof data.progress === "number" &&
    Number.isFinite(data.progress) &&
    data.progress >= 0 &&
    data.progress <= 1
  );
}

function isJobListResponse(value: unknown): value is JobListResponse {
  if (
    !isRecord(value) ||
    !Array.isArray(value.data) ||
    !value.data.every(isJobResource) ||
    !isRecord(value.meta) ||
    !isResponseMeta(value.meta) ||
    !isRecord(value.meta.pagination)
  ) {
    return false;
  }
  const pagination = value.meta.pagination;
  return (
    typeof pagination.limit === "number" &&
    Number.isInteger(pagination.limit) &&
    pagination.limit >= 1 &&
    pagination.limit <= 100 &&
    isNullableString(pagination.next_cursor) &&
    typeof pagination.has_more === "boolean"
  );
}

function isJobAttemptListResponse(value: unknown): value is JobAttemptListResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.data) &&
    value.data.every(isJobAttemptResource) &&
    isResponseMeta(value.meta)
  );
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

function jobPath(jobId: string, suffix = ""): string {
  if (!JOB_ID_PATTERN.test(jobId)) {
    throw new TypeError("Job ID must use the canonical prefixed UUID format.");
  }
  return `/api/v1/jobs/${jobId}${suffix}`;
}

function translationPath(projectId: string, suffix: string): string {
  if (!PROJECT_ID_PATTERN.test(projectId)) {
    throw new TypeError("Project ID must use the canonical prefixed UUID format.");
  }
  return `/api/v1/projects/${projectId}/translation${suffix}`;
}

function translationReadinessPath(projectId: string): string {
  if (!PROJECT_ID_PATTERN.test(projectId)) {
    throw new TypeError("Project ID must use the canonical prefixed UUID format.");
  }
  return `/api/v1/projects/${projectId}/translation-readiness`;
}

function jobListPath(options: JobListOptions): string {
  const query = new URLSearchParams();
  const limit = options.limit ?? 50;
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new RangeError("Job list limit must be between 1 and 100.");
  }
  query.set("limit", String(limit));
  if (options.projectId !== undefined) {
    if (!PROJECT_ID_PATTERN.test(options.projectId)) {
      throw new TypeError("Project ID must use the canonical prefixed UUID format.");
    }
    query.set("project_id", options.projectId);
  }
  if (options.documentId !== undefined) {
    if (!DOCUMENT_ID_PATTERN.test(options.documentId)) {
      throw new TypeError("Document ID must use the canonical prefixed UUID format.");
    }
    query.set("document_id", options.documentId);
  }
  if (options.jobType !== undefined) {
    query.set("job_type", options.jobType);
  }
  if (options.status !== undefined) {
    query.set("status", options.status);
  }
  if (options.cursor !== undefined) {
    if (options.cursor.length < 1 || options.cursor.length > 1024) {
      throw new TypeError("Job cursor is invalid.");
    }
    query.set("cursor", options.cursor);
  }
  return `/api/v1/jobs?${query.toString()}`;
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
  headers?: Readonly<Record<string, string>>;
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
      for (const [name, value] of Object.entries(definition.headers ?? {})) {
        headers.set(name, value);
      }
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
          const retryAfterSeconds = parseRetryAfter(
            response.headers.get("Retry-After"),
          );
          return {
            ok: true,
            data: payload,
            status: response.status,
            requestId: responseRequestId,
            ...(retryAfterSeconds === undefined ? {} : { retryAfterSeconds }),
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

    getJob(
      jobId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<JobDataResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated job contract.",
          method: "GET",
          path: jobPath(jobId),
          validate: isJobDataResponse,
        },
        requestOptions,
      );
    },

    listJobs(
      options: JobListOptions = {},
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<JobListResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated job list contract.",
          method: "GET",
          path: jobListPath(options),
          validate: isJobListResponse,
        },
        requestOptions,
      );
    },

    getJobAttempts(
      jobId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<JobAttemptListResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated job attempt contract.",
          method: "GET",
          path: jobPath(jobId, "/attempts"),
          validate: isJobAttemptListResponse,
        },
        requestOptions,
      );
    },

    cancelJob(
      jobId: string,
      input: CancelJobInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<JobDataResponse>> {
      return request(
        {
          body: input,
          invalidResponseMessage:
            "The API response did not match the generated job contract.",
          method: "POST",
          path: jobPath(jobId, "/cancel"),
          validate: isJobDataResponse,
        },
        requestOptions,
      );
    },

    retryJob(
      jobId: string,
      retryKey: string,
      input: RetryJobInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<JobDataResponse>> {
      return request(
        {
          body: input,
          headers: { [IDEMPOTENCY_KEY_HEADER]: idempotencyKey(retryKey) },
          invalidResponseMessage:
            "The API response did not match the generated job contract.",
          method: "POST",
          path: jobPath(jobId, "/retry"),
          validate: isJobDataResponse,
        },
        requestOptions,
      );
    },

    getTranslationReadiness(
      projectId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<TranslationReadinessResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated translation readiness contract.",
          method: "GET",
          path: translationReadinessPath(projectId),
          validate: isTranslationReadinessResponse,
        },
        requestOptions,
      );
    },

    startTranslation(
      projectId: string,
      startKey: string,
      input: StartTranslationInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<TranslationJobResponse>> {
      return request(
        {
          body: input,
          headers: { [IDEMPOTENCY_KEY_HEADER]: idempotencyKey(startKey) },
          invalidResponseMessage:
            "The API response did not match the generated translation start contract.",
          method: "POST",
          path: translationPath(projectId, "/start"),
          validate: isTranslationJobResponse,
        },
        requestOptions,
      );
    },

    getTranslationStatus(
      projectId: string,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<TranslationStatusResponse>> {
      return request(
        {
          invalidResponseMessage:
            "The API response did not match the generated translation status contract.",
          method: "GET",
          path: translationPath(projectId, "/status"),
          validate: isTranslationStatusResponse,
        },
        requestOptions,
      );
    },

    cancelTranslation(
      projectId: string,
      input: CancelTranslationInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<TranslationStatusResponse>> {
      return request(
        {
          body: input,
          invalidResponseMessage:
            "The API response did not match the generated translation status contract.",
          method: "POST",
          path: translationPath(projectId, "/cancel"),
          validate: isTranslationStatusResponse,
        },
        requestOptions,
      );
    },

    retryFailedTranslation(
      projectId: string,
      retryKey: string,
      input: RetryTranslationInput,
      requestOptions: RequestOptions = {},
    ): Promise<ApiResult<TranslationStatusResponse>> {
      return request(
        {
          body: input,
          headers: { [IDEMPOTENCY_KEY_HEADER]: idempotencyKey(retryKey) },
          invalidResponseMessage:
            "The API response did not match the generated translation status contract.",
          method: "POST",
          path: translationPath(projectId, "/retry-failed"),
          validate: isTranslationStatusResponse,
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
