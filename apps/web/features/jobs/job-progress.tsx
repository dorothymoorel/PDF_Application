"use client";

import { createTransLokaClient, type JobResource } from "@transloka/api-client";
import { useEffect, useRef, useState } from "react";

const DEFAULT_POLL_SECONDS = 2;
const TERMINAL_STATUSES = new Set<JobResource["status"]>([
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);
const CANCELLABLE_STATUSES = new Set<JobResource["status"]>(["QUEUED", "RUNNING"]);
const RETRYABLE_STATUSES = new Set<JobResource["status"]>([
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);

type JobClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "cancelJob" | "getJob" | "retryJob"
>;

const defaultClient = createTransLokaClient();

function statusLabel(status: JobResource["status"]): string {
  return status
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function stageLabel(stage: string | null, status: JobResource["status"]): string {
  if (stage === null) {
    return status === "QUEUED" || status === "CREATED"
      ? "Waiting for a worker"
      : "No active stage";
  }
  return stage
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function isTerminal(status: JobResource["status"]): boolean {
  return TERMINAL_STATUSES.has(status);
}

function retryFailedItemsOnly(status: JobResource["status"]): boolean {
  return ["COMPLETED_WITH_WARNINGS", "PARTIALLY_COMPLETED", "FAILED"].includes(status);
}

function retryKey(jobId: string): string {
  return `job-ui-retry-${jobId}-${Date.now().toString(36)}`;
}

export function JobProgress({
  client = defaultClient,
  jobId,
}: Readonly<{
  client?: JobClient;
  jobId: string;
}>) {
  const [job, setJob] = useState<JobResource | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<"cancel" | "retry" | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const mounted = useRef(false);
  const mutationController = useRef<AbortController | null>(null);
  const pendingRetryKey = useRef<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      mutationController.current?.abort();
    };
  }, []);

  useEffect(() => {
    setJob(null);
    setLoadError(null);
    setActionError(null);
    pendingRetryKey.current = null;
  }, [jobId]);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let requestController: AbortController | undefined;

    const poll = async () => {
      requestController = new AbortController();
      const result = await client.getJob(jobId, { signal: requestController.signal });
      if (disposed) {
        return;
      }
      if (!result.ok) {
        if (result.error.kind !== "aborted") {
          setLoadError(result.error.message);
        }
        return;
      }

      const nextJob = result.data.data;
      setJob(nextJob);
      setLoadError(null);
      if (!isTerminal(nextJob.status)) {
        const pollSeconds = Math.max(
          1,
          result.retryAfterSeconds ?? DEFAULT_POLL_SECONDS,
        );
        timer = setTimeout(() => void poll(), pollSeconds * 1_000);
      }
    };

    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) {
        clearTimeout(timer);
      }
      requestController?.abort();
    };
  }, [client, jobId, refreshVersion]);

  const cancel = async () => {
    if (job === null || pendingAction !== null) {
      return;
    }
    const controller = new AbortController();
    mutationController.current = controller;
    setPendingAction("cancel");
    setActionError(null);
    const result = await client.cancelJob(
      job.id,
      { reason: "Cancelled by user." },
      { signal: controller.signal },
    );
    if (!mounted.current) {
      return;
    }
    mutationController.current = null;
    setPendingAction(null);
    if (!result.ok) {
      if (result.error.kind !== "aborted") {
        setActionError(result.error.message);
      }
      return;
    }
    setJob(result.data.data);
    setRefreshVersion((value) => value + 1);
  };

  const retry = async () => {
    if (job === null || pendingAction !== null) {
      return;
    }
    const controller = new AbortController();
    mutationController.current = controller;
    pendingRetryKey.current ??= retryKey(job.id);
    setPendingAction("retry");
    setActionError(null);
    const result = await client.retryJob(
      job.id,
      pendingRetryKey.current,
      { retry_failed_items_only: retryFailedItemsOnly(job.status) },
      { signal: controller.signal },
    );
    if (!mounted.current) {
      return;
    }
    mutationController.current = null;
    setPendingAction(null);
    if (!result.ok) {
      if (result.error.kind !== "aborted") {
        setActionError(result.error.message);
      }
      return;
    }
    pendingRetryKey.current = null;
    setJob(result.data.data);
    setRefreshVersion((value) => value + 1);
  };

  if (job === null) {
    return (
      <section
        aria-busy={loadError === null}
        aria-labelledby="job-progress-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 className="text-xl font-semibold text-slate-950" id="job-progress-heading">
          Job progress
        </h2>
        {loadError === null ? (
          <p className="mt-3 text-sm text-slate-600" role="status">
            Loading job status…
          </p>
        ) : (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4" role="alert">
            <p className="font-medium text-red-900">Job status could not be loaded.</p>
            <p className="mt-1 text-sm text-red-800">{loadError}</p>
            <button
              className="mt-3 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
              onClick={() => setRefreshVersion((value) => value + 1)}
              type="button"
            >
              Retry status check
            </button>
          </div>
        )}
      </section>
    );
  }

  const progress = Math.round(job.progress * 100);
  const canCancel = CANCELLABLE_STATUSES.has(job.status);
  const canRetry =
    RETRYABLE_STATUSES.has(job.status) && job.retry_count < job.max_retries;

  return (
    <section
      aria-labelledby="job-progress-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-950" id="job-progress-heading">
            Job progress
          </h2>
          <p className="mt-1 text-sm text-slate-500">{job.job_type.replaceAll("_", " ")}</p>
        </div>
        <span
          aria-live="polite"
          className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800"
          role="status"
        >
          {statusLabel(job.status)}
        </span>
      </div>

      <div className="mt-6">
        <div className="flex justify-between gap-4 text-sm font-medium text-slate-700">
          <span>{stageLabel(job.current_stage, job.status)}</span>
          <span>{progress}%</span>
        </div>
        <progress
          aria-label="Job progress"
          className="mt-2 h-3 w-full accent-slate-900"
          max={100}
          value={progress}
        >
          {progress}%
        </progress>
      </div>

      {job.error !== null ? (
        <div
          aria-label="Failure details"
          className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4"
          role="alert"
        >
          <p className="font-semibold text-red-900">Job could not complete</p>
          <p className="mt-1 font-mono text-xs text-red-700">{job.error.code}</p>
          <p className="mt-2 text-sm leading-6 text-red-800">{job.error.message}</p>
        </div>
      ) : null}

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
        {canCancel ? (
          <button
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void cancel()}
            type="button"
          >
            {pendingAction === "cancel" ? "Cancelling…" : "Cancel job"}
          </button>
        ) : null}
        {job.status === "CANCELLATION_REQUESTED" ? (
          <p className="text-sm text-slate-600" role="status">
            Cancellation requested. Waiting for a safe checkpoint.
          </p>
        ) : null}
        {canRetry ? (
          <button
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={pendingAction !== null}
            onClick={() => void retry()}
            type="button"
          >
            {pendingAction === "retry" ? "Retrying…" : "Retry job"}
          </button>
        ) : null}
        {RETRYABLE_STATUSES.has(job.status) && !canRetry ? (
          <p className="text-sm text-slate-600">Retry limit reached.</p>
        ) : null}
      </div>

      {actionError !== null ? (
        <p className="mt-4 text-sm text-red-700" role="alert">
          {actionError}
        </p>
      ) : null}
    </section>
  );
}
