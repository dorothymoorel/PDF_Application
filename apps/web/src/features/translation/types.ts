import {
  createTransLokaClient,
  type StartTranslationInput,
} from "@transloka/api-client";

export type TranslationUiClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  | "getTranslationReadiness"
  | "startTranslation"
  | "getTranslationStatus"
  | "cancelTranslation"
  | "retryFailedTranslation"
>;

export type TranslationSettings = Pick<
  StartTranslationInput,
  | "scope"
  | "provider_type"
  | "model_id"
  | "cloud_model_name"
  | "cloud_consent"
  | "translation_style"
  | "batch_size"
  | "context_mode"
>;

export type TranslationReadiness = {
  ready: boolean;
  blocking_issues: readonly { code: string; message: string }[];
  warnings: readonly { code: string; count: number }[];
  segment_count: number;
  estimated_batches: number;
};

export type TranslationStatus = {
  status: string;
  total_segments: number;
  completed_segments: number;
  failed_segments: number;
  review_required_segments: number;
  progress: number;
  active_job_id: string | null;
  current_batch: number;
  total_batches: number;
  unattempted_segments?: number | null;
  provider_error_code?: string | null;
  retry_after_seconds?: number | null;
};

export const TERMINAL_TRANSLATION_STATUSES = new Set([
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);

export function isTerminalTranslationStatus(status: string): boolean {
  return TERMINAL_TRANSLATION_STATUSES.has(status);
}

export function statusLabel(status: string): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}
