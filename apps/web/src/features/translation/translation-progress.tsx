"use client";

import { createTransLokaClient } from "@transloka/api-client";
import { useEffect, useRef, useState } from "react";

import {
  isTerminalTranslationStatus,
  statusLabel,
  type TranslationStatus,
  type TranslationUiClient,
} from "./types";

const defaultClient = createTransLokaClient();
const RETRYABLE_STATUSES = new Set([
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);

function retryKey(projectId: string): string {
  return `translation-ui-retry-${projectId}-${Date.now().toString(36)}`;
}

function boundedProgress(value: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
}

export function TranslationProgress({
  client = defaultClient,
  pollIntervalMs = 2_000,
  projectId,
  refreshToken = 0,
}: Readonly<{
  client?: TranslationUiClient;
  pollIntervalMs?: number;
  projectId: string;
  refreshToken?: number;
}>) {
  const [status, setStatus] = useState<TranslationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<"cancel" | "retry" | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const poll = async () => {
      const result = await client.getTranslationStatus(projectId, { signal: controller.signal });
      if (disposed || !mounted.current) {
        return;
      }
      if (!result.ok) {
        if (result.error.kind !== "aborted") {
          setError(result.error.message);
        }
        return;
      }
      const nextStatus = result.data.data;
      setStatus(nextStatus);
      setError(null);
      if (!isTerminalTranslationStatus(nextStatus.status)) {
        timer = setTimeout(() => void poll(), Math.max(250, pollIntervalMs));
      }
    };

    setStatus(null);
    setError(null);
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      controller.abort();
    };
  }, [client, pollIntervalMs, projectId, refreshToken, refreshVersion]);

  const cancel = async () => {
    if (status === null || pendingAction !== null || isTerminalTranslationStatus(status.status)) {
      return;
    }
    setPendingAction("cancel");
    setError(null);
    const result = await client.cancelTranslation(projectId, { reason: "Cancelled by user." });
    if (!mounted.current) {
      return;
    }
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStatus(result.data.data);
    setRefreshVersion((value) => value + 1);
  };

  const retry = async () => {
    if (status === null || pendingAction !== null || !RETRYABLE_STATUSES.has(status.status)) {
      return;
    }
    setPendingAction("retry");
    setError(null);
    const result = await client.retryFailedTranslation(
      projectId,
      retryKey(projectId),
      { use_smaller_batch: true, use_selected_model: true },
    );
    if (!mounted.current) {
      return;
    }
    setPendingAction(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStatus(result.data.data);
    setRefreshVersion((value) => value + 1);
  };

  return (
    <section
      aria-busy={status === null && error === null}
      aria-labelledby="translation-progress-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Translation job</p>
          <h2 className="mt-1 text-xl font-semibold text-slate-950" id="translation-progress-heading">
            Translation progress
          </h2>
        </div>
        {status !== null ? (
          <span aria-live="polite" className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800" role="status">
            {statusLabel(status.status)}
          </span>
        ) : null}
      </div>

      {status === null ? (
        error === null ? (
          <p className="mt-5 text-sm text-slate-600" role="status">Loading translation status…</p>
        ) : (
          <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4" role="alert">
            <p className="font-medium text-red-900">Translation status could not be loaded.</p>
            <p className="mt-1 text-sm text-red-800">{error}</p>
            <button
              className="mt-3 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
              onClick={() => setRefreshVersion((value) => value + 1)}
              type="button"
            >
              Retry status check
            </button>
          </div>
        )
      ) : (
        <>
          <div className="mt-6">
            <div className="flex justify-between gap-4 text-sm font-medium text-slate-700">
              <span>
                {status.completed_segments} of {status.total_segments} segments
              </span>
              <span>{Math.round(boundedProgress(status.progress) * 100)}%</span>
            </div>
            <progress
              aria-label="Translation progress"
              className="mt-2 h-3 w-full accent-slate-900"
              max={100}
              value={Math.round(boundedProgress(status.progress) * 100)}
            />
            <p className="mt-2 text-sm text-slate-600">
              Batch {status.current_batch} of {status.total_batches} · {status.failed_segments} failed · {status.review_required_segments} need review
            </p>
          </div>

          {status.failed_segments > 0 && RETRYABLE_STATUSES.has(status.status) ? (
            <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
              {status.failed_segments} segment(s) failed and can be retried with a smaller batch.
            </p>
          ) : null}

          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
            {!isTerminalTranslationStatus(status.status) ? (
              <button
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={pendingAction !== null}
                onClick={() => void cancel()}
                type="button"
              >
                {pendingAction === "cancel" ? "Cancelling…" : "Cancel translation"}
              </button>
            ) : null}
            {RETRYABLE_STATUSES.has(status.status) ? (
              <button
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={pendingAction !== null}
                onClick={() => void retry()}
                type="button"
              >
                {pendingAction === "retry" ? "Retrying…" : "Retry failed segments"}
              </button>
            ) : null}
          </div>
        </>
      )}

      {error !== null && status !== null ? (
        <p className="mt-4 text-sm text-red-700" role="alert">{error}</p>
      ) : null}
    </section>
  );
}
