// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ProjectResource } from "@transloka/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ModelsUiClient } from "../../src/features/models";
import { ProjectWorkspace } from "./project-workspace";
import { createWorkspaceClient } from "./workspace-client";

vi.mock("../documents/document-import", () => ({ DocumentImport: () => null }));

const project = {
  id: "prj_00000000-0000-4000-8000-000000000001",
  name: "Recovered project",
  description: null,
  status: "CREATED",
  source_language: "en",
  target_language: "id",
  document_type: "GENERAL_DOCUMENT",
  translation_style: "PROFESSIONAL",
  reconstruction_mode: "HYBRID",
  progress: 0,
  active_document_id: null,
  settings: {},
  created_at: "2026-09-09T00:00:00Z",
  updated_at: "2026-09-09T00:00:00Z",
} satisfies ProjectResource;

const modelsClient = {
  getHealth: vi.fn(),
  listModels: vi.fn().mockResolvedValue({ ok: true, data: [] }),
  refreshModels: vi.fn(),
  selectTranslationModel: vi.fn(),
} satisfies ModelsUiClient;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("project workspace", () => {
  it("retries one transient project-load failure", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("temporary connection failure"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ data: project, meta: { request_id: "project-retry" } }),
          { headers: { "Content-Type": "application/json" }, status: 200 },
        ),
      );

    render(
      <ProjectWorkspace
        client={createWorkspaceClient({ fetch })}
        modelsClient={modelsClient}
        pollIntervalMs={60_000}
        projectId={project.id}
      />,
    );

    expect(await screen.findByText(project.name)).toBeTruthy();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Project unavailable")).toBeNull();
  });
});
