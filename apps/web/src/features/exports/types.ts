export type ExportProfile = "STANDARD" | "HIGH_QUALITY" | "ARCHIVE";

export const EXPORT_PROFILES: readonly ExportProfile[] = [
  "STANDARD",
  "HIGH_QUALITY",
  "ARCHIVE",
];

export type ExportRecord = {
  id: string;
  filename: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  download_url?: string | null;
};

export type ExportClient = {
  createExport: (input: {
    profile: ExportProfile;
    projectId: string;
  }) => Promise<ExportRecord>;
  downloadExport: (exportId: string) => Promise<Blob>;
};

export function exportStatusLabel(status: ExportRecord["status"]): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}
