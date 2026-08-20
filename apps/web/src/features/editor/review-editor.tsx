"use client";

import { useEffect, useState } from "react";

import {
  SourcePageViewer,
  type PdfDocumentLoader,
  type SourcePageBlock,
  type SourcePageSegment,
} from "../pdf-viewer/source-page-viewer";
import type {
  ReviewEditorClient,
  ReviewEditorContext,
  ReviewGlossaryItem,
  ReviewPageData,
  ReviewSegment,
} from "./types";

function initialTranslation(segment: ReviewSegment | undefined): string {
  return (
    segment?.reviewed_translation ?? segment?.final_text ?? segment?.machine_translation ?? ""
  );
}

function pageBlocks(page: ReviewPageData): readonly SourcePageBlock[] {
  return page.blocks.map((block) => ({
    id: block.id,
    pageReadingOrder: block.page_reading_order,
    sourceGeometry: block.source_geometry,
  }));
}

function pageSegments(page: ReviewPageData): readonly SourcePageSegment[] {
  return page.segments.map((segment) => ({
    id: segment.id,
    blockId: segment.block_id,
    sourceText: segment.source_text,
  }));
}

function contextValue(value: string | null | undefined): string {
  return value?.trim() || "Not available";
}

export function ReviewEditor({
  client,
  context = {},
  glossary = [],
  initialSegmentId = null,
  loadDocument,
  pageId,
  pdfUrl,
}: Readonly<{
  client: ReviewEditorClient;
  context?: ReviewEditorContext;
  glossary?: readonly ReviewGlossaryItem[];
  initialSegmentId?: string | null;
  loadDocument?: PdfDocumentLoader;
  pageId: string;
  pdfUrl: string;
}>) {
  const [view, setView] = useState<ReviewPageData | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(initialSegmentId);
  const [pageNumber, setPageNumber] = useState(1);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setError(null);
    setSaveMessage(null);
    setView(null);

    void client
      .getPageEditorView(pageId, { signal: controller.signal })
      .then((result) => {
        if (!active) {
          return;
        }
        if (!result.ok) {
          if (result.error.kind !== "aborted") {
            setError(result.error.message);
          }
          return;
        }
        const nextView = result.data.data;
        const requestedSegment = nextView.segments.find(
          (segment) => segment.id === initialSegmentId,
        );
        setView(nextView);
        setPageNumber(nextView.page.source_page_number);
        setSelectedSegmentId(requestedSegment?.id ?? nextView.segments[0]?.id ?? null);
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(cause instanceof Error ? cause.message : "The review page could not be loaded.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [client, initialSegmentId, pageId, reloadVersion]);

  const selectedSegment = view?.segments.find((segment) => segment.id === selectedSegmentId);

  useEffect(() => {
    setDraft(initialTranslation(selectedSegment));
    setSaveMessage(null);
  }, [
    selectedSegment?.current_revision,
    selectedSegment?.final_text,
    selectedSegment?.id,
    selectedSegment?.machine_translation,
    selectedSegment?.reviewed_translation,
  ]);

  const saveTranslation = async () => {
    if (selectedSegment === undefined || selectedSegment.is_locked || isSaving) {
      return;
    }
    const reviewedTranslation = draft.trim();
    if (reviewedTranslation === "") {
      setError("Translation cannot be empty.");
      setSaveMessage(null);
      return;
    }

    setIsSaving(true);
    setError(null);
    setSaveMessage(null);
    try {
      const result = await client.editSegmentTranslation(selectedSegment.id, {
        reviewed_translation: reviewedTranslation,
        expected_revision: selectedSegment.current_revision,
      });
      if (!result.ok) {
        setError(result.error.message);
        return;
      }
      const updatedSegment = result.data.data;
      setView((current) =>
        current === null
          ? current
          : {
              ...current,
              segments: current.segments.map((segment) =>
                segment.id === updatedSegment.id ? updatedSegment : segment,
              ),
            },
      );
      setSaveMessage("Translation saved.");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The translation could not be saved.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main
      aria-busy={isLoading || isSaving}
      aria-labelledby="review-editor-heading"
      className="w-full space-y-6"
    >
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Review editor</p>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-slate-950" id="review-editor-heading">
            Side-by-side review
          </h1>
          {selectedSegment?.is_locked ? (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
              Locked
            </span>
          ) : null}
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Review the source page, translation, context, glossary, and warnings without leaving the page.
        </p>
      </header>

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading review editor…
        </p>
      ) : error !== null && view === null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
          <p className="font-medium text-red-900">Review editor could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={() => setReloadVersion((value) => value + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : view === null ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          No review page is available.
        </p>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)]">
          <div className="space-y-6">
            <SourcePageViewer
              blocks={pageBlocks(view)}
              {...(loadDocument === undefined ? {} : { loadDocument })}
              onPageChange={setPageNumber}
              onSelectSegment={setSelectedSegmentId}
              pageHeightPoints={view.page.height_points}
              pageNumber={pageNumber}
              pageWidthPoints={view.page.width_points}
              pdfUrl={pdfUrl}
              segments={pageSegments(view)}
              selectedSegmentId={selectedSegmentId}
            />

            <section
              aria-labelledby="review-context-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h2 className="text-lg font-semibold text-slate-950" id="review-context-heading">
                Context
              </h2>
              <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-slate-500">Heading</dt>
                  <dd className="mt-1 text-slate-800">{contextValue(context.heading)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Section summary</dt>
                  <dd className="mt-1 text-slate-800">{contextValue(context.sectionSummary)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Previous segment</dt>
                  <dd className="mt-1 text-slate-800">{contextValue(context.previousSegment)}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-500">Next segment</dt>
                  <dd className="mt-1 text-slate-800">{contextValue(context.nextSegment)}</dd>
                </div>
              </dl>
            </section>
          </div>

          <div className="space-y-6">
            <section
              aria-labelledby="source-segment-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h2 className="text-lg font-semibold text-slate-950" id="source-segment-heading">
                Source segment
              </h2>
              {selectedSegment === undefined ? (
                <p className="mt-3 text-sm text-slate-600">Select a segment from the source page.</p>
              ) : (
                <p className="mt-3 rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-800">
                  {selectedSegment.source_text}
                </p>
              )}
            </section>

            <section
              aria-labelledby="translation-editor-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-950" id="translation-editor-heading">
                    Translation editor
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    {selectedSegment === undefined
                      ? "Select a segment to edit its translation."
                      : `Revision ${selectedSegment.current_revision} · ${selectedSegment.review_status}`}
                  </p>
                </div>
                {selectedSegment?.is_locked ? (
                  <span className="text-sm font-medium text-amber-800">Editing is disabled.</span>
                ) : null}
              </div>
              <label className="mt-4 block text-sm font-medium text-slate-800" htmlFor="translation-editor">
                Reviewed translation
              </label>
              <textarea
                className="mt-2 min-h-36 w-full resize-y rounded-xl border border-slate-300 px-3 py-3 text-sm leading-6 text-slate-950 outline-none focus:border-blue-700 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100"
                disabled={selectedSegment === undefined || selectedSegment.is_locked || isSaving}
                id="translation-editor"
                onChange={(event) => setDraft(event.target.value)}
                readOnly={selectedSegment?.is_locked ?? false}
                value={draft}
              />
              <button
                className="mt-4 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={selectedSegment === undefined || selectedSegment.is_locked || isSaving}
                onClick={() => void saveTranslation()}
                type="button"
              >
                {isSaving ? "Saving…" : "Save translation"}
              </button>
              {saveMessage !== null ? (
                <p className="mt-3 text-sm text-emerald-700" role="status">
                  {saveMessage}
                </p>
              ) : null}
              {error !== null && view !== null ? (
                <p className="mt-3 text-sm text-red-700" role="alert">
                  {error}
                </p>
              ) : null}
            </section>

            <section
              aria-labelledby="review-glossary-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h2 className="text-lg font-semibold text-slate-950" id="review-glossary-heading">
                Glossary
              </h2>
              {glossary.length === 0 ? (
                <p className="mt-3 text-sm text-slate-600">No glossary terms for this segment.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {glossary.map((item) => (
                    <li className="rounded-lg bg-slate-50 p-3" key={item.id}>
                      <span className="font-medium text-slate-900">{item.sourceTerm}</span>
                      <span className="mx-2 text-slate-400">→</span>
                      <span className="text-slate-700">{item.targetTerm ?? "Keep original"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              aria-labelledby="review-warnings-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h2 className="text-lg font-semibold text-slate-950" id="review-warnings-heading">
                Warnings
              </h2>
              {view.warnings.length === 0 ? (
                <p className="mt-3 text-sm text-slate-600">No warnings for this page.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {view.warnings.map((warning) => (
                    <li className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950" key={warning.id}>
                      <p className="font-medium">{warning.warning_type}</p>
                      <p className="mt-1">{warning.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}
    </main>
  );
}
