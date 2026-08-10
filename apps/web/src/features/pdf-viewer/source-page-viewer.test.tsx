// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  type PdfDocumentHandle,
  type PdfDocumentLoader,
  SourcePageViewer,
  type SourcePageBlock,
  type SourcePageSegment,
} from "./source-page-viewer";

const BLOCKS: readonly SourcePageBlock[] = [
  {
    id: "blk_00000000-0000-4000-8000-000000000001",
    pageReadingOrder: 0,
    sourceGeometry: { x: 60, y: 160, width: 180, height: 80 },
  },
  {
    id: "blk_00000000-0000-4000-8000-000000000002",
    pageReadingOrder: 1,
    sourceGeometry: { x: 300, y: 400, width: 240, height: 120 },
  },
];

const FIRST_BLOCK_ID = "blk_00000000-0000-4000-8000-000000000001";
const SECOND_BLOCK_ID = "blk_00000000-0000-4000-8000-000000000002";

const SEGMENTS: readonly SourcePageSegment[] = [
  {
    id: "seg_00000000-0000-4000-8000-000000000001",
    blockId: FIRST_BLOCK_ID,
    sourceText: "First source segment.",
  },
  {
    id: "seg_00000000-0000-4000-8000-000000000002",
    blockId: SECOND_BLOCK_ID,
    sourceText: "Second source segment.",
  },
];

function fakePdf() {
  const cancel = vi.fn();
  const renderPage = vi.fn(() => ({ promise: Promise.resolve(), cancel }));
  const getViewport = vi.fn(({ scale }: { scale: number }) => ({
    width: 600 * scale,
    height: 800 * scale,
  }));
  const getPage = vi.fn(() => Promise.resolve({ getViewport, render: renderPage }));
  const destroy = vi.fn(() => Promise.resolve());
  const document = { numPages: 3, getPage, destroy } satisfies PdfDocumentHandle;
  const loadDocument = vi.fn(() => Promise.resolve(document)) satisfies PdfDocumentLoader;

  return { cancel, destroy, getPage, getViewport, loadDocument, renderPage };
}

function ViewerHarness({ loadDocument }: Readonly<{ loadDocument: PdfDocumentLoader }>) {
  const [pageNumber, setPageNumber] = useState(1);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  return (
    <>
      <SourcePageViewer
        blocks={BLOCKS}
        loadDocument={loadDocument}
        onPageChange={setPageNumber}
        onSelectSegment={setSelectedSegmentId}
        pageHeightPoints={800}
        pageNumber={pageNumber}
        pageWidthPoints={600}
        pdfUrl="/api/v1/documents/doc_1/original"
        segments={SEGMENTS}
        selectedSegmentId={selectedSegmentId}
      />
      <output aria-label="Current page">{pageNumber}</output>
      <output aria-label="Selected segment">{selectedSegmentId ?? "none"}</output>
    </>
  );
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

describe("source page viewer", () => {
  it("renders the requested PDF page and aligns block overlays", async () => {
    const pdf = fakePdf();
    render(<ViewerHarness loadDocument={pdf.loadDocument} />);

    await waitFor(() => expect(pdf.renderPage).toHaveBeenCalledTimes(1));

    expect(pdf.loadDocument).toHaveBeenCalledWith("/api/v1/documents/doc_1/original");
    expect(pdf.getPage).toHaveBeenCalledWith(1);
    expect(screen.getByRole("img", { name: "Source PDF page 1" })).toBeTruthy();
    expect(screen.getByTestId("page-surface").style.width).toBe("600px");
    expect(screen.getByTestId("page-surface").style.height).toBe("800px");

    const firstOverlay = screen.getByRole("button", { name: "Block 1" });
    expect(firstOverlay.style.left).toBe("10%");
    expect(firstOverlay.style.top).toBe("20%");
    expect(firstOverlay.style.width).toBe("30%");
    expect(firstOverlay.style.height).toBe("10%");
    expect(firstOverlay.textContent).toBe("");
  });

  it("zooms the canvas and overlay surface together", async () => {
    const pdf = fakePdf();
    render(<ViewerHarness loadDocument={pdf.loadDocument} />);
    await waitFor(() => expect(pdf.renderPage).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));

    expect(screen.getByLabelText("Zoom level").textContent).toBe("125%");
    await waitFor(() => expect(pdf.getViewport).toHaveBeenCalledWith({ scale: 1.25 }));
    expect(screen.getByTestId("page-surface").style.width).toBe("750px");
    expect(screen.getByRole("button", { name: "Block 1" }).style.left).toBe("10%");
  });

  it("selects segments from the list and their block overlays", async () => {
    const pdf = fakePdf();
    render(<ViewerHarness loadDocument={pdf.loadDocument} />);
    await waitFor(() => expect(pdf.renderPage).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Second source segment." }));
    expect(screen.getByLabelText("Selected segment").textContent).toBe(
      "seg_00000000-0000-4000-8000-000000000002",
    );
    expect(screen.getByRole("button", { name: "Block 2" }).getAttribute("aria-pressed")).toBe(
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "Block 1" }));
    expect(screen.getByLabelText("Selected segment").textContent).toBe(
      "seg_00000000-0000-4000-8000-000000000001",
    );
  });

  it("changes pages with navigation controls", async () => {
    const pdf = fakePdf();
    render(<ViewerHarness loadDocument={pdf.loadDocument} />);
    await waitFor(() => expect(pdf.renderPage).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));

    expect(screen.getByLabelText("Current page").textContent).toBe("2");
    await waitFor(() => expect(pdf.getPage).toHaveBeenCalledWith(2));
    expect(screen.getByText("Page 2 of 3")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(screen.getByLabelText("Current page").textContent).toBe("1");
  });

  it("supports basic keyboard page navigation", async () => {
    const pdf = fakePdf();
    render(<ViewerHarness loadDocument={pdf.loadDocument} />);
    await waitFor(() => expect(pdf.renderPage).toHaveBeenCalledTimes(1));
    const viewer = screen.getByRole("region", { name: "Source page viewer" });

    fireEvent.keyDown(viewer, { key: "ArrowRight" });
    expect(screen.getByLabelText("Current page").textContent).toBe("2");

    fireEvent.keyDown(viewer, { key: "End" });
    expect(screen.getByLabelText("Current page").textContent).toBe("3");

    fireEvent.keyDown(viewer, { key: "Home" });
    expect(screen.getByLabelText("Current page").textContent).toBe("1");
  });
});
