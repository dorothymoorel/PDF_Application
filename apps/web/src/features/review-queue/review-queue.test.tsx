// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiResult } from "@transloka/api-client";

import { ReviewQueue, type ReviewQueueClient, type ReviewQueueResponse } from "./index";
import type { ReviewQueueItem, ReviewQueueSegment } from "./types";

function success(data: ReviewQueueResponse): ApiResult<ReviewQueueResponse> {
  return { ok: true, data, status: 200, requestId: "req_review_queue_test" };
}

function segment(id: string, sourceText: string, globalOrder: number): ReviewQueueSegment {
  return {
    id,
    block_id: `blk_${id.slice(4)}`,
    section_id: null,
    segment_order: globalOrder,
    global_order: globalOrder,
    source_text: sourceText,
    resolved_source_text: sourceText,
    machine_translation: `Translation: ${sourceText}`,
    reviewed_translation: null,
    final_text: null,
    source_language: "en",
    target_language: "id",
    status: "NEEDS_REVIEW",
    review_status: "REVIEW_REQUIRED",
    is_locked: false,
    current_revision: 1,
    confidence: { overall: 0.5 },
    warning_count: 0,
  };
}

function item(nextSegment: ReviewQueueSegment): ReviewQueueItem {
  return {
    page_id: "pag_00000000-0000-4000-8000-000000000001",
    segment: nextSegment,
    warnings: [],
    source_context: {
      previous_segment: null,
      next_segment: null,
      heading: "Chapter 1",
    },
  };
}

function response(items: ReviewQueueItem[]): ReviewQueueResponse {
  return {
    data: items,
    meta: {
      request_id: "req_review_queue_test",
      pagination: { limit: 20, next_cursor: null, has_more: false },
    },
  };
}

function makeClient(items: ReviewQueueItem[]) {
  const listReviewQueue = vi.fn<ReviewQueueClient["listReviewQueue"]>(() =>
    Promise.resolve(success(response(items))),
  );
  return {
    client: { listReviewQueue } satisfies ReviewQueueClient,
    listReviewQueue,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReviewQueue", () => {
  it("passes warning, confidence, status, page, and section filters to the client", async () => {
    const first = item(segment("seg_00000000-0000-4000-8000-000000000001", "First", 1));
    const { client, listReviewQueue } = makeClient([first]);
    render(<ReviewQueue client={client} onSelectSegment={vi.fn()} projectId="prj_test" />);
    await screen.findByText("First");

    fireEvent.change(screen.getByLabelText("Warning"), { target: { value: "true" } });
    fireEvent.change(screen.getByLabelText("Confidence max"), { target: { value: "0.7" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "REVIEW_REQUIRED" } });
    fireEvent.change(screen.getByLabelText("Page ID"), { target: { value: "pag_1" } });
    fireEvent.change(screen.getByLabelText("Section ID"), { target: { value: "sec_1" } });

    await waitFor(() => {
      const lastCall = listReviewQueue.mock.calls[listReviewQueue.mock.calls.length - 1];
      expect(lastCall?.[0]).toBe("prj_test");
      expect(lastCall?.[1]).toEqual({
        confidence_max: 0.7,
        page_id: "pag_1",
        section_id: "sec_1",
        status: "REVIEW_REQUIRED",
        warning: true,
      });
    });
  });

  it("renders items in the API-provided reading order", async () => {
    const second = item(segment("seg_00000000-0000-4000-8000-000000000002", "Second", 2));
    const first = item(segment("seg_00000000-0000-4000-8000-000000000001", "First", 1));
    const { client } = makeClient([first, second]);
    render(<ReviewQueue client={client} onSelectSegment={vi.fn()} projectId="prj_test" />);

    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]?.textContent).toContain("First");
    expect(rows[1]?.textContent).toContain("Second");
  });

  it("renders an empty state when no segment requires review", async () => {
    const { client } = makeClient([]);
    render(<ReviewQueue client={client} onSelectSegment={vi.fn()} projectId="prj_test" />);

    expect((await screen.findByRole("status")).textContent).toContain("No segments require review.");
  });

  it("navigates directly to the selected segment", async () => {
    const first = item(segment("seg_00000000-0000-4000-8000-000000000001", "First", 1));
    const onSelectSegment = vi.fn();
    const { client } = makeClient([first]);
    render(<ReviewQueue client={client} onSelectSegment={onSelectSegment} projectId="prj_test" />);

    fireEvent.click(await screen.findByRole("button", { name: /First/ }));
    expect(onSelectSegment).toHaveBeenCalledWith(first.segment.id, first.page_id);
  });
});
