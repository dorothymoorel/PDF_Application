import {
  createRequestHeaders,
  createTransLokaClient,
  DEFAULT_API_BASE_URL,
  IDEMPOTENCY_KEY_HEADER,
  REQUEST_ID_HEADER,
  validateBaseUrl,
  type ApiResult,
  type components,
} from "@transloka/api-client";

import type {
  BackupListResponse,
  CreateBackupInput,
  CreateBackupResponse,
  RestoreBackupInput,
  RestoreBackupResponse,
  VerifyBackupResponse,
} from "../../src/features/backups/backup-panel";
import type { ExportRecord } from "../../src/features/exports/types";
import type { OCRReviewResponse, SourceResolutionInput, SourceResolutionResponse } from "../../src/features/ocr/types";
import type { ReviewPageResponse, SaveSegmentTranslationInput, SegmentDataResponse } from "../../src/features/editor/types";
import type { ReviewQueueQueryFilters, ReviewQueueResponse } from "../../src/features/review-queue/types";

type FetchImplementation = (input: string | URL, init?: RequestInit) => Promise<Response>;
type RequestOptions = { signal?: AbortSignal };
type PageListResponse = components["schemas"]["DocumentPageListResponse"];
type PageResource = components["schemas"]["PageEditorPageResponse"];

export type OCRStatus = {
  active_job_id: string | null;
  completed_pages: number;
  current_stage: string | null;
  failed_pages: number;
  progress: number;
  selected_pages: number;
  status: string;
};

export type OCRStatusResponse = {
  data: OCRStatus;
  meta: { request_id: string };
};

export type OCRJobResponse = {
  data: { job_id: string; status: string };
  meta: { request_id: string };
};

type WorkspaceClientOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
};

const SAFE_ID = /^(?:prj|doc|pag|seg|exp|bkp|job)_[0-9a-f-]{36}$/u;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMeta(value: unknown): value is { request_id: string } {
  return isRecord(value) && typeof value.request_id === "string" && value.request_id.length > 0;
}

function isEnvelope(value: unknown, validateData: (data: unknown) => boolean): boolean {
  return isRecord(value) && validateData(value.data) && isMeta(value.meta);
}

function isPage(value: unknown): value is PageResource {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    SAFE_ID.test(value.id) &&
    typeof value.document_id === "string" &&
    SAFE_ID.test(value.document_id) &&
    Number.isInteger(value.source_page_number) &&
    isRecord(value.preview)
  );
}

function isPageListResponse(value: unknown): value is PageListResponse {
  return isEnvelope(value, (data) => Array.isArray(data) && data.every(isPage));
}

function isOCRStatusResponse(value: unknown): value is OCRStatusResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.status === "string" &&
      typeof data.progress === "number" &&
      data.progress >= 0 &&
      data.progress <= 1 &&
      Number.isInteger(data.selected_pages) &&
      Number.isInteger(data.completed_pages) &&
      Number.isInteger(data.failed_pages) &&
      (data.active_job_id === null || typeof data.active_job_id === "string"),
  );
}

function isJobEnvelope(value: unknown): value is OCRJobResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.job_id === "string" &&
      SAFE_ID.test(data.job_id) &&
      typeof data.status === "string",
  );
}

function isOCRPageResponse(value: unknown): value is OCRReviewResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.page_id === "string" &&
      typeof data.raw_text === "string" &&
      typeof data.resolved_source_text === "string" &&
      Array.isArray(data.segments) &&
      data.segments.every(
        (segment) =>
          isRecord(segment) &&
          typeof segment.id === "string" &&
          typeof segment.resolved_source_text === "string" &&
          typeof segment.current_revision === "number",
      ),
  );
}

function isSourceResolutionResponse(value: unknown): value is SourceResolutionResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.id === "string" &&
      typeof data.resolved_source_text === "string" &&
      typeof data.current_revision === "number",
  );
}

function isReviewQueueResponse(value: unknown): value is ReviewQueueResponse {
  return isEnvelope(
    value,
    (data) =>
      Array.isArray(data) &&
      data.every(
        (item) =>
          isRecord(item) &&
          typeof item.page_id === "string" &&
          isRecord(item.segment) &&
          typeof item.segment.id === "string" &&
          Array.isArray(item.warnings) &&
          isRecord(item.source_context),
      ),
  );
}

function isReviewPageResponse(value: unknown): value is ReviewPageResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      isPage(data.page) &&
      Array.isArray(data.blocks) &&
      Array.isArray(data.segments) &&
      Array.isArray(data.warnings),
  );
}

