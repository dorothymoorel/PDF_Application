// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelsWorkspace } from "./models-workspace";
import type { LocalModel, ModelsResult, ModelsUiClient } from "./types";

const MODEL: LocalModel = {
  id: "mdl_12345678-1234-4234-8234-123456789abc",
  ollama_model_name: "qwen3:1.7b",
  model_family: "qwen",
  parameter_class: "1.7b",
  quantization: "Q4_K_M",
  disk_size_bytes: 1_000_000,
  license_status: "APPROVED",
  is_installed: true,
  is_selected_translation: false,
  is_selected_validation: false,
};

type SelectTranslationModelMock = (modelId: string) => Promise<ModelsResult<LocalModel>>;
type SelectTranslationModelSpy = ReturnType<typeof vi.fn<SelectTranslationModelMock>>;
type ModelsFixture = { client: ModelsUiClient; selectTranslationModel: SelectTranslationModelSpy };

function clientWith({
  health = { status: "AVAILABLE", base_url: "http://127.0.0.1:11434", version: "unknown" },
  models = [],
}: Readonly<{
  health?: { status: "AVAILABLE" | "DEGRADED" | "UNAVAILABLE"; base_url: string; version: string };
  models?: readonly LocalModel[];
}> = {}): ModelsFixture {
  const selectTranslationModel = vi.fn<SelectTranslationModelMock>().mockResolvedValue({
    ok: true,
    data: { ...MODEL, is_selected_translation: true },
  });
  return {
    client: {
      getHealth: vi.fn().mockResolvedValue({ ok: true, data: health }),
      listModels: vi.fn().mockResolvedValue({ ok: true, data: models }),
      refreshModels: vi.fn().mockResolvedValue({ ok: true, data: models }),
      selectTranslationModel,
    },
    selectTranslationModel,
  };
}

afterEach(cleanup);

describe("models workspace", () => {
  it("shows a safe no-model state without cloud providers", async () => {
    render(<ModelsWorkspace client={clientWith().client} />);

    expect(await screen.findByText("No local translation models detected.")).toBeTruthy();
    expect(screen.getByText("Local Ollama models only. No cloud provider is used.")).toBeTruthy();
    expect(screen.queryByRole("option", { name: /OpenAI|cloud provider/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Refresh local models" })).toBeTruthy();
  });

  it("reports when Ollama is down", async () => {
    render(
      <ModelsWorkspace
        client={clientWith({
          health: {
            status: "UNAVAILABLE",
            base_url: "http://127.0.0.1:11434",
            version: "unknown",
          },
        }).client}
      />,
    );

    expect(await screen.findByText("Ollama is unavailable")).toBeTruthy();
  });

  it("selects an installed local model for translation", async () => {
    const fixture = clientWith({ models: [MODEL] });
    const onModelSelected = vi.fn();
    render(<ModelsWorkspace client={fixture.client} onModelSelected={onModelSelected} />);

    fireEvent.click(await screen.findByRole("button", { name: "Use for translation" }));
    await waitFor(() =>
      expect(fixture.selectTranslationModel.mock.calls.some((call) => call[0] === MODEL.id)).toBe(true),
    );
    expect(onModelSelected).toHaveBeenCalledWith({ ...MODEL, is_selected_translation: true });
    expect(await screen.findByText("Selected for translation")).toBeTruthy();
  });
});
