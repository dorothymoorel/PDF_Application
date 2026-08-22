"use client";

import {
  createTransLokaClient,
  type ReconstructionMode,
  type ReconstructionSettings as ApiReconstructionSettings,
} from "@transloka/api-client";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  boundedProgress,
  RECONSTRUCTION_PROFILES,
  reconstructionStatusLabel,
  type ReconstructionProfile,
  type ReconstructionReadiness,
  type ReconstructionStatus,
  type ReconstructionUiClient,
} from "./types";

const defaultClient = createTransLokaClient();
const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950";
const ACTIVE_STATUSES = new Set([
  "CREATED",
  "QUEUED",
  "RUNNING",
  "RETRYING",
  "CANCELLATION_REQUESTED",
  "PREPARING",
  "MEASURING",
  "LAYING_OUT",
  "RENDERING",
  "VALIDATING",
]);

function startKey(projectId: string): string {
  return `reconstruction-ui-${projectId}-${Date.now().toString(36)}`;
}

function retryKey(pageId: string): string {
  return `reconstruction-ui-retry-${pageId}-${Date.now().toString(36)}`;
}

function defaultSettings(profile: ReconstructionProfile): ApiReconstructionSettings & {
  profile: ReconstructionProfile;
} {
  return {
    profile,
    preserve_page_size: true,
    preserve_images: true,
    preserve_headers: true,
    preserve_footers: true,
    preserve_page_numbers: true,
    translate_captions: true,
    minimum_body_font_pt: 8,
    maximum_font_reduction_percent: 10,
    allow_page_addition: true,
    allow_column_change: false,
    table_complexity_fallback: "PRESERVE_AS_IMAGE",
    image_quality: "STANDARD",
    block_export_on_critical_errors: true,
  };
}

