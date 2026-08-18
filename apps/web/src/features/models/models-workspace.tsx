"use client";

import { useEffect, useState } from "react";

import { createLocalModelsClient } from "./local-model-client";
import type { LocalModel, ModelsUiClient, OllamaHealth } from "./types";

const defaultClient = createLocalModelsClient();

function healthLabel(health: OllamaHealth | null): string {
  if (health === null) {
    return "Checking Ollama health…";
  }
  if (health.status === "AVAILABLE") {
    return "Ollama is available";
  }
  if (health.status === "DEGRADED") {
    return "Ollama is degraded";
  }
  return "Ollama is unavailable";
}

function modelDetails(model: LocalModel): string {
  const details = [model.model_family, model.parameter_class, model.quantization].filter(
    (value): value is string => value !== null && value.trim() !== "",
  );
  return details.length > 0 ? details.join(" · ") : "Local Ollama model";
}

export function ModelsWorkspace({
  client = defaultClient,
  onModelSelected,
}: Readonly<{
  client?: ModelsUiClient;
  onModelSelected?: (model: LocalModel) => void;
}>) {
  const [health, setHealth] = useState<OllamaHealth | null>(null);
  const [models, setModels] = useState<readonly LocalModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    const [healthResult, modelsResult] = await Promise.all([
      client.getHealth(),
      client.listModels(),
    ]);
    if (healthResult.ok) {
      setHealth(healthResult.data);
    } else {
      setHealth(null);
      setError(healthResult.error.message);
    }
    if (modelsResult.ok) {
      setModels(modelsResult.data);
    } else {
      setModels([]);
      setError((current) => current ?? modelsResult.error.message);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    void load();
  }, [client]);

  const refresh = async () => {
    setPendingAction("refresh");
    setError(null);
    const result = await client.refreshModels();
    if (result.ok) {
      setModels(result.data);
    } else {
      setError(result.error.message);
    }
    setPendingAction(null);
  };

  const selectModel = async (model: LocalModel) => {
    setPendingAction(`select:${model.id}`);
    setError(null);
    const result = await client.selectTranslationModel(model.id);
    if (result.ok) {
      setModels((current) =>
        current.map((item) => ({
          ...item,
          is_selected_translation: item.id === result.data.id,
        })),
      );
      onModelSelected?.(result.data);
    } else {
      setError(result.error.message);
    }
    setPendingAction(null);
  };

  return (
    <section
      aria-busy={isLoading}
      aria-labelledby="models-workspace-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Local model runtime
          </p>
          <h2 className="mt-1 text-xl font-semibold text-slate-950" id="models-workspace-heading">
            Translation models
          </h2>
          <p className="mt-1 text-sm text-slate-600">Local Ollama models only. No cloud provider is used.</p>
        </div>
        <button
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={pendingAction !== null || isLoading}
          onClick={() => void refresh()}
          type="button"
        >
          {pendingAction === "refresh" ? "Refreshing…" : "Refresh local models"}
        </button>
      </div>

      <div
        aria-live="polite"
        className={`mt-5 rounded-xl border p-4 text-sm ${
          health?.status === "AVAILABLE"
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-amber-200 bg-amber-50 text-amber-900"
        }`}
        role="status"
      >
        <p className="font-semibold">{healthLabel(health)}</p>
        {health !== null ? <p className="mt-1">Endpoint: {health.base_url}</p> : null}
      </div>

      {error !== null ? (
        <p className="mt-4 text-sm text-red-700" role="alert">
          {error}
        </p>
      ) : null}

      {isLoading ? (
        <p className="mt-6 text-sm text-slate-600" role="status">
          Loading local models…
        </p>
      ) : models.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-5">
          <p className="font-medium text-slate-900">No local translation models detected.</p>
          <p className="mt-1 text-sm text-slate-600">
            Install a model in the local Ollama runtime, then refresh this list.
          </p>
        </div>
      ) : (
        <ul className="mt-6 space-y-3" aria-label="Local translation models">
          {models.map((model) => (
            <li
              className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 p-4"
              key={model.id}
            >
              <div>
                <p className="font-semibold text-slate-950">{model.ollama_model_name}</p>
                <p className="mt-1 text-sm text-slate-600">{modelDetails(model)}</p>
                {model.is_selected_translation ? (
                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                    Selected for translation
                  </p>
                ) : null}
              </div>
              <button
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={pendingAction !== null || model.is_selected_translation || !model.is_installed}
                onClick={() => void selectModel(model)}
                type="button"
              >
                {pendingAction === `select:${model.id}` ? "Selecting…" : "Use for translation"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
