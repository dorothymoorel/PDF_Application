"use client";

import { useEffect, useState } from "react";
import type { ApiResult } from "@transloka/api-client";

export const STORAGE_CATEGORIES = [
  "originals",
  "page_renders",
  "ocr",
  "intermediate",
  "exports",
  "backups",
] as const;

export type StorageCategory = (typeof STORAGE_CATEGORIES)[number];

export type StorageUsage = {
  free_disk_bytes: number;
  total_managed_bytes: number;
  categories: Record<StorageCategory, number>;
};

export type StorageUsageResponse = {
  data: StorageUsage;
  meta: { request_id: string };
};

export type CleanupPreviewRequest = {
  older_than_days: number;
  dry_run: true;
};

export type CleanupPreview = {
  job_id: string;
  operation: "TEMP_CLEANUP" | "CACHE_CLEANUP";
  status: "COMPLETED";
  healthy: boolean;
  dry_run: true;
  checked_count: number;
  issue_count: number;
  issues: string[];
  orphans: string[];
  candidates: string[];
  deleted: string[];
  protected: string[];
};

export type CleanupPreviewResponse = {
  data: CleanupPreview;
  meta: { request_id: string };
};

export type StorageClient = {
  getStorageUsage: () => Promise<ApiResult<StorageUsageResponse>>;
  previewCleanup: (
    input: CleanupPreviewRequest,
  ) => Promise<ApiResult<CleanupPreviewResponse>>;
};

const CATEGORY_LABELS: Record<StorageCategory, string> = {
  originals: "Originals",
  page_renders: "Page renders",
  ocr: "OCR",
  intermediate: "Intermediate",
  exports: "Exports",
  backups: "Backups",
};

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) {
    return "0 B";
  }
  if (value < 1_000) {
    return `${Math.round(value)} B`;
  }
  if (value < 1_000_000) {
    return `${Math.round(value / 1_000)} KB`;
  }
  if (value < 1_000_000_000) {
    return `${Math.round(value / 1_000_000)} MB`;
  }
  return `${Math.round(value / 1_000_000_000)} GB`;
}

function errorMessage(result: { error: { message: string } }): string {
  return result.error.message;
}

export function StorageDashboard({
  client,
}: Readonly<{
  client: StorageClient;
}>) {
  const [usage, setUsage] = useState<StorageUsage | null>(null);
  const [cleanup, setCleanup] = useState<CleanupPreview | null>(null);
  const [olderThanDays, setOlderThanDays] = useState("7");
  const [isLoading, setIsLoading] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);
    void client
      .getStorageUsage()
      .then((result) => {
        if (!active) return;
        if (!result.ok) {
          setError(errorMessage(result));
          return;
        }
        setUsage(result.data.data);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "Storage usage could not be loaded.");
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [client]);

  const previewCleanup = async () => {
    if (isPreviewing) return;
    const days = Number(olderThanDays);
    if (!Number.isInteger(days) || days < 1 || days > 3650) {
      setError("Cleanup age must be a whole number between 1 and 3650 days.");
      return;
    }
    setIsPreviewing(true);
    setError(null);
    const result = await client.previewCleanup({ older_than_days: days, dry_run: true });
    setIsPreviewing(false);
    if (!result.ok) {
      setError(errorMessage(result));
      return;
    }
    setCleanup(result.data.data);
  };

  return (
    <section aria-labelledby="storage-dashboard-heading" className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Storage</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="storage-dashboard-heading">
          Storage usage
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Review managed files and preview cleanup candidates without deleting anything.
        </p>
      </header>

      {error !== null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4" role="alert">
          <p className="font-medium text-red-900">Storage data could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
        </div>
      ) : null}

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading storage usage…
        </p>
      ) : usage !== null ? (
        <>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <dt className="text-sm font-medium text-slate-600">Managed storage</dt>
              <dd className="mt-1 text-2xl font-bold text-slate-950">
                {formatBytes(usage.total_managed_bytes)} managed
              </dd>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <dt className="text-sm font-medium text-slate-600">Free disk</dt>
              <dd className="mt-1 text-2xl font-bold text-slate-950">
                {formatBytes(usage.free_disk_bytes)} free
              </dd>
            </div>
          </dl>

          <section aria-labelledby="storage-categories-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-950" id="storage-categories-heading">
              Storage categories
            </h2>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {STORAGE_CATEGORIES.map((category) => (
                <li className="rounded-xl border border-slate-200 bg-slate-50 p-4" key={category}>
                  <p className="font-semibold text-slate-950">{CATEGORY_LABELS[category]}</p>
                  <p className="mt-1 text-sm text-slate-600">{formatBytes(usage.categories[category])}</p>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}

      <section aria-labelledby="cleanup-preview-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Maintenance</p>
          <h2 className="mt-1 text-xl font-semibold text-slate-950" id="cleanup-preview-heading">
            Cleanup preview
          </h2>
          <p className="mt-1 text-sm text-slate-600">Preview temporary files before any cleanup is requested.</p>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm font-medium text-slate-800" htmlFor="cleanup-age">
            Older than (days)
            <input
              className="mt-1 block w-32 rounded-lg border border-slate-300 px-3 py-2 font-normal"
              id="cleanup-age"
              min={1}
              max={3650}
              onChange={(event) => setOlderThanDays(event.target.value)}
              type="number"
              value={olderThanDays}
            />
          </label>
          <button
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isPreviewing}
            onClick={() => void previewCleanup()}
            type="button"
          >
            {isPreviewing ? "Preparing preview…" : "Preview cleanup"}
          </button>
        </div>
        {cleanup !== null ? (
          <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4" role="status">
            <p className="font-semibold text-amber-950">Dry run only — no files were deleted.</p>
            <p className="mt-1 text-sm text-amber-900">
              {cleanup.candidates.length} candidate(s) · {cleanup.protected.length} protected file(s)
            </p>
            {cleanup.candidates.length > 0 ? (
              <ul aria-label="Cleanup candidates" className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-950">
                {cleanup.candidates.map((candidate) => <li key={candidate}>{candidate}</li>)}
              </ul>
            ) : null}
            {cleanup.protected.length > 0 ? (
              <ul aria-label="Protected files" className="mt-3 list-disc space-y-1 pl-5 text-sm text-emerald-900">
                {cleanup.protected.map((file) => <li key={file}>{file}</li>)}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>
    </section>
  );
}

export { formatBytes };
