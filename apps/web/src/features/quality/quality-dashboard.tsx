"use client";

import { useEffect, useMemo, useState } from "react";

import {
  humanizeQualityValue,
  QUALITY_REPORT_STATUSES,
  QUALITY_REPORT_TYPES,
  QUALITY_SEVERITIES,
  QUALITY_WARNING_STATUSES,
  type QualityDashboardClient,
  type QualityReportRecord,
  type QualityReportQueryFilters,
  type QualityReportStatus,
  type QualityReportType,
  type QualitySeverity,
  type QualityWarning,
  type QualityWarningStatus,
} from "./types";

type FilterState = Readonly<{
  reportType: QualityReportType | "";
  reportStatus: QualityReportStatus | "";
  severity: QualitySeverity | "";
  warningStatus: QualityWarningStatus | "";
}>;

const INITIAL_FILTERS: FilterState = {
  reportType: "",
  reportStatus: "",
  severity: "",
  warningStatus: "",
};

const SEVERITY_TONE: Record<QualitySeverity, string> = {
  INFO: "border-slate-200 bg-slate-50 text-slate-800",
  LOW: "border-sky-200 bg-sky-50 text-sky-900",
  MEDIUM: "border-amber-200 bg-amber-50 text-amber-900",
  HIGH: "border-orange-200 bg-orange-50 text-orange-950",
  CRITICAL: "border-red-300 bg-red-50 text-red-950",
};

function toQueryFilters(filters: FilterState): QualityReportQueryFilters {
  return {
    ...(filters.reportType === "" ? {} : { report_type: filters.reportType }),
    ...(filters.reportStatus === "" ? {} : { status: filters.reportStatus }),
    ...(filters.severity === "" ? {} : { severity: filters.severity }),
    ...(filters.warningStatus === "" ? {} : { warning_status: filters.warningStatus }),
  };
}

function warningCounts(report: QualityReportRecord | null): Record<QualitySeverity, number> {
  const counts: Record<QualitySeverity, number> = {
    INFO: 0,
    LOW: 0,
    MEDIUM: 0,
    HIGH: 0,
    CRITICAL: 0,
  };
  if (report === null) {
    return counts;
  }
  for (const warning of report.warnings) {
    counts[warning.severity] += 1;
  }
  if (report.warnings.length === 0) {
    counts.CRITICAL = report.critical_warning_count;
    counts.HIGH = report.high_warning_count;
    counts.MEDIUM = report.medium_warning_count;
    counts.LOW = report.low_warning_count;
  }
  return counts;
}

function aggregateWarningCounts(reports: readonly QualityReportRecord[]): Record<QualitySeverity, number> {
  const counts: Record<QualitySeverity, number> = {
    INFO: 0,
    LOW: 0,
    MEDIUM: 0,
    HIGH: 0,
    CRITICAL: 0,
  };
  for (const report of reports) {
    const reportCounts = warningCounts(report);
    for (const severity of QUALITY_SEVERITIES) {
      counts[severity] += reportCounts[severity];
    }
  }
  return counts;
}

function isOpenCritical(warning: QualityWarning): boolean {
  return warning.severity === "CRITICAL" && warning.status === "OPEN";
}

