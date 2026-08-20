// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BulkSegmentActions, type BulkSegmentActionClient } from ".";
import type { BulkSegmentActionResponse } from "./types";

const SEGMENTS = [
  { id: "seg-one", current_revision: 2, is_locked: false, source_text: "First" },
  { id: "seg-two", current_revision: 4, is_locked: true, source_text: "Second" },
] as const;

function success(results: BulkSegmentActionResponse["data"]["results"]): {
  ok: true;
  data: BulkSegmentActionResponse;
  status: number;
  requestId: string;
} {
  return {
    ok: true,
    data: {
      data: {
        action: "approve",
        results,
        succeeded: results.filter((result) => result.status === "SUCCEEDED").length,
        failed: results.filter((result) => result.status === "FAILED").length,
        queued: results.filter((result) => result.status === "QUEUED").length,
        job_id: null,
      },
      meta: { request_id: "bulk-ui-test" },
    },
    status: 200,
    requestId: "bulk-ui-test",
  };
}

afterEach(() => {
  cleanup();
});

describe("BulkSegmentActions", () => {
  it("submits selected IDs with their current revisions", async () => {
    const bulkSegmentAction = vi.fn<BulkSegmentActionClient["bulkSegmentAction"]>();
    bulkSegmentAction.mockResolvedValue(
      success([{ segment_id: "seg-one", status: "SUCCEEDED", current_revision: 3, error: null }]),
    );
    const client: BulkSegmentActionClient = { bulkSegmentAction };
    render(<BulkSegmentActions client={client} segments={SEGMENTS} />);

    fireEvent.click(screen.getByLabelText("Select First"));
    fireEvent.click(screen.getByRole("button", { name: "Apply action" }));

    await waitFor(() =>
      expect(bulkSegmentAction).toHaveBeenCalledWith(
        {
          action: "approve",
          selected_ids: ["seg-one"],
          expected_revisions: { "seg-one": 2 },
        },
        expect.anything(),
      ),
    );
    const options = bulkSegmentAction.mock.calls[0]?.[1];
    expect(options?.idempotencyKey).toMatch(/^editor-bulk-approve-/);
    expect(await screen.findByText(/1 succeeded/)).toBeTruthy();
  });

  it("shows partial failures and retries only failed IDs", async () => {
    const bulkSegmentAction = vi.fn<BulkSegmentActionClient["bulkSegmentAction"]>();
    bulkSegmentAction
      .mockResolvedValueOnce(
        success([
          { segment_id: "seg-one", status: "SUCCEEDED", current_revision: 3, error: null },
          {
            segment_id: "seg-two",
            status: "FAILED",
            current_revision: 4,
            error: { code: "SEGMENT_LOCKED", message: "Locked", details: {} },
          },
        ]),
      )
      .mockResolvedValueOnce(
        success([{ segment_id: "seg-two", status: "SUCCEEDED", current_revision: 5, error: null }]),
      );
    const client: BulkSegmentActionClient = { bulkSegmentAction };
    render(<BulkSegmentActions client={client} segments={SEGMENTS} />);

    fireEvent.click(screen.getByLabelText("Select all segments"));
    fireEvent.click(screen.getByRole("button", { name: "Apply action" }));
    expect(await screen.findByText(/Retry failed \(1\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry failed (1)" }));

    await waitFor(() =>
      expect(bulkSegmentAction).toHaveBeenLastCalledWith(
        {
          action: "approve",
          selected_ids: ["seg-two"],
          expected_revisions: { "seg-two": 4 },
        },
        expect.anything(),
      ),
    );
    const options = bulkSegmentAction.mock.calls[1]?.[1];
    expect(options?.idempotencyKey).toMatch(/^editor-bulk-approve-/);
  });
});
