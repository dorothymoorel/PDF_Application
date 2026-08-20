import type { ApiResult } from "@transloka/api-client";

export type WarningSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type WarningStatus =
  | "OPEN"
  | "RESOLVED"
  | "ACCEPTED"
  | "FALSE_POSITIVE"
  | "IGNORED_BY_POLICY";

export type WarningRecord = {
  id: string;
  project_id: string;
  document_id: string | null;
  page_id: string | null;
  segment_id: string | null;
  warning_type: string;
  severity: WarningSeverity;
  message: string;
  details: Record<string, unknown>;
  status: WarningStatus;
  resolution_type: string | null;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type WarningListResponse = {
  data: WarningRecord[];
  meta: {
    request_id: string;
    pagination: {
      limit: number;
      next_cursor: string | null;
      has_more: boolean;
    };
  };
};

export type WarningQueryFilters = {
  status?: WarningStatus;
  severity?: WarningSeverity;
  warning_type?: string;
  page_id?: string;
  segment_id?: string;
};

export interface WarningClient {
  listWarnings(
    projectId: string,
    filters: WarningQueryFilters,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<WarningListResponse>>;
  resolveWarning(
    warningId: string,
    resolutionNote?: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<WarningRecord>>;
  acceptWarning(
    warningId: string,
    resolutionNote?: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<WarningRecord>>;
  markWarningFalsePositive(
    warningId: string,
    resolutionNote?: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<WarningRecord>>;
}
