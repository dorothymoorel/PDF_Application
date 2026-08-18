export type OllamaHealthStatus = "AVAILABLE" | "DEGRADED" | "UNAVAILABLE";

export type OllamaHealth = {
  status: OllamaHealthStatus;
  base_url: string;
  version: string;
};

export type LocalModel = {
  id: string;
  ollama_model_name: string;
  model_family: string | null;
  parameter_class: string | null;
  quantization: string | null;
  disk_size_bytes: number | null;
  license_status: string;
  is_installed: boolean;
  is_selected_translation: boolean;
  is_selected_validation: boolean;
};

export type ModelsResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: Error };

export interface ModelsUiClient {
  getHealth(): Promise<ModelsResult<OllamaHealth>>;
  listModels(): Promise<ModelsResult<readonly LocalModel[]>>;
  refreshModels(): Promise<ModelsResult<readonly LocalModel[]>>;
  selectTranslationModel(modelId: string): Promise<ModelsResult<LocalModel>>;
}
