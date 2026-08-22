"use client";

import { useState } from "react";

import {
  EXPORT_PROFILES,
  exportStatusLabel,
  type ExportClient,
  type ExportProfile,
  type ExportRecord,
} from "./types";

export function ExportPanel({
  client,
  projectId,
}: Readonly<{
  client: ExportClient;
  projectId: string;
}>) {
  const [profile, setProfile] = useState<ExportProfile>("STANDARD");
  const [exportRecord, setExportRecord] = useState<ExportRecord | null>(null);
  const [pendingAction, setPendingAction] = useState<"create" | "download" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createExport = async () => {
    if (pendingAction !== null) return;
    setPendingAction("create");
    setError(null);
    try {
      setExportRecord(await client.createExport({ profile, projectId }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The export could not be created.");
    } finally {
      setPendingAction(null);
    }
  };

  const download = async () => {
    if (exportRecord === null || exportRecord.status !== "COMPLETED" || pendingAction !== null) {
      return;
    }
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
    <section aria-labelledby="export-panel-heading" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Final output</p>
      <h2 className="mt-1 text-xl font-semibold text-slate-950" id="export-panel-heading">
        Create and download export
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Exports are created only after reconstruction validation succeeds.
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
          onClick={() => void createExport()}
          type="button"
        >
          {pendingAction === "create" ? "Creating…" : "Create export"}
        </button>
        {exportRecord?.status === "COMPLETED" ? (
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
        <p className="mt-4 text-sm text-slate-700" role="status">
          {exportRecord.filename} · {exportStatusLabel(exportRecord.status)}
        </p>
      ) : null}
      {error !== null ? <p className="mt-4 text-sm text-red-700" role="alert">{error}</p> : null}
    </section>
  );
}

export const ExportDownload = ExportPanel;
