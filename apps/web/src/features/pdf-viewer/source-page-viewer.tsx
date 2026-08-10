"use client";

import { useEffect, useRef, useState } from "react";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2;
const ZOOM_STEP = 0.25;

export interface PagePointGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SourcePageBlock {
  id: string;
  pageReadingOrder: number;
  sourceGeometry: PagePointGeometry;
}

export interface SourcePageSegment {
  id: string;
  blockId: string;
  sourceText: string;
}

interface PdfViewport {
  width: number;
  height: number;
}

interface PdfRenderTask {
  promise: Promise<void>;
  cancel(): void;
}

interface PdfPageHandle {
  getViewport(options: { scale: number }): PdfViewport;
  render(options: {
    canvas: HTMLCanvasElement;
    canvasContext: CanvasRenderingContext2D;
    scale: number;
    transform?: [number, number, number, number, number, number];
  }): PdfRenderTask;
}

export interface PdfDocumentHandle {
  numPages: number;
  getPage(pageNumber: number): Promise<PdfPageHandle>;
  destroy(): Promise<void>;
}

export type PdfDocumentLoader = (url: string) => Promise<PdfDocumentHandle>;

async function loadPdfDocument(url: string): Promise<PdfDocumentHandle> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
  const loadingTask = pdfjs.getDocument({ url });
  const document = await loadingTask.promise;

  return {
    numPages: document.numPages,
    async getPage(pageNumber) {
      const page = await document.getPage(pageNumber);
      return {
        getViewport(options) {
          return page.getViewport(options);
        },
        render(options) {
          const { scale, ...renderOptions } = options;
          return page.render({
            ...renderOptions,
            viewport: page.getViewport({ scale }),
          });
        },
      };
    },
    async destroy() {
      await loadingTask.destroy();
    },
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function percentage(value: number, total: number): string {
  return `${(value / total) * 100}%`;
}

export function SourcePageViewer({
  blocks,
  loadDocument = loadPdfDocument,
  onPageChange,
  onSelectSegment,
  pageHeightPoints,
  pageNumber,
  pageWidthPoints,
  pdfUrl,
  segments,
  selectedSegmentId = null,
}: Readonly<{
  blocks: readonly SourcePageBlock[];
  loadDocument?: PdfDocumentLoader;
  onPageChange(pageNumber: number): void;
  onSelectSegment(segmentId: string): void;
  pageHeightPoints: number;
  pageNumber: number;
  pageWidthPoints: number;
  pdfUrl: string;
  segments: readonly SourcePageSegment[];
  selectedSegmentId?: string | null;
}>) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<PdfDocumentHandle | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [pageCount, setPageCount] = useState(0);
  const [viewport, setViewport] = useState<PdfViewport>({
    width: pageWidthPoints,
    height: pageHeightPoints,
  });
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    let active = true;
    let loadedDocument: PdfDocumentHandle | null = null;
    setDocument(null);
    setDocumentError(null);
    setPageCount(0);

    void loadDocument(pdfUrl)
      .then((nextDocument) => {
        loadedDocument = nextDocument;
        if (!active) {
          return nextDocument.destroy();
        }
        setDocument(nextDocument);
        setPageCount(nextDocument.numPages);
      })
      .catch(() => {
        if (active) {
          setDocumentError("The source PDF could not be loaded.");
        }
      });

    return () => {
      active = false;
      if (loadedDocument !== null) {
        void loadedDocument.destroy();
      }
    };
  }, [loadDocument, pdfUrl]);

  useEffect(() => {
    if (document === null) {
      return;
    }

    let active = true;
    let renderTask: PdfRenderTask | null = null;
    setDocumentError(null);
    setIsRendering(true);

    void document
      .getPage(pageNumber)
      .then((page) => {
        if (!active) {
          return;
        }
        const nextViewport = page.getViewport({ scale: zoom });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (canvas === null || canvas === undefined || context === null || context === undefined) {
          throw new Error("Canvas rendering is unavailable.");
        }

        const outputScale = Math.max(1, window.devicePixelRatio || 1);
        canvas.width = Math.floor(nextViewport.width * outputScale);
        canvas.height = Math.floor(nextViewport.height * outputScale);
        canvas.style.width = `${nextViewport.width}px`;
        canvas.style.height = `${nextViewport.height}px`;
        setViewport(nextViewport);

        renderTask = page.render({
          canvas,
          canvasContext: context,
          scale: zoom,
          ...(outputScale === 1
            ? {}
            : { transform: [outputScale, 0, 0, outputScale, 0, 0] }),
        });
        return renderTask.promise;
      })
      .then(() => {
        if (active) {
          setIsRendering(false);
        }
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof Error && error.name === "RenderingCancelledException")) {
          setIsRendering(false);
          setDocumentError("The source page could not be rendered.");
        }
      });

    return () => {
      active = false;
      renderTask?.cancel();
    };
  }, [document, pageNumber, zoom]);

  const changePage = (nextPage: number) => {
    if (pageCount === 0) {
      return;
    }
    const boundedPage = clamp(nextPage, 1, pageCount);
    if (boundedPage !== pageNumber) {
      onPageChange(boundedPage);
    }
  };

  const handleKeyboard = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      changePage(pageNumber - 1);
    } else if (event.key === "ArrowRight" || event.key === "PageDown") {
      event.preventDefault();
      changePage(pageNumber + 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      changePage(1);
    } else if (event.key === "End") {
      event.preventDefault();
      changePage(pageCount);
    }
  };

  const selectBlock = (blockId: string) => {
    const segment = segments.find((candidate) => candidate.blockId === blockId);
    if (segment !== undefined) {
      onSelectSegment(segment.id);
    }
  };

  return (
    <section
      aria-label="Source page viewer"
      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
      onKeyDown={handleKeyboard}
      tabIndex={0}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <button
            aria-label="Previous page"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium disabled:opacity-40"
            disabled={pageCount === 0 || pageNumber <= 1}
            onClick={() => changePage(pageNumber - 1)}
            type="button"
          >
            Previous
          </button>
          <span aria-live="polite" className="min-w-24 text-center text-sm text-slate-700">
            Page {pageNumber} of {pageCount || "â€“"}
          </span>
          <button
            aria-label="Next page"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium disabled:opacity-40"
            disabled={pageCount === 0 || pageNumber >= pageCount}
            onClick={() => changePage(pageNumber + 1)}
            type="button"
          >
            Next
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            aria-label="Zoom out"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium disabled:opacity-40"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setZoom((value) => clamp(value - ZOOM_STEP, MIN_ZOOM, MAX_ZOOM))}
            type="button"
          >
            âˆ’
          </button>
          <output aria-label="Zoom level" className="min-w-14 text-center text-sm text-slate-700">
            {Math.round(zoom * 100)}%
          </output>
          <button
            aria-label="Zoom in"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium disabled:opacity-40"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setZoom((value) => clamp(value + ZOOM_STEP, MIN_ZOOM, MAX_ZOOM))}
            type="button"
          >
            +
          </button>
        </div>
      </div>

      {documentError === null ? null : (
        <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
          {documentError}
        </p>
      )}

      <div className="mt-4 overflow-auto rounded-xl bg-slate-100 p-4">
        <div
          className="relative mx-auto bg-white shadow"
          data-testid="page-surface"
          style={{ height: viewport.height, width: viewport.width }}
        >
          <canvas aria-label={`Source PDF page ${pageNumber}`} className="block" ref={canvasRef} role="img" />
          <div aria-label="Document block overlays" className="absolute inset-0">
            {blocks.map((block) => {
              const isSelected = segments.some(
                (segment) => segment.blockId === block.id && segment.id === selectedSegmentId,
              );
              return (
                <button
                  aria-label={`Block ${block.pageReadingOrder + 1}`}
                  aria-pressed={isSelected}
                  className={`absolute border-2 transition-colors ${
                    isSelected
                      ? "border-blue-600 bg-blue-400/20"
                      : "border-amber-500 bg-amber-300/10 hover:bg-amber-300/20"
                  }`}
                  data-block-id={block.id}
                  key={block.id}
                  onClick={() => selectBlock(block.id)}
                  style={{
                    height: percentage(block.sourceGeometry.height, pageHeightPoints),
                    left: percentage(block.sourceGeometry.x, pageWidthPoints),
                    top: percentage(block.sourceGeometry.y, pageHeightPoints),
                    width: percentage(block.sourceGeometry.width, pageWidthPoints),
                  }}
                  type="button"
                >
                  {process.env.NODE_ENV === "development" ? (
                    <span className="absolute -left-1 -top-6 rounded bg-slate-950 px-1.5 py-0.5 text-xs text-white">
                      {block.pageReadingOrder + 1}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
          {isRendering ? (
            <p
              className="absolute inset-x-4 top-4 rounded bg-white/90 p-2 text-center text-sm text-slate-700"
              role="status"
            >
              Rendering source pageâ€¦
            </p>
          ) : null}
        </div>
      </div>

      <ul aria-label="Page segments" className="mt-4 list-none p-0">
        {segments.map((segment) => (
          <li key={segment.id}>
            <button
              aria-pressed={segment.id === selectedSegmentId}
              className={`mb-2 block w-full rounded-lg border p-3 text-left text-sm ${
                segment.id === selectedSegmentId
                  ? "border-blue-500 bg-blue-50 text-blue-950"
                  : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
              }`}
              onClick={() => onSelectSegment(segment.id)}
              type="button"
            >
              {segment.sourceText}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
