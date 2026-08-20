// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiResult } from "@transloka/api-client";

import { OCRReview, type OCRReviewClient, type OCRReviewResponse, type OCRReviewSegment } from "./index";

const FIRST_SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000001";
const SECOND_SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000002";

const FIRST_SEGMENT: OCRReviewSegment = {
  id: FIRST_SEGMENT_ID,
  block_id: "blk_00000000-0000-4000-8000-000000000001",
  source_text: "First resolved source.",
  resolved_source_text: "First resolved source.",
  raw_ocr_text: "First raw OCR.",
  normalized_source_text: "First resolved source.",
  current_revision: 1,
  is_locked: false,
  confidence: { overall: 0.92 },
  status: "READY_FOR_TRANSLATION",
};

const SECOND_SEGMENT: OCRReviewSegment = {
  ...FIRST_SEGMENT,
  id: SECOND_SEGMENT_ID,
  block_id: "blk_00000000-0000-4000-8000-000000000002",
  source_text: "Second resolved source.",
  resolved_source_text: "Second resolved source.",
  raw_ocr_text: "Second raw OCR.",
  normalized_source_text: "Second resolved source.",
  current_revision: 3,
  confidence: { overall: 0.8 },
};

function success<T>(data: T): ApiResult<T> {
  return { ok: true, data, status: 200, requestId: "req_ocr_test" };
}

function failure<T>(code: string, message: string): ApiResult<T> {
  return {
    ok: false,
    error: { kind: "api", code, details: {}, message, requestId: "req_ocr_test" },
    status: 409,
    requestId: "req_ocr_test",
  };
}

function pageResult(
  segments: OCRReviewSegment[] = [FIRST_SEGMENT, SECOND_SEGMENT],
  ocrConfidence = 0.92,
): ApiResult<OCRReviewResponse> {
  return success({
    data: {
      page_id: "pag_00000000-0000-4000-8000-000000000001",
      raw_text: "First raw OCR.\nSecond raw OCR.",
      resolved_source_text: "First resolved source.\nSecond resolved source.",
      ocr_confidence: ocrConfidence,
      segments,
    },
    meta: { request_id: "req_ocr_test" },
  });
}

function makeClient(
  page: ApiResult<OCRReviewResponse> = pageResult(),
  save: OCRReviewClient["resolveSegmentSource"] = () =>
    Promise.resolve(
      success({
        data: { ...FIRST_SEGMENT, resolution_source: "MANUAL" },
        meta: { request_id: "req_ocr_test" },
      }),
    ),
) {
  return {
    getPageOcr: vi.fn(() => Promise.resolve(page)),
    resolveSegmentSource: vi.fn(save),
  } satisfies OCRReviewClient & {
    getPageOcr: ReturnType<typeof vi.fn>;
    resolveSegmentSource: ReturnType<typeof vi.fn>;
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("OCRReview", () => {
  it("shows a warning when OCR confidence is low", async () => {
    const client = makeClient(pageResult([FIRST_SEGMENT], 0.42));

    render(<OCRReview client={client} pageId="page-1" pageImageUrl="/page-1.png" />);

    expect(await screen.findByText("Low OCR confidence")).toBeTruthy();
    expect(screen.getByText("Confidence: 42%")).toBeTruthy();
  });

  it("keeps raw OCR read-only and allows resolved source edits", async () => {
    const client = makeClient(pageResult([FIRST_SEGMENT]));

    render(<OCRReview client={client} pageId="page-1" pageImageUrl="/page-1.png" />);

    expect(await screen.findByRole("img", { name: "OCR source page" })).toBeTruthy();
    expect(screen.getByLabelText<HTMLTextAreaElement>("Raw OCR").value).toBe("First raw OCR.");

    const resolvedSource = screen.getByLabelText<HTMLTextAreaElement>("Resolved source");
    expect(resolvedSource.value).toBe("First resolved source.");
    expect(resolvedSource.readOnly).toBe(false);
    fireEvent.change(resolvedSource, { target: { value: "Corrected source." } });
    await waitFor(() => expect(resolvedSource.value).toBe("Corrected source."));
  });

  it("saves a source correction with the current revision and explains retranslation", async () => {
    const client = makeClient(pageResult([FIRST_SEGMENT]));

    render(<OCRReview client={client} pageId="page-1" pageImageUrl="/page-1.png" />);
    const resolvedSource = await screen.findByLabelText<HTMLTextAreaElement>("Resolved source");
    fireEvent.change(resolvedSource, { target: { value: "Corrected source." } });
    fireEvent.click(screen.getByRole("button", { name: "Save source correction" }));

    await waitFor(() => expect(client.resolveSegmentSource).toHaveBeenCalledTimes(1));
    expect(client.resolveSegmentSource).toHaveBeenCalledWith(FIRST_SEGMENT_ID, {
      resolved_source_text: "Corrected source.",
      resolution_source: "MANUAL",
      expected_revision: 1,
    });
    expect(
      await screen.findByText(/Re-translation may be required because this correction invalidates/i),
    ).toBeTruthy();
  });

  it("shows a reload action when save loses a revision conflict", async () => {
    const client = makeClient(
      pageResult([FIRST_SEGMENT]),
      () => Promise.resolve(failure("REVISION_CONFLICT", "The segment was changed by another reviewer.")),
    );

    render(<OCRReview client={client} pageId="page-1" pageImageUrl="/page-1.png" />);
    await screen.findByLabelText("Resolved source");
    fireEvent.click(screen.getByRole("button", { name: "Save source correction" }));

    expect(await screen.findByRole("alertdialog", { name: "OCR source conflict" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload OCR page" })).toBeTruthy();
  });

  it("navigates between OCR segments", async () => {
    const client = makeClient();

    render(<OCRReview client={client} pageId="page-1" pageImageUrl="/page-1.png" />);
    const resolvedSource = await screen.findByLabelText<HTMLTextAreaElement>("Resolved source");
    fireEvent.click(screen.getByRole("button", { name: "Next segment" }));
    await waitFor(() => expect(resolvedSource.value).toBe("Second resolved source."));

    fireEvent.click(screen.getByRole("button", { name: "Previous segment" }));
    await waitFor(() => expect(resolvedSource.value).toBe("First resolved source."));
  });
});