export function QualityDashboard({
  client,
  onNavigateToPage,
  onNavigateToSegment,
  projectId,
}: Readonly<{
  client: QualityDashboardClient;
  onNavigateToPage?(pageId: string): void;
  onNavigateToSegment?(segmentId: string): void;
  projectId: string;
}>) {
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [reports, setReports] = useState<QualityReportRecord[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<QualityReportRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setError(null);

    void client
      .listReports(projectId, toQueryFilters(filters), { signal: controller.signal })
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
        const nextReports = result.data.data;
        setReports(nextReports);
        setSelectedReportId((current) =>
          current !== null && nextReports.some((report) => report.id === current)
            ? current
            : nextReports[0]?.id ?? null,
        );
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(cause instanceof Error ? cause.message : "Quality reports could not be loaded.");
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

  useEffect(() => {
    if (selectedReportId === null) {
      setSelectedReport(null);
      return;
    }
    const controller = new AbortController();
    let active = true;
    setIsLoadingDetail(true);
    setSelectedReport(null);

    void client
      .getReport(selectedReportId, { signal: controller.signal })
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
        setSelectedReport(result.data);
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setError(cause instanceof Error ? cause.message : "The quality report could not be loaded.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoadingDetail(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [client, selectedReportId]);

  const visibleWarnings = useMemo(() => {
    if (selectedReport === null) {
      return [];
    }
    return selectedReport.warnings.filter(
      (warning) =>
        (filters.severity === "" || warning.severity === filters.severity) &&
        (filters.warningStatus === "" || warning.status === filters.warningStatus),
    );
  }, [filters.severity, filters.warningStatus, selectedReport]);

  const counts = selectedReport === null ? aggregateWarningCounts(reports) : warningCounts(selectedReport);
  const countsDescription = selectedReport === null ? "warnings in matching reports" : "warnings in selected report";
  const blockingWarnings = selectedReport?.warnings.filter(isOpenCritical) ?? [];

  const updateFilter = <Key extends keyof FilterState>(key: Key, value: FilterState[Key]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  return (
    <main
      aria-busy={isLoading || isLoadingDetail}
      aria-labelledby="quality-dashboard-heading"
      className="w-full space-y-6"
    >
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Quality control</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="quality-dashboard-heading">
          Warning and quality dashboard
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Inspect report checks, keep warning history, and resolve blocking quality issues before export.
        </p>
      </header>

      {error !== null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
          <p className="font-medium text-red-900">Quality data could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={() => setReloadVersion((value) => value + 1)}
            type="button"
          >
            Retry
          </button>
        </div>
      ) : null}

      <fieldset className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <legend className="sr-only">Quality dashboard filters</legend>
        <label className="text-sm font-medium text-slate-800" htmlFor="quality-report-type">
          Report type
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="quality-report-type"
            onChange={(event) => updateFilter("reportType", event.target.value as QualityReportType | "")}
            value={filters.reportType}
          >
            <option value="">All report types</option>
            {QUALITY_REPORT_TYPES.map((value) => (
              <option key={value} value={value}>
                {humanizeQualityValue(value)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="quality-report-status">
          Report status
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="quality-report-status"
            onChange={(event) => updateFilter("reportStatus", event.target.value as QualityReportStatus | "")}
            value={filters.reportStatus}
          >
            <option value="">All report statuses</option>
            {QUALITY_REPORT_STATUSES.map((value) => (
              <option key={value} value={value}>
                {humanizeQualityValue(value)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="quality-severity">
          Severity
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="quality-severity"
            onChange={(event) => updateFilter("severity", event.target.value as QualitySeverity | "")}
            value={filters.severity}
          >
            <option value="">All severities</option>
            {QUALITY_SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="quality-warning-status">
          Warning status
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="quality-warning-status"
            onChange={(event) =>
              updateFilter("warningStatus", event.target.value as QualityWarningStatus | "")
            }
            value={filters.warningStatus}
          >
            <option value="">All warning statuses</option>
            {QUALITY_WARNING_STATUSES.map((value) => (
              <option key={value} value={value}>
                {humanizeQualityValue(value)}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <section aria-label="Warning counts" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {QUALITY_SEVERITIES.map((severity) => (
          <div className={`rounded-xl border p-4 ${SEVERITY_TONE[severity]}`} key={severity}>
            <p className="text-xs font-semibold uppercase tracking-wide">{severity}</p>
            <p className="mt-1 text-2xl font-bold" data-testid={`quality-count-${severity}`}>
              {counts[severity]}
            </p>
            <p className="text-xs">{countsDescription}</p>
          </div>
        ))}
      </section>

      {isOpenCriticalReport(blockingWarnings) ? (
        <div
          aria-labelledby="quality-blocking-heading"
          className="rounded-2xl border-2 border-red-400 bg-red-50 p-5 text-red-950"
          role="alert"
        >
          <p className="font-bold" id="quality-blocking-heading">Blocking critical issues</p>
          <p className="mt-1 text-sm">
            {blockingWarnings.length} critical issue(s) remain open and block completion or export until resolved.
          </p>
        </div>
      ) : null}

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading quality reports…
        </p>
      ) : reports.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          No quality reports found.
        </p>
      ) : (
        <section aria-labelledby="quality-reports-heading" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Reports</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950" id="quality-reports-heading">
                Quality report history
              </h2>
            </div>
            <p className="text-sm text-slate-600">{reports.length} report(s)</p>
          </div>
          <ul aria-label="Quality reports" className="mt-4 divide-y divide-slate-200">
            {reports.map((report) => (
              <li key={report.id}>
                <button
                  aria-pressed={selectedReportId === report.id}
                  className="block w-full px-2 py-4 text-left transition hover:bg-blue-50"
                  onClick={() => setSelectedReportId(report.id)}
                  type="button"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-950">{humanizeQualityValue(report.report_type)}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {report.id} · {report.version} · {new Date(report.created_at).toLocaleString()}
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-800">
                      {humanizeQualityValue(report.status)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-700">
                    Score: {report.overall_score === null ? "Not scored" : `${Math.round(report.overall_score * 100)}%`} ·{" "}
                    {report.critical_warning_count} critical · {report.high_warning_count} high · {report.medium_warning_count} medium · {report.low_warning_count} low
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {selectedReport !== null ? (
        <section aria-labelledby="quality-report-details-heading" className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <header>
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Report details</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950" id="quality-report-details-heading">
              {humanizeQualityValue(selectedReport.report_type)} checks and warnings
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {selectedReport.id} · {humanizeQualityValue(selectedReport.status)}
            </p>
          </header>

          <section aria-labelledby="quality-checks-heading">
            <h3 className="text-lg font-semibold text-slate-950" id="quality-checks-heading">
              Checks
            </h3>
            {selectedReport.checks.length === 0 ? (
              <p className="mt-2 text-sm text-slate-600">No checks recorded for this report.</p>
            ) : (
              <ul className="mt-3 grid gap-3 md:grid-cols-2">
                {selectedReport.checks.map((check) => (
                  <li className="rounded-xl border border-slate-200 bg-slate-50 p-4" key={check.id}>
                    <div className="flex flex-wrap justify-between gap-2">
                      <p className="font-semibold text-slate-950">{humanizeQualityValue(check.check_type)}</p>
                      <span className="text-xs font-semibold text-slate-700">
                        {humanizeQualityValue(check.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">
                      {humanizeQualityValue(check.scope_type)} · {check.scope_id}
                      {check.score === null ? "" : ` · ${Math.round(check.score * 100)}%`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="quality-warnings-heading">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-950" id="quality-warnings-heading">
                  Warnings
                </h3>
                <p className="mt-1 text-sm text-slate-600">Resolved findings remain visible in this history.</p>
              </div>
              <p className="text-sm text-slate-600">{visibleWarnings.length} shown</p>
            </div>
            {isLoadingDetail ? (
              <p className="mt-3 text-sm text-slate-600" role="status">Loading report details…</p>
            ) : visibleWarnings.length === 0 ? (
              <p className="mt-3 text-sm text-slate-600" role="status">
                {selectedReport.warnings.length === 0
                  ? "No warnings in this report."
                  : "No warnings match the selected filters."}
              </p>
            ) : (
              <ul aria-label="Quality warnings" className="mt-3 space-y-3">
                {visibleWarnings.map((warning) => (
                  <li
                    className={`rounded-xl border p-4 ${
                      warning.severity === "CRITICAL" && warning.status === "OPEN"
                        ? SEVERITY_TONE.CRITICAL
                        : "border-slate-200 bg-white"
                    }`}
                    key={warning.id}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-950">{warning.warning_type}</p>
                        <p className="mt-1 text-sm text-slate-700">{warning.message}</p>
                      </div>
                      <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold text-slate-900">
                        {warning.severity} · {humanizeQualityValue(warning.status)}
                      </span>
                    </div>
                    {warning.resolution_note !== null ? (
                      <p className="mt-3 text-xs text-slate-600">Resolution: {warning.resolution_note}</p>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {warning.page_id !== null && onNavigateToPage !== undefined ? (
                        <button
                          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100"
                          onClick={() => onNavigateToPage(warning.page_id as string)}
                          type="button"
                        >
                          Open page {warning.page_id}
                        </button>
                      ) : null}
                      {warning.segment_id !== null && onNavigateToSegment !== undefined ? (
                        <button
                          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100"
                          onClick={() => onNavigateToSegment(warning.segment_id as string)}
                          type="button"
                        >
                          Open segment {warning.segment_id}
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </section>
      ) : null}
    </main>
  );
}

function isOpenCriticalReport(warnings: readonly QualityWarning[]): boolean {
  return warnings.length > 0;
}

export const QualityWorkspace = QualityDashboard;
