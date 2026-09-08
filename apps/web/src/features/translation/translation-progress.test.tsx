// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TranslationProgress } from "./translation-progress";
import type { TranslationStatus, TranslationUiClient } from "./types";

function result(status: TranslationStatus) {
  return {
    ok: true as const,
    data: { data: status, meta: { request_id: "translation-status" } },
    status: 200,
    requestId: "translation-status",
  };
}

function statusWith(overrides: Partial<TranslationStatus> = {}): TranslationStatus {
  return {
    status: "RUNNING",
    total_segments: 20,
    completed_segments: 8,
    failed_segments: 0,
    review_required_segments: 1,
    progress: 0.4,
    active_job_id: "job_translation_1",
    current_batch: 2,
    total_batches: 5,
    ...overrides,
  };
}

function clientWith(status: TranslationStatus): TranslationUiClient {
  return {
    getTranslationReadiness: vi.fn(),
    startTranslation: vi.fn(),
    getTranslationStatus: vi.fn().mockResolvedValue(result(status)),
    cancelTranslation: vi.fn().mockResolvedValue(result({ ...status, status: "CANCELLATION_REQUESTED" })),
    retryFailedTranslation: vi.fn().mockResolvedValue(result({ ...status, status: "RETRYING" })),
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

describe("translation progress", () => {
  it("keeps document coverage visible when a job fails and batches are unknown", async () => {
    render(<TranslationProgress projectId="prj_1" client={clientWith(statusWith({
      status: "FAILED", completed_segments: 10, total_segments: 20, progress: 0.5,
      current_batch: 0, total_batches: 0,
    }))} />);
    await settle();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("10 of 20 segments")).toBeTruthy();
    expect(screen.getByText("Saved translations across the document")).toBeTruthy();
    expect(screen.getByText(/Job batch count is not available yet/)).toBeTruthy();
    expect(screen.queryByText(/Batch 0 of 0/)).toBeNull();
  });

  it("labels persisted batch counts as job work, separate from document coverage", async () => {
    render(<TranslationProgress projectId="prj_1" client={clientWith(statusWith())} />);
    await settle();
    expect(screen.getByText(/Job batches processed: 2 of 5/)).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
  });

  it("renders running progress and allows cancellation", async () => {
    const client = clientWith(statusWith());
    render(<TranslationProgress client={client} pollIntervalMs={10_000} projectId="prj_1" />);
    await settle();

    expect(screen.getByText("Running")).toBeTruthy();
    expect(screen.getByText("8 of 20 segments")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel translation" }));
    await settle();
    expect(client.cancelTranslation).toHaveBeenCalledWith("prj_1", { reason: "Cancelled by user." });
  });

  it("shows failed segments and retries them", async () => {
    const client = clientWith(statusWith({ status: "FAILED", failed_segments: 3, progress: 0.65 }));
    render(<TranslationProgress client={client} projectId="prj_1" />);
    await settle();

    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("3 segment(s) failed and can be retried with a smaller batch.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry failed segments" }));
    await settle();
    expect(client.retryFailedTranslation).toHaveBeenCalledWith(
      "prj_1",
      expect.stringContaining("translation-ui-retry-prj_1-"),
      { use_smaller_batch: true, use_selected_model: true },
    );
  });

  it("refreshes a stale terminal result when a sibling starts a new job", async () => {
    const failed = statusWith({ status: "FAILED", active_job_id: "job_old", failed_segments: 2 });
    const running = statusWith({ status: "RUNNING", active_job_id: "job_new", completed_segments: 9, progress: 0.45 });
    const client: TranslationUiClient = {
      ...clientWith(failed),
      getTranslationStatus: vi
        .fn()
        .mockResolvedValueOnce(result(failed))
        .mockResolvedValueOnce(result(running)),
    };
    const view = render(
      <TranslationProgress client={client} pollIntervalMs={10_000} projectId="prj_1" refreshToken={0} />,
    );
    await settle();
    expect(screen.getByText("Failed")).toBeTruthy();

    view.rerender(
      <TranslationProgress client={client} pollIntervalMs={10_000} projectId="prj_1" refreshToken={1} />,
    );

    await waitFor(() => expect(screen.getByText("Running")).toBeTruthy());
    expect(screen.getByText("9 of 20 segments")).toBeTruthy();
  });

  it("renders completed state without active actions", async () => {
    vi.useFakeTimers();
    const client = clientWith(
      statusWith({ status: "COMPLETED", completed_segments: 20, progress: 1, active_job_id: null }),
    );
    render(<TranslationProgress client={client} projectId="prj_1" />);
    await settle();

    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel translation" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry failed segments" })).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(client.getTranslationStatus).toHaveBeenCalledTimes(1);
  });
});
