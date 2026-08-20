"use client";

import { useEffect, useState } from "react";

import type { WarningClient, WarningRecord, WarningSeverity, WarningStatus } from "./types";

const STATUS_OPTIONS: WarningStatus[] = [
  "OPEN",
  "RESOLVED",
  "ACCEPTED",
  "FALSE_POSITIVE",
  "IGNORED_BY_POLICY",
];
const SEVERITY_OPTIONS: WarningSeverity[] = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
const NON_OVERRIDEABLE_CRITICAL_TYPES = new Set([
  "MISSING_TRANSLATED_SEGMENT",
  "PLACEHOLDER_RESTORATION_FAILED",
  "OUTPUT_PDF_CORRUPTED",
  "ORIGINAL_FILE_CHECKSUM_MISMATCH",
  "PATH_TRAVERSAL_DETECTED",
  "TABLE_STRUCTURE_CORRUPTED_CRITICAL",
  "CRITICAL_TEXT_CLIPPING",
  "CRITICAL_LAYOUT_COLLISION",
]);

export function Warnings({
  client,
  projectId,
}: Readonly<{
  client: WarningClient;
  projectId: string;
}>) {
  const [status, setStatus] = useState<WarningStatus | "">("");
  const [severity, setSeverity] = useState<WarningSeverity | "">("");
  const [items, setItems] = useState<WarningRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setIsLoading(true);
    setError(null);
    const filters = {
      ...(status === "" ? {} : { status }),
      ...(severity === "" ? {} : { severity }),
    };

    void client
      .listWarnings(projectId, filters, { signal: controller.signal })
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
          setError(cause instanceof Error ? cause.message : "Warnings could not be loaded.");
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
  }, [client, projectId, reloadVersion, severity, status]);

  const mutate = async (
    item: WarningRecord,
    action: "accept" | "false-positive" | "resolve",
  ) => {
    setMutatingId(item.id);
    setError(null);
    const result =
      action === "accept"
        ? await client.acceptWarning(item.id)
        : action === "false-positive"
          ? await client.markWarningFalsePositive(item.id)
          : await client.resolveWarning(item.id);
    setMutatingId(null);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setReloadVersion((value) => value + 1);
  };

  return (
    <section aria-busy={isLoading} aria-labelledby="warnings-heading" className="w-full space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Quality warnings</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-950" id="warnings-heading">
          Warning resolution
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Resolve findings without deleting their history.
        </p>
      </header>

      <fieldset className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-2">
        <legend className="sr-only">Warning filters</legend>
        <label className="text-sm font-medium text-slate-800" htmlFor="warnings-status">
          Status
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="warnings-status"
            onChange={(event) => setStatus(event.target.value as WarningStatus | "")}
            value={status}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium text-slate-800" htmlFor="warnings-severity">
          Severity
          <select
            className="mt-2 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            id="warnings-severity"
            onChange={(event) => setSeverity(event.target.value as WarningSeverity | "")}
            value={severity}
          >
            <option value="">All severities</option>
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      {isLoading ? (
        <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600" role="status">
          Loading warnings…
        </p>
      ) : error !== null ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
          <p className="font-medium text-red-900">Warnings could not be loaded.</p>
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
          No warnings found.
        </p>
      ) : (
        <ol aria-label="Warnings" className="space-y-3">
          {items.map((item) => {
            const isOpen = item.status === "OPEN";
            const criticalBlocked =
              item.severity === "CRITICAL" &&
              isOpen &&
              NON_OVERRIDEABLE_CRITICAL_TYPES.has(item.warning_type);
            const disabled = !isOpen || mutatingId === item.id;
            return (
              <li className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" key={item.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">{item.warning_type}</p>
                    <p className="mt-1 text-sm text-slate-700">{item.message}</p>
                  </div>
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
                    {item.severity} · {item.status}
                  </span>
                </div>
                {item.resolution_note ? (
                  <p className="mt-3 text-xs text-slate-500">Resolution: {item.resolution_note}</p>
                ) : null}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    className="rounded-lg bg-blue-700 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={disabled}
                    onClick={() => void mutate(item, "resolve")}
                    type="button"
                  >
                    Resolve
                  </button>
                  <button
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={disabled || criticalBlocked}
                    onClick={() => void mutate(item, "accept")}
                    title={criticalBlocked ? "Non-overridable critical warning" : undefined}
                    type="button"
                  >
                    Accept
                  </button>
                  <button
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={disabled || criticalBlocked}
                    onClick={() => void mutate(item, "false-positive")}
                    title={criticalBlocked ? "Non-overridable critical warning" : undefined}
                    type="button"
                  >
                    False positive
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
