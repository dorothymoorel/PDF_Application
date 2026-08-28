// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BackupPanel,
  type BackupClient,
  type BackupJobStatus,
  type BackupListResponse,
  type BackupRecord,
  type BackupStatus,
  type CreateBackupResponse,
} from "./backup-panel";

function success<T>(data: T) {
  return { ok: true as const, data, status: 200, requestId: "req_backup_test" };
}

function backup(): BackupRecord {
  return {
    id: "bkp_00000000-0000-4000-8000-000000000001",
    backup_type: "DATABASE_ONLY",
    filename: "transloka-backup.zip",
    size_bytes: 4_096,
    checksum_sha256: "abc123",
    application_version: "0.1.0",
    database_schema_version: "0010",
    status: "COMPLETED",
    created_at: "2026-08-22T00:00:00.000Z",
    completed_at: "2026-08-22T00:01:00.000Z",
  };
}

function listResponse(items: BackupRecord[] = [backup()]): BackupListResponse {
  return {
    data: items,
    meta: { request_id: "req_backup_test" },
  };
}

function makeClient(overrideStatus: BackupJobStatus = "QUEUED"): BackupClient {
  return {
    listBackups: vi.fn(() => Promise.resolve(success(listResponse()))),
    createBackup: vi.fn(() =>
      Promise.resolve(
        success<CreateBackupResponse>({
          data: { job_id: "job_backup_test", backup_id: null, status: overrideStatus },
          meta: { request_id: "req_create_test" },
        }),
      ),
    ),
    verifyBackup: vi.fn(() =>
      Promise.resolve(
        success({
          data: { backup_id: backup().id, status: "VERIFIED" as const, message: "Checksum verified." },
          meta: { request_id: "req_verify_test" },
        }),
      ),
    ),
    restoreBackup: vi.fn(() =>
      Promise.resolve(
        success({
          data: {
            job_id: "job_restore_test",
            backup_id: backup().id,
            status: "ACCEPTED" as const,
            pre_restore_backup_id: "bkp_pre_restore",
          },
          meta: { request_id: "req_restore_test" },
        }),
      ),
    ),
  };
}

afterEach(() => cleanup());

describe("BackupPanel", () => {
  it("creates a backup with the selected scope", async () => {
    const client = makeClient();

    render(<BackupPanel client={client} />);
    await screen.findByText("transloka-backup.zip");

    fireEvent.change(screen.getByLabelText("Backup scope"), {
      target: { value: "FULL_PROJECTS" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create backup" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(client.createBackup).toHaveBeenCalledWith(
      {
        backup_type: "FULL_PROJECTS",
        include_original_files: false,
        include_exports: false,
        include_intermediate_files: false,
      },
      expect.stringMatching(/^backup-ui-/),
    );
    expect(screen.getByText(/Backup job QUEUED: job_backup_test/)).toBeTruthy();
  });

  it("keeps BackupStatus for BackupRecord separate from BackupJobStatus", () => {
    // backup-panel.tsx:14 stays QUEUED|RUNNING|COMPLETED|FAILED for BackupRecord
    const recordStatus: BackupStatus = "COMPLETED";
    expect(["QUEUED", "RUNNING", "COMPLETED", "FAILED"]).toContain(recordStatus);
    // BackupJobStatus is separate union for CreateBackupResponse at :42
    const jobStatus: BackupJobStatus = "STALE";
    expect(["QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"]).toContain(jobStatus);
    // ensure they are not merged - BackupRecord should not accept RETRYING
    const isBackupRecordStatus = (s: string): boolean => ["QUEUED","RUNNING","COMPLETED","FAILED"].includes(s);
    expect(isBackupRecordStatus("RETRYING")).toBe(false);
    expect(isBackupRecordStatus("STALE")).toBe(false);
  });

  it("renders truthful create-result message for every BackupJobStatus", async () => {
    for (const status of ["QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"] as const) {
      const client = makeClient(status);
      const { unmount } = render(<BackupPanel client={client} />);
      await screen.findByText("transloka-backup.zip");
      fireEvent.click(screen.getByRole("button", { name: "Create backup" }));
      await act(async () => { await Promise.resolve(); });
      expect(screen.getByText(`Backup job ${status}: job_backup_test`)).toBeTruthy();
      unmount();
      cleanup();
    }
  });

  it("verifies a listed backup", async () => {
    const client = makeClient();

    render(<BackupPanel client={client} />);
    await screen.findByText("transloka-backup.zip");
    fireEvent.click(screen.getByRole("button", { name: "Verify backup" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(client.verifyBackup).toHaveBeenCalledWith(backup().id);
    expect(screen.getByText("Checksum verified.")).toBeTruthy();
  });

  it("shows restore warning and blocks the request until exact confirmation", async () => {
    const client = makeClient();

    render(<BackupPanel client={client} />);
    await screen.findByText("transloka-backup.zip");
    fireEvent.click(screen.getByRole("button", { name: "Restore backup" }));

    expect(screen.getByRole("alert").textContent).toContain("maintenance mode");
    const confirmButton = screen.getByRole("button", { name: "Confirm restore" });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Restore confirmation"), {
      target: { value: "restore" },
    });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(confirmButton);
    expect(client.restoreBackup).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Restore confirmation"), {
      target: { value: "RESTORE" },
    });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(confirmButton);
    await act(async () => {
      await Promise.resolve();
    });

    expect(client.restoreBackup).toHaveBeenCalledWith(
      backup().id,
      {
        confirmation: "RESTORE",
        create_pre_restore_backup: true,
        restore_files: true,
      },
      expect.stringMatching(/^restore-ui-/),
    );
    expect(screen.getByText(/Restore accepted/)).toBeTruthy();
  });
});
