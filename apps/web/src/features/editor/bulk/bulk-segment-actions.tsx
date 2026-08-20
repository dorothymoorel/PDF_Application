"use client";

import { useMemo, useState } from "react";

import type {
  BulkSegment,
  BulkSegmentAction,
  BulkSegmentActionClient,
  BulkSegmentActionInput,
  BulkSegmentActionResult,
} from "./types";

const ACTIONS: readonly { value: BulkSegmentAction; label: string }[] = [
  { value: "approve", label: "Approve selected" },
  { value: "lock", label: "Lock selected" },
  { value: "retranslate", label: "Retranslate selected" },
];
const FOCUS_RING_CLASS =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2";

function nextSelection(
  selected: ReadonlySet<string>,
  segmentId: string,
  checked: boolean,
): Set<string> {
  const result = new Set(selected);
  if (checked) {
    result.add(segmentId);
  } else {
    result.delete(segmentId);
  }
  return result;
}

export function BulkSegmentActions({
  client,
  onCompleted,
  segments,
}: Readonly<{
  client: BulkSegmentActionClient;
  onCompleted?: (result: BulkSegmentActionResult[]) => void;
  segments: readonly BulkSegment[];
}>) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [action, setAction] = useState<BulkSegmentAction>("approve");
  const [results, setResults] = useState<readonly BulkSegmentActionResult[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const segmentById = useMemo(
    () => new Map(segments.map((segment) => [segment.id, segment])),
    [segments],
  );
  const selectedIds = useMemo(
    () => segments.filter((segment) => selected.has(segment.id)).map((segment) => segment.id),
    [segments, selected],
  );
  const failedIds = useMemo(
    () => results.filter((result) => result.status === "FAILED").map((result) => result.segment_id),
    [results],
  );

  const submit = async (ids: readonly string[] = selectedIds) => {
    if (ids.length === 0 || isSubmitting) {
      return;
    }
    const expectedRevisions = Object.fromEntries(
      ids.flatMap((id) => {
        const segment = segmentById.get(id);
        return segment === undefined ? [] : [[id, segment.current_revision]];
      }),
    );
    const input: BulkSegmentActionInput = {
      action,
      selected_ids: [...ids],
      expected_revisions: expectedRevisions,
    };
    setIsSubmitting(true);
    setError(null);
    setJobId(null);
    try {
      const result = await client.bulkSegmentAction(input, {
        idempotencyKey: `editor-bulk-${action}-${Date.now()}`,
      });
      if (!result.ok) {
        setError(result.error.message);
        return;
      }
      setResults(result.data.data.results);
      setJobId(result.data.data.job_id);
      onCompleted?.(result.data.data.results);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "The bulk action failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleAll = (checked: boolean) => {
    setSelected(checked ? new Set(segments.map((segment) => segment.id)) : new Set());
  };

  return (
    <section
      aria-busy={isSubmitting}
      aria-labelledby="bulk-segment-actions-heading"
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950" id="bulk-segment-actions-heading">
            Bulk segment actions
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Select segments, then apply one approved review action at a time.
          </p>
        </div>
        <span className="text-sm font-medium text-slate-600">{selectedIds.length} selected</span>
      </div>

      {segments.length === 0 ? (
        <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600" role="status">
          No segments are available.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="w-12 px-2 py-3">
                  <label className="sr-only" htmlFor="select-all-segments">
                    Select all segments
                  </label>
                  <input
                    checked={selectedIds.length === segments.length}
                    className={FOCUS_RING_CLASS}
                    id="select-all-segments"
                    onChange={(event) => toggleAll(event.target.checked)}
                    type="checkbox"
                  />
                </th>
                <th className="px-2 py-3">Segment</th>
                <th className="px-2 py-3">State</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((segment) => (
                <tr className="border-b border-slate-100 last:border-0" key={segment.id}>
                  <td className="px-2 py-3">
                    <label className="sr-only" htmlFor={`select-segment-${segment.id}`}>
                      Select {segment.source_text ?? segment.id}
                    </label>
                    <input
                      checked={selected.has(segment.id)}
                      className={FOCUS_RING_CLASS}
                      id={`select-segment-${segment.id}`}
                      onChange={(event) =>
                        setSelected((current) =>
                          nextSelection(current, segment.id, event.target.checked),
                        )
                      }
                      type="checkbox"
                    />
                  </td>
                  <td className="px-2 py-3 text-slate-800">
                    {segment.source_text ?? segment.id}
                  </td>
                  <td className="px-2 py-3 text-slate-600">
                    {segment.is_locked ? "Locked" : "Editable"} · revision {segment.current_revision}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="text-sm font-medium text-slate-800" htmlFor="bulk-segment-action">
          Action
          <select
            className={`mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-950 ${FOCUS_RING_CLASS}`}
            id="bulk-segment-action"
            onChange={(event) => setAction(event.target.value as BulkSegmentAction)}
            value={action}
          >
            {ACTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className={`rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING_CLASS}`}
          disabled={selectedIds.length === 0 || isSubmitting}
          onClick={() => void submit()}
          type="button"
        >
          {isSubmitting ? "Applying…" : "Apply action"}
        </button>
        {failedIds.length > 0 ? (
          <button
            className={`rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING_CLASS}`}
            disabled={isSubmitting}
            onClick={() => void submit(failedIds)}
            type="button"
          >
            Retry failed ({failedIds.length})
          </button>
        ) : null}
      </div>

      {jobId !== null ? (
        <p className="mt-3 text-sm text-blue-800" role="status">
          Retranslation queued as {jobId}.
        </p>
      ) : null}
      {results.length > 0 ? (
        <div className="mt-4 space-y-2" role="status">
          <p className="text-sm font-medium text-slate-800">
            {results.filter((result) => result.status === "SUCCEEDED").length} succeeded · {failedIds.length}{" "}
            failed · {results.filter((result) => result.status === "QUEUED").length} queued
          </p>
          {results
            .filter((result) => result.status === "FAILED")
            .map((result) => (
              <p className="rounded-lg bg-red-50 p-3 text-sm text-red-900" key={result.segment_id}>
                {result.segment_id}: {result.error?.message ?? "Action failed."}
              </p>
            ))}
        </div>
      ) : null}
      {error !== null ? (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