export function ReconstructionWorkspace({
  client = defaultClient,
  onCreateExport,
  pageId,
  pollIntervalMs = 2_000,
  projectId,
  reconstructionPageId,
}: Readonly<{
  client?: ReconstructionUiClient;
  onCreateExport?: (input: {
    profile: ReconstructionProfile;
    projectId: string;
  }) => Promise<string> | string | void;
  pageId?: string;
  pollIntervalMs?: number;
  projectId: string;
  reconstructionPageId?: string;
}>) {
  const [mode, setMode] = useState<ReconstructionMode>("HYBRID");
  const [profile, setProfile] = useState<ReconstructionProfile>("BALANCED");
  const [settings, setSettings] = useState(() => defaultSettings("BALANCED"));
  const [readiness, setReadiness] = useState<ReconstructionReadiness | null>(null);
  const [status, setStatus] = useState<ReconstructionStatus | null>(null);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    "preview" | "start" | "cancel" | "retry" | "export" | null
  >(null);
  const [exportId, setExportId] = useState<string | null>(null);
  const mounted = useRef(false);

  const criticalWarningCount = status?.critical_warning_count ?? 0;
  const canExport =
    status !== null &&
    ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(status.status) &&
    criticalWarningCount === 0;
  const canCancel = status !== null && ACTIVE_STATUSES.has(status.status);
  const canRetry =
    reconstructionPageId !== undefined &&
    status !== null &&
    ["FAILED", "PARTIALLY_COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(status.status);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();

    const loadReadiness = async () => {
      const result = await client.getReconstructionReadiness(projectId, {
        signal: controller.signal,
      });
      if (disposed || !mounted.current) return;
      if (!result.ok) {
        if (result.error.kind !== "aborted") setError(result.error.message);
        return;
      }
      setReadiness(result.data.data);
    };

    setReadiness(null);
    void loadReadiness();
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [client, projectId]);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const poll = async () => {
      const result = await client.getReconstructionStatus(projectId, {
        signal: controller.signal,
      });
      if (disposed || !mounted.current) return;
      if (!result.ok) {
        if (result.error.kind !== "aborted") setError(result.error.message);
        return;
      }
      const nextStatus = result.data.data;
      setStatus(nextStatus);
      setError(null);
      if (ACTIVE_STATUSES.has(nextStatus.status) || nextStatus.status === "NOT_STARTED") {
        timer = setTimeout(() => void poll(), Math.max(250, pollIntervalMs));
      }
    };

    setStatus(null);
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
      controller.abort();
    };
  }, [client, pollIntervalMs, projectId]);

  const currentSettings = useMemo(
    () => ({ ...settings, profile }),
    [profile, settings],
  );

  const updateSetting = <K extends keyof typeof settings>(
    key: K,
    value: (typeof settings)[K],
  ) => {
    setSettings((current) => ({ ...current, [key]: value }));
  };

  const preview = async () => {
    if (pageId === undefined || pendingAction !== null) return;
    setPendingAction("preview");
    setError(null);
    setPreviewMessage(null);
    const result = await client.previewReconstruction(projectId, {
      page_id: pageId,
      mode,
      settings: currentSettings,
    });
    if (!mounted.current) return;
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setPreviewMessage(`Preview ready (${result.data.data.preview_id}).`);
  };

  const start = async () => {
    if (pendingAction !== null) return;
    setPendingAction("start");
    setError(null);
    const readinessResult = await client.getReconstructionReadiness(projectId);
    if (!mounted.current) return;
    if (!readinessResult.ok) {
      setPendingAction(null);
      setError(readinessResult.error.message);
      return;
    }
    const nextReadiness = readinessResult.data.data;
    setReadiness(nextReadiness);
    if (!nextReadiness.ready) {
      setPendingAction(null);
      setError("Reconstruction cannot start until all readiness blockers are resolved.");
      return;
    }
    const result = await client.startReconstruction(
      projectId,
      startKey(projectId),
      { mode, page_ids: null, settings: currentSettings },
    );
    if (!mounted.current) return;
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStatus((current) => ({
      ...(current ?? {
        progress: 0,
        completed_pages: 0,
        total_source_pages: 0,
        generated_target_pages: 0,
        warning_count: 0,
        critical_warning_count: 0,
        active_job_id: null,
      }),
      status: result.data.data.status,
      active_job_id: result.data.data.job_id,
    }));
  };

  const cancel = async () => {
    if (pendingAction !== null || !canCancel) return;
    setPendingAction("cancel");
    setError(null);
    const result = await client.cancelReconstruction(projectId);
    if (!mounted.current) return;
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStatus(result.data.data);
  };

  const retry = async () => {
    if (pendingAction !== null || !canRetry || reconstructionPageId === undefined) return;
    setPendingAction("retry");
    setError(null);
    const result = await client.retryReconstructionPage(
      reconstructionPageId,
      retryKey(reconstructionPageId),
      { fallback_mode: "REFLOW", override_settings: { ...currentSettings } },
    );
    if (!mounted.current) return;
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStatus((current) =>
      current === null
        ? current
        : { ...current, status: result.data.data.status, active_job_id: result.data.data.job_id },
    );
  };

  const createExport = async () => {
    if (pendingAction !== null || !canExport || onCreateExport === undefined) return;
    setPendingAction("export");
    setError(null);
    try {
      const nextExportId = await onCreateExport({ profile, projectId });
      if (typeof nextExportId === "string" && nextExportId !== "") setExportId(nextExportId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The export could not be created.");
    } finally {
      if (mounted.current) setPendingAction(null);
    }
  };

  return (
    <section
      aria-busy={pendingAction !== null}
      aria-labelledby="reconstruction-workspace-heading"
      className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Reconstruction and export
        </p>
        <h2 className="mt-1 text-2xl font-semibold text-slate-950" id="reconstruction-workspace-heading">
          Preserve the document while making translated pages readable
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Preview one page, start a background reconstruction, and keep critical warnings visible before export.
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <label className="text-sm font-medium text-slate-800" htmlFor="reconstruction-mode">
            Reconstruction mode
          </label>
          <select
            className={inputClass}
            id="reconstruction-mode"
            onChange={(event) => setMode(event.target.value as ReconstructionMode)}
            value={mode}
          >
            {(readiness?.available_modes ?? ["OVERLAY", "REFLOW", "HYBRID"]).map((value) => (
              <option key={value} value={value}>
                {value.charAt(0) + value.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-sm font-medium text-slate-800" htmlFor="reconstruction-profile">
            Reconstruction profile
          </label>
          <select
            className={inputClass}
            id="reconstruction-profile"
            onChange={(event) => {
              const nextProfile = event.target.value as ReconstructionProfile;
              setProfile(nextProfile);
              setSettings((current) => ({ ...current, profile: nextProfile }));
            }}
            value={profile}
          >
            {RECONSTRUCTION_PROFILES.map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="rounded-xl border border-slate-200 p-4">
        <legend className="px-1 text-sm font-semibold text-slate-900">Layout settings</legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {(
            [
              ["preserve_images", "Preserve images"],
              ["preserve_headers", "Preserve headers"],
              ["preserve_footers", "Preserve footers"],
              ["allow_page_addition", "Allow page addition"],
              ["allow_column_change", "Allow column changes"],
              ["block_export_on_critical_errors", "Block export on critical errors"],
            ] as const
          ).map(([key, label]) => (
            <label className="flex items-center gap-2 text-sm text-slate-700" key={key}>
              <input
                checked={Boolean(settings[key])}
                onChange={(event) => updateSetting(key, event.target.checked)}
                type="checkbox"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      {readiness !== null ? (
        <div
          aria-label="Reconstruction readiness"
          className={
            readiness.ready
              ? "rounded-xl border border-emerald-200 bg-emerald-50 p-4"
              : "rounded-xl border border-red-200 bg-red-50 p-4"
          }
        >
          <p className="font-semibold text-slate-950">
            Readiness: {readiness.ready ? "Ready" : "Blocked"}
          </p>
          {readiness.blocking_issues.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800">
              {readiness.blocking_issues.map((issue) => (
                <li key={`${issue.code}:${issue.message}`}>{issue.message}</li>
              ))}
            </ul>
          ) : null}
          {readiness.warnings.length > 0 ? (
            <p className="mt-2 text-sm text-amber-800">
              {readiness.warnings.map((warning) => `${warning.code} (${warning.count})`).join(", ")}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-slate-600" role="status">Checking reconstruction readiness…</p>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={pendingAction !== null || pageId === undefined}
          onClick={() => void preview()}
          type="button"
        >
          {pendingAction === "preview" ? "Preparing preview…" : "Preview page"}
        </button>
        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={pendingAction !== null || readiness?.ready !== true}
          onClick={() => void start()}
          type="button"
        >
          {pendingAction === "start" ? "Starting…" : "Start reconstruction"}
        </button>
        {canCancel ? (
          <button
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void cancel()}
            type="button"
          >
            {pendingAction === "cancel" ? "Cancelling…" : "Cancel reconstruction"}
          </button>
        ) : null}
        {canRetry ? (
          <button
            className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void retry()}
            type="button"
          >
            {pendingAction === "retry" ? "Retrying…" : "Retry page with reflow"}
          </button>
        ) : null}
      </div>

      {previewMessage !== null ? <p className="text-sm text-emerald-700" role="status">{previewMessage}</p> : null}

      {status !== null ? (
        <div aria-label="Reconstruction progress" className="rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap justify-between gap-3 text-sm font-medium text-slate-700">
            <span>{reconstructionStatusLabel(status.status)}</span>
            <span>{Math.round(boundedProgress(status.progress) * 100)}%</span>
          </div>
          <progress
            aria-label="Reconstruction progress"
            className="mt-2 h-3 w-full accent-slate-900"
            max={100}
            value={Math.round(boundedProgress(status.progress) * 100)}
          />
          <p className="mt-2 text-sm text-slate-600">
            {status.completed_pages} of {status.total_source_pages} source pages · {status.generated_target_pages} target pages · {status.warning_count} warnings
          </p>
          {criticalWarningCount > 0 ? (
            <p className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-900" role="alert">
              {criticalWarningCount} critical warning(s) block export.
            </p>
          ) : null}
        </div>
      ) : null}

      {onCreateExport !== undefined ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
          <button
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null || !canExport}
            onClick={() => void createExport()}
            type="button"
          >
            {pendingAction === "export" ? "Creating export…" : "Create export"}
          </button>
          {exportId !== null ? <span className="text-sm text-emerald-700">Export ready: {exportId}</span> : null}
        </div>
      ) : null}

      {error !== null ? <p className="text-sm text-red-700" role="alert">{error}</p> : null}
    </section>
  );
}

export const ReconstructionSettings = ReconstructionWorkspace;
export const ReconstructionProgress = ReconstructionWorkspace;
