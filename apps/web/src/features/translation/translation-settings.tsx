"use client";

import { createTransLokaClient, type StartTranslationInput } from "@transloka/api-client";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { LocalModel } from "../models";
import {
  type TranslationReadiness,
  type TranslationUiClient,
} from "./types";

const defaultClient = createTransLokaClient();
const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950";

function startKey(projectId: string): string {
  return `translation-ui-${projectId}-${Date.now().toString(36)}`;
}

export function TranslationSettings({
  client = defaultClient,
  models = [],
  modelId,
  projectId,
  onStarted,
}: Readonly<{
  client?: TranslationUiClient;
  models?: readonly LocalModel[];
  modelId?: string;
  projectId: string;
  onStarted?: (jobId: string) => void;
}>) {
  const installedModels = useMemo(
    () => models.filter((model) => model.is_installed),
    [models],
  );
  const [selectedModelId, setSelectedModelId] = useState(modelId ?? "");
  const [style, setStyle] = useState<NonNullable<StartTranslationInput["translation_style"]>>("PROFESSIONAL");
  const [scope, setScope] = useState<StartTranslationInput["scope"]>("FULL_DOCUMENT");
  const [batchSize, setBatchSize] = useState("5");
  const [readiness, setReadiness] = useState<TranslationReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [startedJobId, setStartedJobId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedModelId((current) => {
      if (modelId !== undefined && installedModels.some((model) => model.id === modelId)) {
        return modelId;
      }
      if (installedModels.some((model) => model.id === current)) {
        return current;
      }
      return installedModels.find((model) => model.is_selected_translation)?.id ?? installedModels[0]?.id ?? "";
    });
  }, [installedModels, modelId]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setReadiness(null);
    setStartedJobId(null);
    if (selectedModelId === "") {
      setError("Select an installed local Ollama model before starting translation.");
      return;
    }
    const parsedBatchSize = Number(batchSize);
    if (!Number.isInteger(parsedBatchSize) || parsedBatchSize < 1 || parsedBatchSize > 100) {
      setError("Batch size must be a whole number between 1 and 100.");
      return;
    }

    setIsStarting(true);
    const readinessResult = await client.getTranslationReadiness(projectId);
    if (!readinessResult.ok) {
      setError(readinessResult.error.message);
      setIsStarting(false);
      return;
    }
    const nextReadiness = readinessResult.data.data;
    setReadiness(nextReadiness);
    if (!nextReadiness.ready) {
      setError("Translation cannot start until all readiness blockers are resolved.");
      setIsStarting(false);
      return;
    }

    const input: StartTranslationInput = {
      scope,
      section_ids: null,
      page_ids: null,
      segment_ids: null,
      model_id: selectedModelId,
      translation_style: style,
      batch_size: parsedBatchSize,
      context_mode: "STANDARD",
      retranslate_existing: false,
      skip_locked_segments: true,
      run_semantic_validation: false,
    };
    const result = await client.startTranslation(projectId, startKey(projectId), input);
    setIsStarting(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setStartedJobId(result.data.data.job_id);
    onStarted?.(result.data.data.job_id);
  };

  return (
    <section
      aria-labelledby="translation-settings-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Translation setup</p>
        <h2 className="mt-1 text-xl font-semibold text-slate-950" id="translation-settings-heading">
          Start local translation
        </h2>
        <p className="mt-1 text-sm text-slate-600">Use a local Ollama model for this project.</p>
      </div>

      <form
        className="mt-6 space-y-5"
        onSubmit={(event) => {
          void submit(event);
        }}
      >
        <div>
          <label className="text-sm font-medium text-slate-800" htmlFor="translation-model">
            Translation model
          </label>
          {installedModels.length === 0 ? (
            <p className="mt-2 rounded-lg border border-dashed border-slate-300 p-3 text-sm text-slate-600">
              No installed local models are available. Check Ollama and refresh the model list.
            </p>
          ) : (
            <select
              className={inputClass}
              id="translation-model"
              onChange={(event) => setSelectedModelId(event.target.value)}
              value={selectedModelId}
            >
              {installedModels.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.ollama_model_name}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label className="text-sm font-medium text-slate-800" htmlFor="translation-style">
              Translation style
            </label>
            <select
              className={inputClass}
              id="translation-style"
              onChange={(event) => setStyle(event.target.value as NonNullable<StartTranslationInput["translation_style"]>)}
              value={style}
            >
              <option value="PROFESSIONAL">Professional</option>
              <option value="ACADEMIC">Academic</option>
              <option value="NATURAL">Natural</option>
              <option value="LITERAL">Literal</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-slate-800" htmlFor="translation-batch-size">
              Batch size
            </label>
            <input
              className={inputClass}
              id="translation-batch-size"
              inputMode="numeric"
              max={100}
              min={1}
              onChange={(event) => setBatchSize(event.target.value)}
              type="number"
              value={batchSize}
            />
          </div>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-800" htmlFor="translation-scope">
            Translation scope
          </label>
          <select
            className={inputClass}
            id="translation-scope"
            onChange={(event) => setScope(event.target.value as StartTranslationInput["scope"])}
            value={scope}
          >
            <option value="FULL_DOCUMENT">Full document</option>
            <option value="UNTRANSLATED_ONLY">Untranslated segments only</option>
            <option value="UNREVIEWED_ONLY">Unreviewed segments only</option>
          </select>
        </div>

        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isStarting || installedModels.length === 0}
          type="submit"
        >
          {isStarting ? "Checking readiness…" : "Start translation"}
        </button>
      </form>

      {error !== null ? (
        <p className="mt-4 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      {readiness !== null ? (
        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4" aria-label="Translation readiness">
          <p className="font-semibold text-slate-900">
            Readiness: {readiness.ready ? "Ready" : "Blocked"}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {readiness.segment_count} segments · approximately {readiness.estimated_batches} batches
          </p>
          {readiness.blocking_issues.length > 0 ? (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-red-800">
              {readiness.blocking_issues.map((issue) => (
                <li key={`${issue.code}:${issue.message}`}>{issue.message}</li>
              ))}
            </ul>
          ) : null}
          {readiness.warnings.length > 0 ? (
            <p className="mt-3 text-sm text-amber-800">
              Warnings: {readiness.warnings.map((warning) => `${warning.code} (${warning.count})`).join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}

      {startedJobId !== null ? (
        <p className="mt-4 text-sm font-medium text-emerald-700" role="status">
          Translation started. Job: {startedJobId}
        </p>
      ) : null}
    </section>
  );
}
