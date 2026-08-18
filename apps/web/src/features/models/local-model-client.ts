import {
  createRequestHeaders,
  DEFAULT_API_BASE_URL,
  validateBaseUrl,
} from "@transloka/api-client";

import type {
  LocalModel,
  ModelsResult,
  ModelsUiClient,
  OllamaHealth,
  OllamaHealthStatus,
} from "./types";

type FetchImplementation = (input: string, init?: RequestInit) => Promise<Response>;

type LocalModelsClientOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isHealthStatus(value: unknown): value is OllamaHealthStatus {
  return value === "AVAILABLE" || value === "DEGRADED" || value === "UNAVAILABLE";
}

function isOllamaHealth(value: unknown): value is OllamaHealth {
  return (
    isRecord(value) &&
    isHealthStatus(value.status) &&
    isString(value.base_url) &&
    isString(value.version)
  );
}

function isLocalModel(value: unknown): value is LocalModel {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.ollama_model_name) &&
    isNullableString(value.model_family) &&
    isNullableString(value.parameter_class) &&
    isNullableString(value.quantization) &&
    isNullableNumber(value.disk_size_bytes) &&
    isString(value.license_status) &&
    isBoolean(value.is_installed) &&
    isBoolean(value.is_selected_translation) &&
    isBoolean(value.is_selected_validation)
  );
}

function responseData(payload: unknown): unknown {
  return isRecord(payload) ? payload.data : undefined;
}

function errorMessage(response: Response): string {
  return `Local model request failed (${response.status} ${response.statusText || "HTTP error"}).`;
}

export function createLocalModelsClient(
  options: LocalModelsClientOptions = {},
): ModelsUiClient {
  const baseUrl = validateBaseUrl(options.baseUrl ?? DEFAULT_API_BASE_URL);
  const fetchImplementation = options.fetch ?? globalThis.fetch.bind(globalThis);

  async function request<T>(
    path: string,
    method: "GET" | "POST",
    validate: (value: unknown) => value is T,
    body?: unknown,
  ): Promise<ModelsResult<T>> {
    try {
      const headers = createRequestHeaders(method);
      const init: RequestInit = {
        cache: "no-store",
        credentials: "omit",
        headers,
        method,
      };
      if (body !== undefined) {
        headers.set("Content-Type", "application/json");
        init.body = JSON.stringify(body);
      }
      const response = await fetchImplementation(`${baseUrl}${path}`, init);
      if (!response.ok) {
        return { ok: false, error: new Error(errorMessage(response)) };
      }
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        return { ok: false, error: new Error("Local model response was not valid JSON.") };
      }
      const data = responseData(payload);
      if (!validate(data)) {
        return { ok: false, error: new Error("Local model response did not match the UI contract.") };
      }
      return { ok: true, data };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error : new Error("Local model request failed."),
      };
    }
  }

  return {
    getHealth: () => request("/api/v1/models/ollama/health", "GET", isOllamaHealth),
    listModels: () =>
      request(
        "/api/v1/models",
        "GET",
        (value): value is readonly LocalModel[] =>
          Array.isArray(value) && value.every(isLocalModel),
      ),
    refreshModels: () =>
      request(
        "/api/v1/models/refresh",
        "POST",
        (value): value is readonly LocalModel[] =>
          Array.isArray(value) && value.every(isLocalModel),
      ),
    selectTranslationModel: (modelId) =>
      request(
        `/api/v1/models/${encodeURIComponent(modelId)}/select`,
        "POST",
        isLocalModel,
        { role: "TRANSLATION" },
      ),
  };
}
