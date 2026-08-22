"use client";

import { useEffect, useState } from "react";
import type { ApiResult } from "@transloka/api-client";

export const BACKUP_TYPES = [
  "DATABASE_ONLY",
  "METADATA",
  "FULL_PROJECTS",
  "FULL_APPLICATION",
] as const;

export type BackupType = (typeof BACKUP_TYPES)[number];
export type BackupStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";

export type BackupRecord = {
  id: string;
  backup_type: BackupType;
  filename: string;
  size_bytes: number;
  checksum_sha256: string;
  application_version: string;
  database_schema_version: string;
  status: BackupStatus;
  created_at: string;
  completed_at: string | null;
};

export type BackupListResponse = {
  data: BackupRecord[];
  meta: { request_id: string };
};

export type CreateBackupInput = {
  backup_type: BackupType;
  include_original_files: boolean;
  include_exports: boolean;
  include_intermediate_files: boolean;
};

export type CreateBackupResponse = {
  data: { job_id: string; backup_id: string | null; status: "QUEUED" };
  meta: { request_id: string };
};

export type VerifyBackupResponse = {
  data: { backup_id: string; status: "VERIFIED" | "FAILED"; message: string };
  meta: { request_id: string };
};

export type RestoreBackupInput = {
  confirmation: "RESTORE";
  create_pre_restore_backup: true;
  restore_files: boolean;
};

export type RestoreBackupResponse = {
  data: {
    job_id: string;
    backup_id: string;
    status: "ACCEPTED";
    pre_restore_backup_id: string | null;
  };
  meta: { request_id: string };
};

export type BackupClient = {
  listBackups: () => Promise<ApiResult<BackupListResponse>>;
  createBackup: (
    input: CreateBackupInput,
    idempotencyKey: string,
  ) => Promise<ApiResult<CreateBackupResponse>>;
  verifyBackup: (backupId: string) => Promise<ApiResult<VerifyBackupResponse>>;
  restoreBackup: (
    backupId: string,
    input: RestoreBackupInput,
    idempotencyKey: string,
  ) => Promise<ApiResult<RestoreBackupResponse>>;
};