function isSegmentDataResponse(value: unknown): value is SegmentDataResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.id === "string" &&
      typeof data.resolved_source_text === "string" &&
      typeof data.current_revision === "number",
  );
}

function isExportRecord(value: unknown): value is ExportRecord {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.filename === "string" &&
    typeof value.status === "string" &&
    typeof value.output_profile === "string" &&
    typeof value.version_number === "number" &&
    (value.checksum_sha256 === null || typeof value.checksum_sha256 === "string")
  );
}

function isExportListResponse(value: unknown): value is { data: ExportRecord[] } {
  return isEnvelope(value, (data) => Array.isArray(data) && data.every(isExportRecord));
}

function isBackupListResponse(value: unknown): value is BackupListResponse {
  return isEnvelope(
    value,
    (data) =>
      Array.isArray(data) &&
      data.every(
        (backup) =>
          isRecord(backup) &&
          typeof backup.id === "string" &&
          typeof backup.backup_type === "string" &&
          typeof backup.status === "string" &&
          typeof backup.filename === "string",
      ),
  );
}

function isCreateBackupResponse(value: unknown): value is CreateBackupResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.job_id === "string" &&
      (data.backup_id === null || typeof data.backup_id === "string") &&
      typeof data.status === "string",
  );
}

function isVerifyBackupResponse(value: unknown): value is VerifyBackupResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.backup_id === "string" &&
      data.status === "VERIFIED" &&
      typeof data.message === "string",
  );
}

function isRestoreBackupResponse(value: unknown): value is RestoreBackupResponse {
  return isEnvelope(
    value,
    (data) =>
      isRecord(data) &&
      typeof data.job_id === "string" &&
      typeof data.backup_id === "string" &&
      data.status === "COMPLETED" &&
      typeof data.pre_restore_backup_id === "string",
  );
}

function queryString(filters: ReviewQueueQueryFilters): string {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value !== undefined) query.set(name, String(value));
  }
  const serialized = query.toString();
  return serialized === "" ? "" : `?${serialized}`;
}

