// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  createTransLokaClient,
  type CancelJobInput,
  type JobResource,
  type RequestOptions,
  type RetryJobInput,
} from "@transloka/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JobProgress } from "./job-progress";

type JobClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "cancelJob" | "getJob" | "retryJob"
>;

const baseJob = {
  id: "job_00000000-0000-4000-8000-000000000001",
  job_type: "MAINTENANCE",
  status: "QUEUED",
  progress: 0,
  current_stage: null,
  project_id: null,
  document_id: null,
  retry_count: 0,
  max_retries: 3,
  created_at: "2026-08-08T10:00:00.000Z",
  started_at: null,
  completed_at: null,
  error: null,
} satisfies JobResource;

function jobResult(job: JobResource, retryAfterSeconds?: number) {
  return {
    ok: true as const,
    data: { data: job, meta: { request_id: "job-status" } },
    status: 200,
    requestId: "job-status",
    ...(retryAfterSeconds === undefined ? {} : { retryAfterSeconds }),
  };
}

function clientWith(job: JobResource, retryAfterSeconds?: number) {
  return {
    cancelJob: vi.fn(
      (_jobId: string, _input: CancelJobInput, options?: RequestOptions) => {
        void options;
        return Promise.resolve(
          jobResult({ ...job, status: "CANCELLATION_REQUESTED" }, retryAfterSeconds),
        );
      },
    ),
    getJob: vi.fn((_jobId: string, options?: RequestOptions) => {
      void options;
      return Promise.resolve(jobResult(job, retryAfterSeconds));
    }),
    retryJob: vi.fn(
      (
        _jobId: string,
        _retryKey: string,
        _input: RetryJobInput,
        options?: RequestOptions,
      ) => {
        void options;
        return Promise.resolve(
          jobResult({ ...job, status: "RETRYING", retry_count: job.retry_count + 1 }),
        );
      },
    ),
  } satisfies JobClient;
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
  });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("job progress", () => {
  it("renders queued state and allows cancellation", async () => {
    const client = clientWith(baseJob, 5);
    render(<JobProgress client={client} jobId={baseJob.id} />);
    await settle();

    expect(screen.getByText("Queued")).toBeTruthy();
    expect(screen.getByText("Waiting for a worker")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    await settle();

    const call = client.cancelJob.mock.calls[0];
    expect(call?.[0]).toBe(baseJob.id);
    expect(call?.[1]).toEqual({ reason: "Cancelled by user." });
    expect(call?.[2]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("renders running progress and obeys Retry-After polling", async () => {
    vi.useFakeTimers();
    const running = {
      ...baseJob,
      status: "RUNNING",
      progress: 0.42,
      current_stage: "EXTRACT_TEXT",
      started_at: "2026-08-08T10:01:00.000Z",
    } satisfies JobResource;
    const client = clientWith(running, 3);
    render(<JobProgress client={client} jobId={running.id} />);
    await settle();

    expect(screen.getByText("Extract Text")).toBeTruthy();
    expect(screen.getAllByText("42%")).toHaveLength(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_999);
    });
    expect(client.getJob).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(client.getJob).toHaveBeenCalledTimes(2);
  });

  it("stops polling after completed status", async () => {
    vi.useFakeTimers();
    const completed = {
      ...baseJob,
      status: "COMPLETED",
      progress: 1,
      current_stage: "COMPLETED",
      completed_at: "2026-08-08T10:05:00.000Z",
    } satisfies JobResource;
    const client = clientWith(completed, 2);
    render(<JobProgress client={client} jobId={completed.id} />);
    await settle();

    expect(screen.getByRole("status").textContent).toBe("Completed");
    expect(screen.queryByRole("button", { name: "Cancel job" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry job" })).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(client.getJob).toHaveBeenCalledTimes(1);
  });

  it("shows failed details and retries failed items", async () => {
    const failed = {
      ...baseJob,
      status: "FAILED",
      progress: 0.6,
      current_stage: "TRANSLATE",
      completed_at: "2026-08-08T10:05:00.000Z",
      error: { code: "MODEL_TIMEOUT", message: "The local model timed out." },
    } satisfies JobResource;
    const client = clientWith(failed);
    render(<JobProgress client={client} jobId={failed.id} />);
    await settle();

    const failure = screen.getByRole("alert", { name: "Failure details" });
    expect(failure.textContent).toContain("MODEL_TIMEOUT");
    expect(failure.textContent).toContain("The local model timed out.");
    fireEvent.click(screen.getByRole("button", { name: "Retry job" }));
    await settle();

    const call = client.retryJob.mock.calls[0];
    expect(call?.[0]).toBe(failed.id);
    expect(call?.[1]?.startsWith("job-ui-retry-")).toBe(true);
    expect(call?.[2]).toEqual({ retry_failed_items_only: true });
    expect(call?.[3]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("offers a full retry for cancelled jobs", async () => {
    const cancelled = {
      ...baseJob,
      status: "CANCELLED",
      completed_at: "2026-08-08T10:05:00.000Z",
    } satisfies JobResource;
    const client = clientWith(cancelled);
    render(<JobProgress client={client} jobId={cancelled.id} />);
    await settle();

    expect(screen.getByText("Cancelled")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry job" }));
    await settle();
    const call = client.retryJob.mock.calls[0];
    expect(call?.[0]).toBe(cancelled.id);
    expect(typeof call?.[1]).toBe("string");
    expect(call?.[2]).toEqual({ retry_failed_items_only: false });
    expect(call?.[3]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("cleans up polling timer and active request on unmount", async () => {
    vi.useFakeTimers();
    const signals: AbortSignal[] = [];
    const client = {
      ...clientWith(baseJob, 5),
      getJob: vi.fn((_jobId: string, options: RequestOptions = {}) => {
        if (options?.signal !== undefined) {
          signals.push(options.signal);
        }
        return Promise.resolve(jobResult(baseJob, 5));
      }),
    } satisfies JobClient;
    const view = render(<JobProgress client={client} jobId={baseJob.id} />);
    await settle();
    expect(signals[0]?.aborted).toBe(false);

    view.unmount();
    expect(signals[0]?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(client.getJob).toHaveBeenCalledTimes(1);
  });
});
