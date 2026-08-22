import type { ApiResult } from "@transloka/api-client";

export type QualityReportType =
  | "EXTRACTION"
  | "OCR"
  | "TRANSLATION"
  | "TERMINOLOGY"
  | "RECONSTRUCTION"
  | "FINAL_EXPORT";

export type QualityReportStatus =
  | "NOT_RUN"
  | "RUNNING"
  | "PASSED"
  | "PASSED_WITH_WARNINGS"
  | "FAILED"
  | "SKIPPED";

export type QualityCheckStatus = QualityReportStatus;
export type QualitySeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type QualityWarningStatus =
  | "OPEN"
  | "RESOLVED"
  | "ACCEPTED"
  | "FALSE_POSITIVE"
  | "IGNORED_BY_POLICY";

export type QualityWarning = {
  id: string;
  project_id: string;
  document_id: string | null;
  page_id: string | null;
  segment_id: string | null;
  warning_type: string;
  severity: QualitySeverity;
  message: string;
  details: Record<string, unknown>;
  status: QualityWarningStatus;
  resolution_type: string | null;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type QualityCheck = {
  id: string;
  report_id: string;
  check_type: string;
  scope_type: string;
  scope_id: string;
  status: QualityCheckStatus;
  score: number | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type QualityReportRecord = {
  id: string;
  project_id: string;
  document_id: string;
  report_type: QualityReportType;
  version: string;
  status: QualityReportStatus;
  overall_score: number | null;
  critical_warning_count: number;
  high_warning_count: number;
  medium_warning_count: number;
  low_warning_count: number;
  summary: Record<string, unknown> | null;
  created_at: string;
  checks: QualityCheck[];
  warnings: QualityWarning[];
};

export type QualityReportsResponse = {
  data: QualityReportRecord[];
  meta: {
    request_id: string;
    pagination?: {
      limit: number;
      next_cursor: string | null;
      has_more: boolean;
    };
  };
};

export type QualityReportQueryFilters = {
  report_type?: QualityReportType;
  status?: QualityReportStatus;
  severity?: QualitySeverity;
  warning_status?: QualityWarningStatus;
};

export interface QualityDashboardClient {
  listReports(
    this: void,
    projectId: string,
    filters: QualityReportQueryFilters,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<QualityReportsResponse>>;
  getReport(
    this: void,
    reportId: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<QualityReportRecord>>;
}

export const QUALITY_REPORT_TYPES: readonly QualityReportType[] = [
  "EXTRACTION",
  "OCR",
  "TRANSLATION",
  "TERMINOLOGY",
  "RECONSTRUCTION",
  "FINAL_EXPORT",
];

export const QUALITY_REPORT_STATUSES: readonly QualityReportStatus[] = [
  "NOT_RUN",
  "RUNNING",
  "PASSED",
  "PASSED_WITH_WARNINGS",
  "FAILED",
  "SKIPPED",
];

export const QUALITY_SEVERITIES: readonly QualitySeverity[] = [
  "INFO",
  "LOW",
  "MEDIUM",
  "HIGH",
  "CRITICAL",
];

export const QUALITY_WARNING_STATUSES: readonly QualityWarningStatus[] = [
  "OPEN",
  "RESOLVED",
  "ACCEPTED",
  "FALSE_POSITIVE",
  "IGNORED_BY_POLICY",
];

export function humanizeQualityValue(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}
