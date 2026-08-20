"use client";

import { useEffect, useMemo, useState } from "react";

import type { OCRReviewClient, OCRReviewPage, OCRReviewSegment } from "./types";

const FOCUS_RING_CLASS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2";
const LOW_CONFIDENCE_THRESHOLD = 0.75;

function confidenceValue(page: OCRReviewPage, segment: OCRReviewSegment | undefined): number | null {
  const segmentConfidence = segment?.confidence.overall ?? null;
  if (segmentConfidence === null) {
    return page.ocr_confidence;
  }
  if (page.ocr_confidence === null) {
    return segmentConfidence;
  }
  return Math.min(segmentConfidence, page.ocr_confidence);
}

function confidenceLabel(value: number | null): string {
  return value === null ? "Not available" : `${Math.round(value * 100)}%`;
}

function rawText(page: OCRReviewPage, segment: OCRReviewSegment | undefined): string {
  return segment?.raw_ocr_text ?? page.raw_text;
}

export function OCRReview({
  client,
  initialSegmentId = null,
  pageId,
  pageImageUrl,
}: Readonly<{
  client: OCRReviewClient;
  initialSegmentId?: string | null;
  pageId: string;
  pageImageUrl: string;
}>) {
  const [view, setView] = useState<OCRReviewPage | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(initialSegmentId);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setError(null);
    setSaveMessage(null);
    setConflictOpen(false);
    setView(null);

    void client
      .getPageOcr(pageId, { signal: controller.signal })
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
        const nextSegment = requestedSegment ?? nextView.segments[0];
        setView(nextView);
        setSelectedSegmentId(nextSegment?.id ?? null);
        setDraft(nextSegment?.resolved_source_text ?? nextView.resolved_source_text);
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(cause instanceof Error ? cause.message : "The OCR page could not be loaded.");
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
  const selectedSegmentIndex =
    view?.segments.findIndex((segment) => segment.id === selectedSegmentId) ?? -1;
  const confidence = useMemo(
    () => (view === null ? null : confidenceValue(view, selectedSegment)),
    [selectedSegment, view],
  );
  const isLowConfidence = confidence !== null && confidence < LOW_CONFIDENCE_THRESHOLD;

  useEffect(() => {
    setDraft(selectedSegment?.resolved_source_text ?? view?.resolved_source_text ?? "");
    setSaveMessage(null);
  }, [selectedSegment?.current_revision, selectedSegment?.id, selectedSegment?.resolved_source_text, view?.resolved_source_text]);

  const moveSelectedSegment = (offset: number) => {
    if (view === null || selectedSegmentIndex < 0) {
      return;
    }
    const nextSegment = view.segments[selectedSegmentIndex + offset];
    if (nextSegment !== undefined) {
      setSelectedSegmentId(nextSegment.id);
    }
  };

  const saveSource = async () => {
    if (selectedSegment === undefined || selectedSegment.is_locked || isSaving) {
      return;
    }
    const resolvedSourceText = draft.trim();
    if (resolvedSourceText === "") {
      setError("Resolved source text cannot be empty.");
      setSaveMessage(null);
      return;
    }

    setIsSaving(true);
    setError(null);
    setSaveMessage(null);
    try {
      const result = await client.resolveSegmentSource(selectedSegment.id, {
        resolved_source_text: resolvedSourceText,
        resolution_source: "MANUAL",
        expected_revision: selectedSegment.current_revision,
      });
      if (!result.ok) {
        setError(result.error.message);
        if (result.error.kind === "api" && result.error.code === "REVISION_CONFLICT") {
          setConflictOpen(true);
        }
        return;
      }

      const updatedSegment = result.data.data;
      setView((current) =>
        current === null
          ? current
          : {
              ...current,
              resolved_source_text: updatedSegment.resolved_source_text,
              segments: current.segments.map((segment) =>
                segment.id === updatedSegment.id ? updatedSegment : segment,
              ),
            },
      );
      setSaveMessage(
        "Source saved. Re-translation may be required because this correction invalidates the existing translation.",
      );
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The source correction could not be saved.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main
      aria-busy={isLoading || isSaving}
      aria-labelledby="ocr-review-heading"
      className="w-full space-y-6 [&_button:focus-visible]:outline-none [&_button:focus-visible]:ring-2 [&_button:focus-visible]:ring-blue-500 [&_button:focus-visible]:ring-offset-2"
    >
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">OCR review</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="ocr-review-heading">
          Correct recognized source text
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Compare the page image with raw OCR, then correct the resolved source before translation.
        </p>
      </header>

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading OCR review…
        </p>
      ) : error !== null && view === null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
          <p className="font-medium text-red-900">OCR review could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
          <button
            className={`mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100 ${FOCUS_RING_CLASS}`}
            onClick={() => setReloadVersion((value) => value + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : view === null ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          No OCR page is available.
        </p>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
          <section
            aria-labelledby="ocr-page-image-heading"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <h2 className="text-lg font-semibold text-slate-950" id="ocr-page-image-heading">
              Page image
            </h2>
            <figure className="mt-4 overflow-auto rounded-xl border border-slate-200 bg-slate-100 p-3">
              <img
                alt="OCR source page"
                className="mx-auto max-h-[70vh] w-auto max-w-full object-contain shadow-sm"
                src={pageImageUrl}
              />
              <figcaption className="mt-3 text-center text-xs text-slate-500">
                Use the image to verify characters, spacing, and line breaks.
              </figcaption>
            </figure>
          </section>

          <div className="space-y-6">
            <section
              aria-labelledby="ocr-source-heading"
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-950" id="ocr-source-heading">
                    Source text
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    {selectedSegment === undefined
                      ? "Page OCR"
                      : `Segment ${selectedSegmentIndex + 1} of ${view.segments.length} · Revision ${selectedSegment.current_revision}`}
                  </p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800">
                  Confidence: {confidenceLabel(confidence)}
                </span>
              </div>

              {isLowConfidence ? (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950" role="alert">
                  <p className="font-semibold">Low OCR confidence</p>
                  <p className="mt-1">
                    Verify this text against the page image before saving a correction.
                  </p>
                </div>
              ) : null}

              <label className="mt-5 block text-sm font-medium text-slate-800" htmlFor="ocr-raw-text">
                Raw OCR
              </label>
              <textarea
                aria-describedby="ocr-raw-help"
                className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-800"
                id="ocr-raw-text"
                readOnly
                value={rawText(view, selectedSegment)}
              />
              <p className="mt-1 text-xs text-slate-500" id="ocr-raw-help">
                Raw OCR is preserved for audit and cannot be edited here.
              </p>

              <label className="mt-5 block text-sm font-medium text-slate-800" htmlFor="ocr-resolved-source">
                Resolved source
              </label>
              <textarea
                className="mt-2 min-h-36 w-full resize-y rounded-xl border border-slate-300 px-3 py-3 text-sm leading-6 text-slate-950 outline-none focus:border-blue-700 focus:ring-2 focus:ring-blue-100"
                disabled={selectedSegment === undefined || selectedSegment.is_locked || isSaving}
                id="ocr-resolved-source"
                onChange={(event) => setDraft(event.target.value)}
                readOnly={selectedSegment?.is_locked ?? false}
                value={draft}
              />

              <nav aria-label="OCR segment navigation" className="mt-4 flex flex-wrap items-center gap-2 border-y border-slate-200 py-3">
                <button
                  aria-label="Previous segment"
                  className={`rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING_CLASS}`}
                  disabled={selectedSegmentIndex <= 0}
                  onClick={() => moveSelectedSegment(-1)}
                  type="button"
                >
                  Previous segment
                </button>
                <button
                  aria-label="Next segment"
                  className={`rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING_CLASS}`}
                  disabled={selectedSegmentIndex < 0 || selectedSegmentIndex >= view.segments.length - 1}
                  onClick={() => moveSelectedSegment(1)}
                  type="button"
                >
                  Next segment
                </button>
              </nav>

              <button
                className={`mt-4 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING_CLASS}`}
                disabled={selectedSegment === undefined || selectedSegment.is_locked || isSaving}
                onClick={() => void saveSource()}
                type="button"
              >
                {isSaving ? "Saving…" : "Save source correction"}
              </button>
              {selectedSegment?.is_locked ? (
                <p className="mt-3 text-sm text-amber-800">This segment is locked and cannot be edited.</p>
              ) : null}
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
              aria-labelledby="ocr-warning-heading"
              className="rounded-2xl border border-amber-200 bg-amber-50 p-5"
            >
              <h2 className="text-lg font-semibold text-amber-950" id="ocr-warning-heading">
                Before you save
              </h2>
              <p className="mt-2 text-sm leading-6 text-amber-950">
                Saving a source correction preserves the raw OCR, but the current translation may be
                cleared and re-translation may be required.
              </p>
            </section>
          </div>
        </div>
      )}

      {conflictOpen ? (
        <div
          aria-labelledby="ocr-conflict-heading"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4"
          role="alertdialog"
        >
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-slate-950" id="ocr-conflict-heading">
              OCR source conflict
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-700">
              This segment changed after you opened it. Reload the latest OCR revision before saving
              again.
            </p>
            <button
              className={`mt-4 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 ${FOCUS_RING_CLASS}`}
              onClick={() => {
                setConflictOpen(false);
                setReloadVersion((value) => value + 1);
              }}
              type="button"
            >
              Reload OCR page
            </button>
          </div>
        </div>
      ) : null}
    </main>
  );
}

export const OcrReview = OCRReview;
