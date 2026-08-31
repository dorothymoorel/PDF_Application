// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiResult } from "@transloka/api-client";

import type { PdfDocumentHandle, PdfDocumentLoader } from "../pdf-viewer/source-page-viewer";
import {
  ReviewEditor,
  type ReviewEditorClient,
  type ReviewPageData,
  type ReviewSegment,
} from "./index";

const FIRST_BLOCK_ID = "blk_00000000-0000-4000-8000-000000000001";
const SECOND_BLOCK_ID = "blk_00000000-0000-4000-8000-000000000002";
const FIRST_SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000001";
const SECOND_SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000002";

const PAGE_VIEW: ReviewPageData = {
  page: {
    id: "pag_00000000-0000-4000-8000-000000000001",
    document_id: "doc_00000000-0000-4000-8000-000000000001",
    source_page_number: 1,
    logical_page_number: "1",
    width_points: 600,
    height_points: 800,
    rotation_degrees: 0,
    page_type: "DIGITAL",
    page_classification: "SINGLE_COLUMN",
    column_count: 1,
    reading_direction: "LTR",
    status: "STRUCTURED",
    confidence: { native_extraction: 1, ocr: null, structure: 1 },
    preview: { thumbnail_url: null, render_url: null },
  },
  blocks: [
    {
      id: FIRST_BLOCK_ID,
      page_id: "pag_00000000-0000-4000-8000-000000000001",
      block_type: "PARAGRAPH",
      page_reading_order: 0,
      global_reading_order: 0,
      parent_block_id: null,
      section_id: null,
      semantic_role: "BODY_TEXT",
      source_text: "First source segment.",
      normalized_source_text: "First source segment.",
      source_geometry: {
        coordinate_system: "TOP_LEFT",
        x: 60,
        y: 160,
        width: 180,
        height: 80,
      },
      target_geometry: null,
      confidence: 1,
      status: "STRUCTURED",
    },
    {
      id: SECOND_BLOCK_ID,
      page_id: "pag_00000000-0000-4000-8000-000000000001",
      block_type: "PARAGRAPH",
      page_reading_order: 1,
      global_reading_order: 1,
      parent_block_id: null,
      section_id: null,
      semantic_role: "BODY_TEXT",
      source_text: "Second source segment.",
      normalized_source_text: "Second source segment.",
      source_geometry: {
        coordinate_system: "TOP_LEFT",
        x: 300,
        y: 400,
        width: 240,
        height: 120,
      },
      target_geometry: null,
      confidence: 1,
      status: "STRUCTURED",
    },
  ],
  segments: [
    {
      id: FIRST_SEGMENT_ID,
      block_id: FIRST_BLOCK_ID,
      source_text: "First source segment.",
      resolved_source_text: "First source segment.",
      source_language: "eng",
      target_language: "ind",
      machine_translation: "Terjemahan pertama.",
      reviewed_translation: null,
      final_text: null,
      current_revision: 1,
      review_status: "NOT_REVIEWED",
      is_locked: false,
      segment_order: 0,
      global_order: 0,
      section_id: null,
      status: "MACHINE_TRANSLATED",
      warning_count: 0,
      confidence: { overall: 0.9 },
    },
    {
      id: SECOND_SEGMENT_ID,
      block_id: SECOND_BLOCK_ID,
      source_text: "Second source segment.",
      resolved_source_text: "Second source segment.",
      source_language: "eng",
      target_language: "ind",
      machine_translation: "Terjemahan kedua.",
      reviewed_translation: null,
      final_text: null,
      current_revision: 3,
      review_status: "REVIEW_REQUIRED",
      is_locked: false,
      segment_order: 1,
      global_order: 1,
      section_id: null,
      status: "NEEDS_REVIEW",
      warning_count: 0,
      confidence: { overall: 0.7 },
    },
  ],
  warnings: [],
};

const FIRST_SEGMENT = PAGE_VIEW.segments[0]!;
const SECOND_SEGMENT = PAGE_VIEW.segments[1]!;

function success<T>(data: T): ApiResult<T> {
  return { ok: true, data, status: 200, requestId: "req_editor_test" };
}

function failure<T>(message: string): ApiResult<T> {
  return {
    ok: false,
    error: { kind: "network", message },
    status: null,
    requestId: null,
  };
}

type PageResponse = {
  data: ReviewPageData;
  meta: { request_id: string };
};