export function createWorkspaceClient(options: WorkspaceClientOptions = {}) {
  const baseUrl = validateBaseUrl(options.baseUrl ?? DEFAULT_API_BASE_URL);
  const fetchImplementation = options.fetch ?? globalThis.fetch.bind(globalThis);
  const core = createTransLokaClient({ baseUrl, fetch: fetchImplementation });

  async function request<T>(
    path: string,
    method: "GET" | "PATCH" | "POST",
    validate: (value: unknown) => value is T,
    requestOptions: RequestOptions = {},
    body?: unknown,
    idempotencyKey?: string,
  ): Promise<ApiResult<T>> {
    try {
      const headers = createRequestHeaders(method);
      if (idempotencyKey !== undefined) headers.set(IDEMPOTENCY_KEY_HEADER, idempotencyKey);
      const init: RequestInit = {
        cache: "no-store",
        credentials: "omit",
        headers,
        method,
        ...(requestOptions.signal === undefined ? {} : { signal: requestOptions.signal }),
      };
      if (body !== undefined) {
        headers.set("Content-Type", "application/json");
        init.body = JSON.stringify(body);
      }
      const response = await fetchImplementation(`${baseUrl}${path}`, init);
      const requestId = response.headers.get(REQUEST_ID_HEADER);
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = undefined;
      }
      if (response.ok && validate(payload)) {
        return { ok: true, data: payload, status: response.status, requestId };
      }
      if (!response.ok && isRecord(payload) && isRecord(payload.error)) {
        const error = payload.error;
        if (typeof error.code === "string" && typeof error.message === "string") {
          return {
            ok: false,
            error: {
              kind: "api",
              code: error.code,
              details: isRecord(error.details) ? error.details : {},
              message: error.message,
              requestId:
                typeof error.request_id === "string" ? error.request_id : requestId ?? "unknown",
            },
            status: response.status,
            requestId,
          };
        }
      }
      return {
        ok: false,
        error: {
          kind: "invalid-response",
          message: response.ok
            ? "The local API response did not match the workspace contract."
            : "The local API returned an invalid error response.",
        },
        status: response.status,
        requestId,
      };
    } catch (cause) {
      if (requestOptions.signal?.aborted === true) {
        return {
          ok: false,
          error: { kind: "aborted", message: "The request was cancelled." },
          status: null,
          requestId: null,
        };
      }
      return {
        ok: false,
        error: {
          kind: "network",
          message: cause instanceof Error ? cause.message : "The local API could not be reached.",
        },
        status: null,
        requestId: null,
      };
    }
  }

  return {
    ...core,
    listDocumentPages: (documentId: string, requestOptions: RequestOptions = {}) =>
      request(
        `/api/v1/documents/${encodeURIComponent(documentId)}/pages`,
        "GET",
        isPageListResponse,
        requestOptions,
      ),
    startDocumentOcr: (documentId: string, key: string, requestOptions: RequestOptions = {}) =>
      request(
        `/api/v1/documents/${encodeURIComponent(documentId)}/ocr/start`,
        "POST",
        isJobEnvelope,
        requestOptions,
        {
          page_ids: null,
          mode: "AUTO",
          language: "en",
          detect_tables: true,
          detect_formulas: true,
        },
        key,
      ),
    getDocumentOcrStatus: (documentId: string, requestOptions: RequestOptions = {}) =>
      request(
        `/api/v1/documents/${encodeURIComponent(documentId)}/ocr/status`,
        "GET",
        isOCRStatusResponse,
        requestOptions,
      ),
    getPageOcr: (pageId: string, requestOptions: RequestOptions = {}) =>
      request(
        `/api/v1/pages/${encodeURIComponent(pageId)}/ocr`,
        "GET",
        isOCRPageResponse,
        requestOptions,
      ),
    resolveSegmentSource: (
      segmentId: string,
      input: SourceResolutionInput,
      requestOptions: RequestOptions = {},
    ) =>
      request(
        `/api/v1/segments/${encodeURIComponent(segmentId)}/source-resolution`,
        "PATCH",
        isSourceResolutionResponse,
        requestOptions,
        input,
      ),
    listReviewQueue: (
      projectId: string,
      filters: ReviewQueueQueryFilters,
      requestOptions: RequestOptions = {},
    ) =>
      request(
        `/api/v1/projects/${encodeURIComponent(projectId)}/review-queue${queryString(filters)}`,
        "GET",
        isReviewQueueResponse,
        requestOptions,
      ),
    getPageEditorView: (pageId: string, requestOptions: RequestOptions = {}) =>
      request(
        `/api/v1/pages/${encodeURIComponent(pageId)}/editor-view`,
        "GET",
        isReviewPageResponse,
        requestOptions,
      ),
    editSegmentTranslation: (
      segmentId: string,
      input: SaveSegmentTranslationInput,
      requestOptions: RequestOptions = {},
    ) =>
      request(
        `/api/v1/segments/${encodeURIComponent(segmentId)}/translation`,
        "PATCH",
        isSegmentDataResponse,
        requestOptions,
        input,
      ),
    listExports: async (projectId: string): Promise<ExportRecord[]> => {
      const result = await request(
        `/api/v1/projects/${encodeURIComponent(projectId)}/exports`,
        "GET",
        isExportListResponse,
      );
      if (!result.ok) throw new Error(result.error.message);
      return result.data.data;
    },
    downloadExport: async (exportId: string): Promise<Blob> => {
      const response = await fetchImplementation(
        `${baseUrl}/api/v1/exports/${encodeURIComponent(exportId)}/download`,
        { cache: "no-store", credentials: "omit", headers: createRequestHeaders("GET") },
      );
      if (!response.ok) throw new Error(`Export download failed (${response.status}).`);
      if (!response.headers.get("content-type")?.includes("application/pdf")) {
        throw new Error("The export download was not a PDF.");
      }
      return response.blob();
    },
    listBackups: () => request("/api/v1/backups", "GET", isBackupListResponse),
    createBackup: (input: CreateBackupInput, key: string) =>
      request("/api/v1/backups", "POST", isCreateBackupResponse, {}, input, key),
    verifyBackup: (backupId: string) =>
      request(
        `/api/v1/backups/${encodeURIComponent(backupId)}/verify`,
        "POST",
        isVerifyBackupResponse,
      ),
    restoreBackup: (backupId: string, input: RestoreBackupInput, key: string) =>
      request(
        `/api/v1/backups/${encodeURIComponent(backupId)}/restore`,
        "POST",
        isRestoreBackupResponse,
        {},
        input,
        key,
      ),
    documentSourceUrl: (documentId: string) =>
      `${baseUrl}/api/v1/documents/${encodeURIComponent(documentId)}/source`,
  };
}

export type WorkspaceClient = ReturnType<typeof createWorkspaceClient>;
export type WorkspacePage = PageResource;
