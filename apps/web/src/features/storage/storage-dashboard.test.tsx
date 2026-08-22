// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  StorageDashboard,
  type CleanupPreviewResponse,
  type StorageClient,
  type StorageUsageResponse,
} from "./storage-dashboard";

function success<T>(data: T) {
  return { ok: true as const, data, status: 200, requestId: "req_storage_test" };
}

function usageResponse(): StorageUsageResponse {
  return {
    data: {
      free_disk_bytes: 12_000,
      total_managed_bytes: 8_000,
      categories: {
        originals: 2_000,
        page_renders: 1_000,
        ocr: 500,
        intermediate: 1_500,
        exports: 2_000,
        backups: 1_000,
      },
    },
    meta: { request_id: "req_storage_test" },
  };
}

function cleanupResponse(): CleanupPreviewResponse {
  return {
    data: {
      job_id: "job_cleanup_test",
      operation: "TEMP_CLEANUP",
      status: "COMPLETED",
      healthy: true,
      dry_run: true,
      checked_count: 4,
      issue_count: 0,
      issues: [],
      orphans: [],
      candidates: ["temp/old-render.bin"],
      deleted: [],
      protected: ["projects/source.pdf"],
    },
    meta: { request_id: "req_cleanup_test" },
  };
}

function makeClient(): StorageClient {
  return {
    getStorageUsage: vi.fn(() => Promise.resolve(success(usageResponse()))),
    previewCleanup: vi.fn(() => Promise.resolve(success(cleanupResponse()))),
  };
}

afterEach(() => cleanup());

describe("StorageDashboard", () => {
  it("renders storage categories and disk totals", async () => {
    const client = makeClient();

    render(<StorageDashboard client={client} />);

    expect(await screen.findByText("Originals")).toBeTruthy();
    expect(screen.getByText("8 KB managed")).toBeTruthy();
    expect(screen.getByText("12 KB free")).toBeTruthy();
    expect(client.getStorageUsage).toHaveBeenCalledOnce();
  });

  it("requests a dry-run cleanup preview and shows protected files", async () => {
    const client = makeClient();

    render(<StorageDashboard client={client} />);
    await screen.findByText("Originals");

    fireEvent.click(screen.getByRole("button", { name: "Preview cleanup" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(client.previewCleanup).toHaveBeenCalledWith({
      older_than_days: 7,
      dry_run: true,
    });
    expect(screen.getByText("temp/old-render.bin")).toBeTruthy();
    expect(screen.getByText("projects/source.pdf")).toBeTruthy();
    expect(screen.getByText(/Dry run only/)).toBeTruthy();
  });
});
