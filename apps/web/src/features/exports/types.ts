export type ExportProfile = "STANDARD" | "HIGH_QUALITY" | "ARCHIVAL";

export const EXPORT_PROFILES: readonly ExportProfile[] = [
  "STANDARD",
  "HIGH_QUALITY",
  "ARCHIVAL",
];

export type ExportRecord = {
  id: string;
  output_profile: string;
  version_number: number;
  filename: string;
  status:
    | "CREATED"
    | "RUNNING"
    | "COMPLETED"
    | "COMPLETED_WITH_WARNINGS"
    | "PARTIALLY_COMPLETED"
    | "FAILED"
    | "CANCELLED";
  checksum_sha256: string | null;
  size_bytes?: number | null;
};

export type ExportClient = {
  listExports: (projectId: string) => Promise<ExportRecord[]>;
  downloadExport: (exportId: string) => Promise<Blob>;
};

export function exportStatusLabel(status: ExportRecord["status"]): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}
