import {
  createTransLokaClient,
  type PreviewReconstructionInput,
  type ReconstructionMode,
  type ReconstructionSettings,
  type StartReconstructionInput,
} from "@transloka/api-client";

export type ReconstructionUiClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  | "getReconstructionReadiness"
  | "previewReconstruction"
  | "startReconstruction"
  | "getReconstructionStatus"
  | "cancelReconstruction"
  | "retryReconstructionPage"
>;

export type ReconstructionProfile = "PRESERVE_LAYOUT" | "BALANCED" | "READABILITY_FIRST";

export const RECONSTRUCTION_PROFILES: readonly ReconstructionProfile[] = [
  "PRESERVE_LAYOUT",
  "BALANCED",
  "READABILITY_FIRST",
];

export type ReconstructionReadiness = {
  ready: boolean;
  blocking_issues: readonly { code: string; message: string }[];
  warnings: readonly { code: string; count: number }[];
  available_modes: readonly ReconstructionMode[];
};

export type ReconstructionStatus = {
  status: string;
  progress: number;
  completed_pages: number;
  total_source_pages: number;
  generated_target_pages: number;
  warning_count: number;
  critical_warning_count: number;
  active_job_id: string | null;
};

export type ReconstructionUiSettings = ReconstructionSettings & {
  profile: ReconstructionProfile;
};

export type ReconstructionStartInput = StartReconstructionInput & {
  settings: ReconstructionUiSettings;
};

export type ReconstructionPreviewInput = PreviewReconstructionInput;

export const TERMINAL_RECONSTRUCTION_STATUSES = new Set([
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
]);

export function isTerminalReconstructionStatus(status: string): boolean {
  return TERMINAL_RECONSTRUCTION_STATUSES.has(status);
}

export function reconstructionStatusLabel(status: string): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

export function boundedProgress(value: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
}
