// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiResult } from "@transloka/api-client";

import { Warnings, type WarningClient, type WarningListResponse, type WarningRecord } from "./index";

function success<T>(data: T): ApiResult<T> {
  return { ok: true, data, status: 200, requestId: "req_warning_test" };
}

function warning(overrides: Partial<WarningRecord> = {}): WarningRecord {
  return {
    id: "wrn_warning_1",
    project_id: "prj_test",
    document_id: null,
    page_id: null,
    segment_id: "seg_test",
    warning_type: "TERM_INCONSISTENT",
    severity: "MEDIUM",
    message: "The protected term is inconsistent.",
    details: {},
    status: "OPEN",
    resolution_type: null,
    resolution_note: null,
    created_at: "2026-08-20T00:00:00.000Z",
    resolved_at: null,
    ...overrides,
  };
}

function response(data: WarningRecord[]): WarningListResponse {
  return {
    data,
    meta: {
      request_id: "req_warning_test",
      pagination: { limit: 50, next_cursor: null, has_more: false },
    },
  };
}

function makeClient(items: WarningRecord[]) {
  const listWarnings = vi.fn<WarningClient["listWarnings"]>(() =>
    Promise.resolve(success(response(items))),
  );
  const resolveWarning = vi.fn<WarningClient["resolveWarning"]>(() =>
    Promise.resolve(success(warning({ status: "RESOLVED" }))),
  );
  const acceptWarning = vi.fn<WarningClient["acceptWarning"]>(() =>
    Promise.resolve(success(warning({ status: "ACCEPTED" }))),
  );
  const markWarningFalsePositive = vi.fn<WarningClient["markWarningFalsePositive"]>(() =>
    Promise.resolve(success(warning({ status: "FALSE_POSITIVE" }))),
  );
  const client = {
    listWarnings,
    resolveWarning,
    acceptWarning,
    markWarningFalsePositive,
  } satisfies WarningClient;
  return { client, listWarnings, resolveWarning };
}

describe("Warnings", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("resolves an open warning and reloads the list", async () => {
    const { client, listWarnings, resolveWarning } = makeClient([warning()]);
    render(<Warnings client={client} projectId="prj_test" />);

    await screen.findByText("The protected term is inconsistent.");
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => expect(resolveWarning).toHaveBeenCalledWith("wrn_warning_1"));
    await waitFor(() => expect(listWarnings).toHaveBeenCalledTimes(2));
  });

  it("blocks accept and false-positive actions for critical warnings", async () => {
    const { client } = makeClient([
      warning({
        id: "wrn_critical",
        severity: "CRITICAL",
        warning_type: "PATH_TRAVERSAL_DETECTED",
      }),
    ]);
    render(<Warnings client={client} projectId="prj_test" />);

    await screen.findByText("The protected term is inconsistent.");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Accept" }).disabled).toBe(true);
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "False positive" }).disabled,
    ).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Resolve" }).disabled).toBe(false);
  });

  it("filters warnings by status and severity", async () => {
    const { client, listWarnings } = makeClient([warning()]);
    render(<Warnings client={client} projectId="prj_test" />);

    await screen.findByText("The protected term is inconsistent.");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "OPEN" } });
    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "HIGH" } });

    await waitFor(() => {
      const lastCall = listWarnings.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("prj_test");
      expect(lastCall?.[1]).toEqual({ status: "OPEN", severity: "HIGH" });
    });
  });
});
