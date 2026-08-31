"use client";

import { useCallback, useEffect, useState } from "react";

import {
  EXPORT_PROFILES,
  exportStatusLabel,
  type ExportClient,
  type ExportProfile,
  type ExportRecord,
} from "./types";

const COMPLETED_STATUSES = new Set(["COMPLETED", "COMPLETED_WITH_WARNINGS"]);

export function ExportPanel({
  client,
  projectId,
}: Readonly<{
  client: ExportClient;
  projectId: string;
}>) {
  const [profile, setProfile] = useState<ExportProfile>("STANDARD");
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [pendingAction, setPendingAction] = useState<"refresh" | "download" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshExports = useCallback(async () => {
    setPendingAction("refresh");
    setError(null);
    try {
      setExports(await client.listExports(projectId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Exports could not be loaded.");
    } finally {
      setPendingAction(null);
    }
  }, [client, projectId]);

  useEffect(() => {
    void refreshExports();
  }, [refreshExports]);

  const exportRecord =
    exports.find(
      (candidate) =>
        candidate.output_profile === profile && COMPLETED_STATUSES.has(candidate.status),
    ) ?? null;

  const download = async () => {
    if (exportRecord === null || pendingAction !== null) return;
    setPendingAction("download");
    setError(null);
    try {
      const blob = await client.downloadExport(exportRecord.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = exportRecord.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The export could not be downloaded.");
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <section
      aria-labelledby="export-panel-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Final output</p>
      <h2 className="mt-1 text-xl font-semibold text-slate-950" id="export-panel-heading">
        Validated PDF exports
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Completed reconstruction jobs create immutable PDF exports. Compare the persisted checksum
        before using a downloaded file.
      </p>

      <div className="mt-5 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-sm font-medium text-slate-800" htmlFor="export-profile">
            Export profile
          </label>
          <select
            className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950"
            id="export-profile"
            onChange={(event) => setProfile(event.target.value as ExportProfile)}
            value={profile}
          >
            {EXPORT_PROFILES.map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={pendingAction !== null}
          onClick={() => void refreshExports()}
          type="button"
        >
          {pendingAction === "refresh" ? "Refreshing…" : "Refresh exports"}
        </button>
        {exportRecord !== null ? (
          <button
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void download()}
            type="button"
          >
            {pendingAction === "download" ? "Downloading…" : "Download PDF"}
          </button>
        ) : null}
      </div>

      {exportRecord !== null ? (
        <div className="mt-4 text-sm text-slate-700" role="status">
          <p>
            {exportRecord.filename} · {exportStatusLabel(exportRecord.status)} · version {exportRecord.version_number}
          </p>
          <p className="mt-1 break-all text-xs text-slate-500">
            SHA-256: {exportRecord.checksum_sha256 ?? "Pending validation"}
          </p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-600" role="status">
          No completed {profile.toLowerCase().replaceAll("_", " ")} export is available. Complete
          reconstruction, then refresh this panel.
        </p>
      )}
      {error !== null ? (
        <p className="mt-4 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

export const ExportDownload = ExportPanel;