function formatBackupSize(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "0 B";
  if (value < 1_000) return `${Math.round(value)} B`;
  if (value < 1_000_000) return `${Math.round(value / 1_000)} KB`;
  return `${Math.round(value / 1_000_000)} MB`;
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function idempotencyKey(prefix: "backup-ui" | "restore-ui"): string {
  return `${prefix}-${Date.now().toString(36)}`;
}

function resultError(result: { error: { message: string } }): string {
  return result.error.message;
}

export function BackupPanel({
  client,
}: Readonly<{
  client: BackupClient;
}>) {
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [scope, setScope] = useState<BackupType>("DATABASE_ONLY");
  const [restoreTarget, setRestoreTarget] = useState<BackupRecord | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    void client
      .listBackups()
      .then((result) => {
        if (!active) return;
        if (!result.ok) {
          setError(resultError(result));
          return;
        }
        setBackups(result.data.data);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Backups could not be loaded.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [client]);

  const createBackup = async () => {
    if (pendingAction !== null) return;
    setPendingAction("create");
    setMessage(null);
    setError(null);
    const result = await client.createBackup(
      {
        backup_type: scope,
        include_original_files: false,
        include_exports: false,
        include_intermediate_files: false,
      },
      idempotencyKey("backup-ui"),
    );
    setPendingAction(null);
    if (!result.ok) {
      setError(resultError(result));
      return;
    }
    setMessage(`Backup queued: ${result.data.data.job_id}`);
  };

  const verifyBackup = async (backupId: string) => {
    if (pendingAction !== null) return;
    setPendingAction(`verify:${backupId}`);
    setMessage(null);
    setError(null);
    const result = await client.verifyBackup(backupId);
    setPendingAction(null);
    if (!result.ok) {
      setError(resultError(result));
      return;
    }
    setMessage(result.data.data.message);
  };

  const openRestore = (backup: BackupRecord) => {
    setRestoreTarget(backup);
    setConfirmation("");
    setMessage(null);
    setError(null);
  };

  const closeRestore = () => {
    if (pendingAction?.startsWith("restore:") === true) return;
    setRestoreTarget(null);
    setConfirmation("");
  };

  const restoreBackup = async () => {
    if (restoreTarget === null || confirmation !== "RESTORE" || pendingAction !== null) return;
    setPendingAction(`restore:${restoreTarget.id}`);
    setMessage(null);
    setError(null);
    const result = await client.restoreBackup(
      restoreTarget.id,
      { confirmation: "RESTORE", create_pre_restore_backup: true, restore_files: true },
      idempotencyKey("restore-ui"),
    );
    setPendingAction(null);
    if (!result.ok) {
      setError(resultError(result));
      return;
    }
    setRestoreTarget(null);
    setConfirmation("");
    setMessage(`Restore accepted: ${result.data.data.job_id}`);
  };

  return (
    <section aria-labelledby="backup-panel-heading" className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Backups</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="backup-panel-heading">
          Backup and restore
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Create verified local backups and restore only after an explicit confirmation.
        </p>
      </header>

      {error !== null ? <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{error}</p> : null}
      {message !== null ? <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">{message}</p> : null}

      <section aria-labelledby="create-backup-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-950" id="create-backup-heading">Create backup</h2>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="text-sm font-medium text-slate-800" htmlFor="backup-scope">
            Backup scope
            <select
              className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 font-normal"
              id="backup-scope"
              onChange={(event) => setScope(event.target.value as BackupType)}
              value={scope}
            >
              {BACKUP_TYPES.map((type) => <option key={type} value={type}>{label(type)}</option>)}
            </select>
          </label>
          <button
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void createBackup()}
            type="button"
          >
            {pendingAction === "create" ? "Creating…" : "Create backup"}
          </button>
        </div>
      </section>

      <section aria-labelledby="backup-list-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">History</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950" id="backup-list-heading">Available backups</h2>
          </div>
          <p className="text-sm text-slate-600">{backups.length} backup(s)</p>
        </div>
        {isLoading ? (
          <p className="mt-4 text-sm text-slate-600" role="status">Loading backups…</p>
        ) : backups.length === 0 ? (
          <p className="mt-4 text-sm text-slate-600" role="status">No backups found.</p>
        ) : (
          <ul aria-label="Backup list" className="mt-4 divide-y divide-slate-200">
            {backups.map((backup) => (
              <li className="py-4 first:pt-0 last:pb-0" key={backup.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">{backup.filename}</p>
                    <p className="mt-1 text-sm text-slate-600">
                      {label(backup.backup_type)} · {formatBackupSize(backup.size_bytes)} · {backup.status}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{backup.id} · schema {backup.database_schema_version}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={pendingAction !== null || backup.status !== "COMPLETED"}
                      onClick={() => void verifyBackup(backup.id)}
                      type="button"
                    >
                      {pendingAction === `verify:${backup.id}` ? "Verifying…" : "Verify backup"}
                    </button>
                    <button
                      className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-950 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={pendingAction !== null || backup.status !== "COMPLETED"}
                      onClick={() => openRestore(backup)}
                      type="button"
                    >
                      Restore backup
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {restoreTarget !== null ? (
        <div aria-labelledby="restore-confirmation-heading" aria-modal="true" className="rounded-2xl border-2 border-amber-400 bg-amber-50 p-5" role="dialog">
          <h2 className="text-xl font-semibold text-amber-950" id="restore-confirmation-heading">Confirm restore</h2>
          <div className="mt-3 rounded-xl border border-amber-300 bg-white p-4 text-sm text-amber-950" role="alert">
            Restoring this backup will replace local application state and may put the API in maintenance mode. Verify the archive before proceeding.
          </div>
          <label className="mt-4 block text-sm font-medium text-amber-950" htmlFor="restore-confirmation">
            Type RESTORE to continue
            <input
              aria-label="Restore confirmation"
              className="mt-1 block w-full max-w-sm rounded-lg border border-amber-400 px-3 py-2 font-normal text-slate-950"
              id="restore-confirmation"
              onChange={(event) => setConfirmation(event.target.value)}
              value={confirmation}
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={confirmation !== "RESTORE" || pendingAction !== null}
              onClick={() => void restoreBackup()}
              type="button"
            >
              {pendingAction?.startsWith("restore:") === true ? "Restoring…" : "Confirm restore"}
            </button>
            <button
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={pendingAction !== null}
              onClick={closeRestore}
              type="button"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export { formatBackupSize, idempotencyKey };
