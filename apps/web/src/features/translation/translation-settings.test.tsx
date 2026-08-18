// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LocalModel } from "../models";
import { TranslationSettings } from "./translation-settings";
import type { TranslationUiClient } from "./types";

const MODEL: LocalModel = {
  id: "mdl_12345678-1234-4234-8234-123456789abc",
  ollama_model_name: "qwen3:1.7b",
  model_family: "qwen",
  parameter_class: "1.7b",
  quantization: "Q4_K_M",
  disk_size_bytes: 1_000_000,
  license_status: "APPROVED",
  is_installed: true,
  is_selected_translation: true,
  is_selected_validation: false,
};

type StartTranslationMock = TranslationUiClient["startTranslation"];
type StartTranslationSpy = ReturnType<typeof vi.fn<StartTranslationMock>>;

function clientWith(ready = true): TranslationUiClient & { startTranslation: StartTranslationSpy } {
  const startTranslation = vi.fn<StartTranslationMock>().mockResolvedValue({
    ok: true,
    data: { data: { job_id: "job_translation_1", status: "QUEUED" }, meta: { request_id: "start" } },
    status: 202,
    requestId: "start",
  });
  return {
    getTranslationReadiness: vi.fn().mockResolvedValue({
      ok: true,
      data: {
        data: {
          ready,
          blocking_issues: ready ? [] : [{ code: "NO_DOCUMENT", message: "Upload a document first." }],
          warnings: [],
          segment_count: 10,
          estimated_batches: 2,
        },
        meta: { request_id: "readiness" },
      },
      status: 200,
      requestId: "readiness",
    }),
    startTranslation,
    getTranslationStatus: vi.fn(),
    cancelTranslation: vi.fn(),
    retryFailedTranslation: vi.fn(),
  };
}

afterEach(cleanup);

describe("translation settings", () => {
  it("requires a local model before starting", () => {
    const client = clientWith();
    render(<TranslationSettings client={client} projectId="prj_1" />);

    expect(screen.getByText(/No installed local models are available\./)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start translation" })).toHaveProperty("disabled", true);
    expect(client.getTranslationReadiness).not.toHaveBeenCalled();
  });

  it("shows readiness blockers and does not start when the project is not ready", async () => {
    const client = clientWith(false);
    render(<TranslationSettings client={client} models={[MODEL]} projectId="prj_1" />);
    fireEvent.click(screen.getByRole("button", { name: "Start translation" }));

    expect(await screen.findByText("Translation cannot start until all readiness blockers are resolved.")).toBeTruthy();
    expect(screen.getByText("Upload a document first.")).toBeTruthy();
    expect(client.startTranslation).not.toHaveBeenCalled();
  });

  it("starts a local translation with style and batch settings", async () => {
    const client = clientWith();
    const onStarted = vi.fn();
    render(
      <TranslationSettings
        client={client}
        models={[MODEL]}
        onStarted={onStarted}
        projectId="prj_1"
      />,
    );
    fireEvent.change(screen.getByLabelText("Translation style"), { target: { value: "ACADEMIC" } });
    fireEvent.change(screen.getByLabelText("Batch size"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Start translation" }));

    await waitFor(() => expect(client.startTranslation).toHaveBeenCalled());
    const startTranslationSpy = client.startTranslation as unknown as {
      mock: { calls: readonly (readonly unknown[])[] };
    };
    const call = startTranslationSpy.mock.calls[0];
    expect(call?.[0]).toBe("prj_1");
    expect(call?.[2]).toMatchObject({
      model_id: MODEL.id,
      translation_style: "ACADEMIC",
      batch_size: 8,
      context_mode: "STANDARD",
      scope: "FULL_DOCUMENT",
    });
    expect(onStarted).toHaveBeenCalledWith("job_translation_1");
    expect(await screen.findByText("Translation started. Job: job_translation_1")).toBeTruthy();
  });
});
