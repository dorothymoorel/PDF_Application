"use client";

import { useEffect, useState } from "react";

import type {
  ReviewQueueClient,
  ReviewQueueItem,
  ReviewQueueQueryFilters,
} from "./types";

type FilterState = Readonly<{
  confidenceMax: string;
  pageId: string;
  sectionId: string;
  status: string;
  warning: string;
}>;

const INITIAL_FILTERS: FilterState = {
  confidenceMax: "",
  pageId: "",
  sectionId: "",
  status: "",
  warning: "",
};

function toQueryFilters(filters: FilterState): ReviewQueueQueryFilters {
  const query: ReviewQueueQueryFilters = {};
  if (filters.warning !== "") {
    query.warning = filters.warning === "true";
  }
  if (filters.confidenceMax !== "") {
    const confidence = Number(filters.confidenceMax);
    if (Number.isFinite(confidence)) {
      query.confidence_max = confidence;
    }
  }
  if (filters.status !== "") {
    query.status = filters.status;
  }
  if (filters.pageId.trim() !== "") {
    query.page_id = filters.pageId.trim();
  }
  if (filters.sectionId.trim() !== "") {
    query.section_id = filters.sectionId.trim();
  }
  return query;
}

function translationFor(item: ReviewQueueItem): string {
  return (
    item.segment.reviewed_translation ??
    item.segment.final_text ??
    item.segment.machine_translation ??
    "No translation yet."
  );
}

export function ReviewQueue({
  client,
  onSelectSegment,
  projectId,
}: Readonly<{
  client: ReviewQueueClient;
  onSelectSegment(segmentId: string): void;
  projectId: string;
}>) {
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setError(null);

    void client
      .listReviewQueue(projectId, toQueryFilters(filters), { signal: controller.signal })
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
        setItems(result.data.data);
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(cause instanceof Error ? cause.message : "The review queue could not be loaded.");
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
  }, [client, filters, projectId, reloadVersion]);

  const updateFilter = <Key extends keyof FilterState>(key: Key, value: FilterState[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  return (
    <section
      aria-busy={isLoading}
      aria-labelledby="review-queue-heading"
      className="w-full space-y-6"
    >
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Review queue</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="review-queue-heading">
          Segments requiring review
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Filter the queue and open a segment directly in the review editor.
        </p>
      </header>

      <fieldset className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-5">
        <legend className="sr-only">Review queue filters</legend>
        <label className="text-sm font-medium text-slate-800" htmlFor="review-queue-warning">
          Warning
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="review-queue-warning"
            onChange={(event) => updateFilter("warning", event.target.value)}
            value={filters.warning}
          >
            <option value="">All</option>
            <option value="true">Has warning</option>
            <option value="false">No warning</option>
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="review-queue-confidence">
          Confidence max
          <input
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="review-queue-confidence"
            max="1"
            min="0"
            onChange={(event) => updateFilter("confidenceMax", event.target.value)}
            step="0.01"
            type="number"
            value={filters.confidenceMax}
          />
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="review-queue-status">
          Status
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="review-queue-status"
            onChange={(event) => updateFilter("status", event.target.value)}
            value={filters.status}
          >
            <option value="">All</option>
            <option value="NOT_REVIEWED">Not reviewed</option>
            <option value="REVIEW_REQUIRED">Review required</option>
            <option value="IN_REVIEW">In review</option>
            <option value="NEEDS_REVIEW">Needs review</option>
            <option value="TRANSLATION_FAILED">Translation failed</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="review-queue-page">
          Page ID
          <input
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="review-queue-page"
            onChange={(event) => updateFilter("pageId", event.target.value)}
            value={filters.pageId}
          />
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="review-queue-section">
          Section ID
          <input
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="review-queue-section"
            onChange={(event) => updateFilter("sectionId", event.target.value)}
            value={filters.sectionId}
          />
        </label>
      </fieldset>

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading review queue…
        </p>
      ) : error !== null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
          <p className="font-medium text-red-900">Review queue could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={() => setReloadVersion((value) => value + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          No segments require review.
        </p>
      ) : (
        <ol aria-label="Review queue segments" className="space-y-3">
          {items.map((item) => (
            <li key={item.segment.id}>
              <button
                className="block w-full rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-400 hover:bg-blue-50"
                data-segment-id={item.segment.id}
                onClick={() => onSelectSegment(item.segment.id)}
                type="button"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <span className="font-semibold text-slate-950">{item.segment.source_text}</span>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
                    {item.segment.review_status}
                  </span>
                </div>
                <p className="mt-3 text-sm text-slate-700">{translationFor(item)}</p>
                <p className="mt-3 text-xs text-slate-500">
                  {item.warnings.length} warning(s)
                  {item.source_context.heading ? ` · ${item.source_context.heading}` : ""}
                </p>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
