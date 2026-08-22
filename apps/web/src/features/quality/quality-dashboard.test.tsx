// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiResult } from "@transloka/api-client";

import {
  QualityDashboard,
  type QualityDashboardClient,
  type QualityReportRecord,
  type QualityReportsResponse,
  type QualityWarning,
} from "./index";

function success<T>(data: T): ApiResult<T> {
  return { ok: true, data, status: 200, requestId: "req_quality_test" };
}

function warning(overrides: Partial<QualityWarning> = {}): QualityWarning {
  return {
    id: "wrn_quality_1",
    project_id: "prj_test",
    document_id: "doc_test",
    page_id: "pag_test",
    segment_id: "seg_test",
    warning_type: "TERM_INCONSISTENT",
    severity: "MEDIUM",
    message: "The protected term is inconsistent.",
    details: {},
    status: "OPEN",
    resolution_type: null,
    resolution_note: null,
    created_at: "2026-08-22T00:00:00.000Z",
    resolved_at: null,
    ...overrides,
  };
}

function report(overrides: Partial<QualityReportRecord> = {}): QualityReportRecord {
  return {
    id: "qrep_quality_1",
    project_id: "prj_test",
    document_id: "doc_test",
    report_type: "TRANSLATION",
    version: "qa_0.1",
    status: "PASSED_WITH_WARNINGS",
    overall_score: 0.9,
    critical_warning_count: 0,
    high_warning_count: 1,
    medium_warning_count: 1,
    low_warning_count: 0,
    summary: null,
    created_at: "2026-08-22T00:00:00.000Z",
    checks: [],
    warnings: [warning()],
    ...overrides,
  };
}

function response(data: QualityReportRecord[]): QualityReportsResponse {
  return {
    data,
    meta: { request_id: "req_quality_test" },
  };
}

function makeClient(items: QualityReportRecord[]) {
  const listReports = vi.fn<QualityDashboardClient["listReports"]>(() =>
    Promise.resolve(success(response(items))),
  );
  const getReport = vi.fn<QualityDashboardClient["getReport"]>((reportId) =>
    Promise.resolve(success(items.find((item) => item.id === reportId) ?? report())),
  );
  return {
    client: { listReports, getReport } satisfies QualityDashboardClient,
    getReport,
    listReports,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("QualityDashboard", () => {
  it("shows severity counts and makes an open critical issue prominent", async () => {
    const critical = warning({
      id: "wrn_critical",
      warning_type: "OUTPUT_PDF_CORRUPTED",
      severity: "CRITICAL",
    });
    const { client } = makeClient(
      [
        report({
          critical_warning_count: 1,
          warnings: [critical, warning()],
        }),
      ],
    );

    render(<QualityDashboard client={client} projectId="prj_test" />);

    expect(await screen.findByRole("alert", { name: /blocking critical issues/i })).toBeTruthy();
    expect(screen.getByTestId("quality-count-CRITICAL").textContent).toBe("1");
    expect(screen.getByText("OUTPUT_PDF_CORRUPTED")).toBeTruthy();
  });

  it("renders an empty state when no reports are available", async () => {
    const { client } = makeClient([]);

    render(<QualityDashboard client={client} projectId="prj_test" />);

    expect((await screen.findByRole("status")).textContent).toContain("No quality reports found.");
  });

  it("keeps resolved warnings visible and filters warning status", async () => {
    const resolved = warning({
      id: "wrn_resolved",
      status: "RESOLVED",
      resolution_type: "USER_FIXED",
      resolution_note: "Term corrected.",
      resolved_at: "2026-08-22T00:01:00.000Z",
    });
    const { client } = makeClient([report({ warnings: [resolved] })]);

    render(<QualityDashboard client={client} projectId="prj_test" />);

    expect(await screen.findByText(/Resolution: Term corrected\./)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Warning status"), { target: { value: "OPEN" } });
    expect(await screen.findByText("No warnings match the selected filters.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Warning status"), { target: { value: "RESOLVED" } });
    expect(await screen.findByText(/Resolution: Term corrected\./)).toBeTruthy();
  });

  it("passes report filters and navigates to warning page and segment", async () => {
    const nextWarning = warning({ id: "wrn_navigation" });
    const { client, listReports } = makeClient([report({ warnings: [nextWarning] })]);
    const onNavigateToPage = vi.fn();
    const onNavigateToSegment = vi.fn();

    render(
      <QualityDashboard
        client={client}
        onNavigateToPage={onNavigateToPage}
        onNavigateToSegment={onNavigateToSegment}
        projectId="prj_test"
      />,
    );

    await screen.findByText("The protected term is inconsistent.");
    fireEvent.change(screen.getByLabelText("Report type"), { target: { value: "OCR" } });
    fireEvent.change(screen.getByLabelText("Report status"), { target: { value: "FAILED" } });

    await waitFor(() => {
      const lastCall = listReports.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("prj_test");
      expect(lastCall?.[1]).toEqual({ report_type: "OCR", status: "FAILED" });
    });

    fireEvent.click(screen.getByRole("button", { name: "Open page pag_test" }));
    fireEvent.click(screen.getByRole("button", { name: "Open segment seg_test" }));
    expect(onNavigateToPage).toHaveBeenCalledWith("pag_test");
    expect(onNavigateToSegment).toHaveBeenCalledWith("seg_test");
  });
});