type SegmentResponse = {
  data: ReviewSegment;
  meta: { request_id: string };
};

function pageResult(page = PAGE_VIEW): ApiResult<PageResponse> {
  return success({ data: page, meta: { request_id: "req_editor_test" } });
}

function fakePdf(): PdfDocumentLoader {
  const document = {
    numPages: 1,
    getPage: vi.fn(() =>
      Promise.resolve({
        getViewport: vi.fn(({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        })),
        render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      }),
    ),
    destroy: vi.fn(() => Promise.resolve()),
  } satisfies PdfDocumentHandle;

  return vi.fn(() => Promise.resolve(document));
}

function makeClient(
  pageResponse: ApiResult<PageResponse> | Promise<ApiResult<PageResponse>> = pageResult(),
): ReviewEditorClient & {
  approveSegment: ReturnType<typeof vi.fn>;
  unapproveSegment: ReturnType<typeof vi.fn>;
  getPageEditorView: ReturnType<typeof vi.fn>;
  editSegmentTranslation: ReturnType<typeof vi.fn>;
} {
  const getPageEditorView = vi.fn(async () => await pageResponse);
  const editSegmentTranslation = vi.fn((): Promise<ApiResult<SegmentResponse>> =>
    Promise.resolve(
      success({
        data: FIRST_SEGMENT,
        meta: { request_id: "req_editor_test" },
      }),
    ),
  );
  const approveSegment = vi.fn((): Promise<ApiResult<SegmentResponse>> =>
    Promise.resolve(
      success({
        data: FIRST_SEGMENT,
        meta: { request_id: "req_editor_approve" },
      }),
    ),
  );
  const unapproveSegment = vi.fn((): Promise<ApiResult<SegmentResponse>> =>
    Promise.resolve(
      success({
        data: FIRST_SEGMENT,
        meta: { request_id: "req_editor_unapprove" },
      }),
    ),
  );
  return { approveSegment, editSegmentTranslation, getPageEditorView, unapproveSegment };
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    {} as CanvasRenderingContext2D,
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ReviewEditor", () => {
  it("selects a segment and updates the source and translation panels", async () => {
    const client = makeClient();
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    expect((await screen.findAllByText("First source segment.")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Second source segment." }));

    expect(screen.getAllByText("Second source segment.").length).toBeGreaterThan(0);
    expect(screen.getByLabelText<HTMLTextAreaElement>("Reviewed translation").value).toBe(
      "Terjemahan kedua.",
    );
  });

  it("exposes labeled keyboard segment navigation and warning text", async () => {
    const pageWithWarning: ReviewPageData = {
      ...PAGE_VIEW,
      warnings: [
        {
          id: "war_00000000-0000-4000-8000-000000000001",
          project_id: "pro_00000000-0000-4000-8000-000000000001",
          document_id: PAGE_VIEW.page.document_id,
          page_id: PAGE_VIEW.page.id,
          segment_id: FIRST_SEGMENT_ID,
          warning_type: "LOW_CONFIDENCE",
          severity: "HIGH",
          status: "OPEN",
          message: "Review the terminology before approval.",
          details: {},
          created_at: "2026-01-01T00:00:00Z",
          resolved_at: null,
        },
      ],
    };
    const client = makeClient(pageResult(pageWithWarning));
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    expect(await screen.findByRole("navigation", { name: "Segment navigation" })).toBeTruthy();
    expect(screen.getByLabelText("Reviewed translation")).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Previous segment" }).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Next segment" }));
    expect(screen.getByText("Segment 2 of 2")).toBeTruthy();
    expect(screen.getByText("Warning — LOW_CONFIDENCE (HIGH)")).toBeTruthy();
    expect(screen.getByText("Status: OPEN")).toBeTruthy();
  });

  it("edits and saves the selected translation", async () => {
    const updatedSegment = {
      ...FIRST_SEGMENT,
      current_revision: 2,
      final_text: "Terjemahan yang ditinjau.",
      reviewed_translation: "Terjemahan yang ditinjau.",
      review_status: "EDITED" as const,
      status: "USER_EDITED" as const,
    };
    const client = makeClient();
    client.editSegmentTranslation.mockResolvedValue(
      success({ data: updatedSegment, meta: { request_id: "req_save" } }),
    );
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    const editor = await screen.findByLabelText("Reviewed translation");
    fireEvent.change(editor, { target: { value: "  Terjemahan yang ditinjau.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save translation" }));

    await waitFor(() =>
      expect(client.editSegmentTranslation).toHaveBeenCalledWith(FIRST_SEGMENT_ID, {
        expected_revision: 1,
        reviewed_translation: "Terjemahan yang ditinjau.",
      }),
    );
    expect(await screen.findByText("Translation saved.")).toBeTruthy();
    expect(screen.getByLabelText<HTMLTextAreaElement>("Reviewed translation").value).toBe(
      "Terjemahan yang ditinjau.",
    );
  });

  it("approves the selected translation at its current revision", async () => {
    const approvedSegment = {
      ...FIRST_SEGMENT,
      current_revision: 2,
      final_text: FIRST_SEGMENT.reviewed_translation,
      review_status: "APPROVED" as const,
      status: "APPROVED" as const,
    };
    const client = makeClient();
    client.approveSegment.mockResolvedValue(
      success({ data: approvedSegment, meta: { request_id: "req_approve" } }),
    );
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    await screen.findByLabelText("Reviewed translation");
    fireEvent.click(screen.getByRole("button", { name: "Approve translation" }));

    await waitFor(() =>
      expect(client.approveSegment).toHaveBeenCalledWith(FIRST_SEGMENT_ID, {
        expected_revision: 1,
        lock_after_approval: false,
      }),
    );
    expect(await screen.findByText("Translation approved.")).toBeTruthy();
  });

  it("reopens an approved translation for revision", async () => {
    const approvedSegment = {
      ...FIRST_SEGMENT,
      review_status: "APPROVED" as const,
      status: "APPROVED" as const,
    };
    const reopenedSegment = {
      ...approvedSegment,
      current_revision: 2,
      review_status: "EDITED" as const,
      status: "USER_EDITED" as const,
    };
    const client = makeClient(pageResult({ ...PAGE_VIEW, segments: [approvedSegment] }));
    client.unapproveSegment.mockResolvedValue(
      success({ data: reopenedSegment, meta: { request_id: "req_unapprove" } }),
    );
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    await screen.findByLabelText("Reviewed translation");
    fireEvent.click(screen.getByRole("button", { name: "Reopen translation" }));

    await waitFor(() =>
      expect(client.unapproveSegment).toHaveBeenCalledWith(FIRST_SEGMENT_ID, {
        expected_revision: 1,
        reason: "Reopened for translation revision.",
      }),
    );
    expect(await screen.findByText("Translation reopened.")).toBeTruthy();
  });

  it("shows an API failure and allows retry", async () => {
    const client = makeClient(failure("API unavailable"));
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    expect((await screen.findByRole("alert")).textContent).toContain("API unavailable");
    client.getPageEditorView.mockResolvedValue(pageResult());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect((await screen.findAllByText("First source segment.")).length).toBeGreaterThan(0);
    expect(client.getPageEditorView).toHaveBeenCalledTimes(2);
  });

  it("renders a loading state while the page request is pending", async () => {
    let resolvePage!: (result: ApiResult<PageResponse>) => void;
    const pending = new Promise<ApiResult<PageResponse>>((resolve) => {
      resolvePage = resolve;
    });
    const client = makeClient(pending);
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    expect(screen.getByRole("status").textContent).toContain("Loading review editor");
    resolvePage(pageResult());
    expect((await screen.findAllByText("First source segment.")).length).toBeGreaterThan(0);
  });

  it("disables editing for a locked segment", async () => {
    const lockedPage: ReviewPageData = {
      ...PAGE_VIEW,
      segments: [{ ...FIRST_SEGMENT, is_locked: true, status: "LOCKED" }, SECOND_SEGMENT],
    };
    const client = makeClient(pageResult(lockedPage));
    render(
      <ReviewEditor
        client={client}
        loadDocument={fakePdf()}
        pageId={PAGE_VIEW.page.id}
        pdfUrl="/source.pdf"
      />,
    );

    const editor = await screen.findByLabelText<HTMLTextAreaElement>("Reviewed translation");
    expect(editor.disabled).toBe(true);
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Save translation" }).disabled,
    ).toBe(true);
    expect(screen.getByText("Editing is disabled.")).toBeTruthy();
    expect(screen.getByText("Locked")).toBeTruthy();
  });
});
