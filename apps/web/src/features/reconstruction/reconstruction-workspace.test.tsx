// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReconstructionWorkspace } from "./reconstruction-workspace";
import type { ReconstructionReadiness, ReconstructionStatus, ReconstructionUiClient } from "./types";

function success<T>(data: T) {
  return {
    ok: true as const,
    data: { data, meta: { request_id: "reconstruction-test" } },
    status: 200,
    requestId: "reconstruction-test",
  };
}

function failure(message: string) {
  return {
    ok: false as const,
    error: { kind: "network" as const, message },
    status: null,
    requestId: null,
  };
}

const readiness: ReconstructionReadiness = {
  ready: true,
  blocking_issues: [],
  warnings: [],
  available_modes: ["OVERLAY", "REFLOW", "HYBRID"],
};

function statusWith(overrides: Partial<ReconstructionStatus> = {}): ReconstructionStatus {
  return {
    status: "RUNNING",
    progress: 0.4,
    completed_pages: 8,
    total_source_pages: 20,
    generated_target_pages: 21,
    warning_count: 1,
    critical_warning_count: 0,
    active_job_id: "job_reconstruction_1",
    ...overrides,
  };
}

function clientWith(status: ReconstructionStatus): ReconstructionUiClient {
  return {
    getReconstructionReadiness: vi.fn().mockResolvedValue(success(readiness)),
    previewReconstruction: vi.fn().mockResolvedValue(
      success({
        preview_id: "prv_preview_1",
        page_id: "pag_1",
        mode: "HYBRID",
        status: "READY",
        temporary: true,
        warnings: [],
      }),
    ),
    startReconstruction: vi.fn().mockResolvedValue(
      success({ job_id: "job_reconstruction_1", status: "QUEUED" }),
    ),
    getReconstructionStatus: vi.fn().mockResolvedValue(success(status)),
    cancelReconstruction: vi.fn().mockResolvedValue(success({ ...status, status: "CANCELLED" })),
    retryReconstructionPage: vi.fn().mockResolvedValue(
      success({ job_id: "job_reconstruction_retry", status: "RETRYING" }),
    ),
  };
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
  });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("reconstruction workspace", () => {
  it("uses BALANCED by default, changes mode, previews, and starts", async () => {
    const client = clientWith(statusWith({ status: "NOT_STARTED", progress: 0 }));
    render(<ReconstructionWorkspace client={client} pageId="pag_1" projectId="prj_1" />);
    await settle();

    expect(screen.getByLabelText<HTMLSelectElement>("Reconstruction profile").value).toBe("BALANCED");
    fireEvent.change(screen.getByLabelText("Reconstruction mode"), { target: { value: "REFLOW" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview page" }));
    await settle();
    expect(client.previewReconstruction).toHaveBeenCalledWith(
      "prj_1",
      expect.objectContaining({ page_id: "pag_1", mode: "REFLOW" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Start reconstruction" }));
    await settle();
    expect(client.startReconstruction).toHaveBeenCalled();
  });

  it("refreshes persisted progress after a completed result is reused", async () => {
    const completed = statusWith({ status: "COMPLETED", progress: 1, completed_pages: 2, total_source_pages: 2, generated_target_pages: 2 });
    const client = clientWith(completed);
    vi.mocked(client.getReconstructionStatus)
      .mockResolvedValueOnce(failure("The local API could not be reached."))
      .mockResolvedValueOnce(success(completed));
    vi.mocked(client.startReconstruction).mockResolvedValueOnce(
      success({ job_id: "job_reconstruction_1", status: "COMPLETED" }),
    );
    render(<ReconstructionWorkspace client={client} projectId="prj_1" />);
    await settle();

    fireEvent.click(screen.getByRole("button", { name: "Start reconstruction" }));
    await settle();
    await settle();

    expect(client.getReconstructionStatus).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText(/2 of 2 source pages/)).toBeTruthy();
  });

  it("renders running progress and allows cancellation", async () => {
    const client = clientWith(statusWith());
    render(<ReconstructionWorkspace client={client} pollIntervalMs={10_000} projectId="prj_1" />);
    await settle();

    expect(screen.getByText("Running")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel reconstruction" }));
    await settle();
    expect(client.cancelReconstruction).toHaveBeenCalledWith("prj_1");
  });

  it("shows failed state and retries a page", async () => {
    const client = clientWith(statusWith({ status: "FAILED", progress: 0.65 }));
    render(
      <ReconstructionWorkspace
        client={client}
        projectId="prj_1"
        reconstructionPageId="rcp_1"
      />,
    );
    await settle();

    expect(screen.getByText("Failed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry page with reflow" }));
    await settle();
    expect(client.retryReconstructionPage).toHaveBeenCalledWith(
      "rcp_1",
      expect.stringContaining("reconstruction-ui-retry-rcp_1-"),
      expect.objectContaining({ fallback_mode: "REFLOW" }),
    );
  });

  it("keeps critical warnings visible and blocks export", async () => {
    const client = clientWith(statusWith({ status: "COMPLETED", progress: 1, critical_warning_count: 1 }));
    const onCreateExport = vi.fn();
    render(<ReconstructionWorkspace client={client} onCreateExport={onCreateExport} projectId="prj_1" />);
    await settle();

    expect(screen.getByRole("alert").textContent).toContain("critical warning(s) block export");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Create export" }).disabled).toBe(true);
    expect(onCreateExport).not.toHaveBeenCalled();
  });
});
