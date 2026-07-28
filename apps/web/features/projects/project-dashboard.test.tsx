// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createTransLokaClient,
  type ProjectResource,
} from "@transloka/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProjectDashboard } from "./project-dashboard";

type ProjectClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "archiveProject" | "createProject" | "listProjects" | "unarchiveProject"
>;

const project = {
  id: "prj_00000000-0000-4000-8000-000000000001",
  name: "System Design Book",
  description: "A local translation project.",
  status: "CREATED",
  source_language: "en",
  target_language: "id",
  document_type: "TECHNICAL_BOOK",
  translation_style: "PROFESSIONAL",
  reconstruction_mode: "HYBRID",
  progress: 0.25,
  active_document_id: null,
  settings: {},
  created_at: "2026-07-28T10:00:00.000Z",
  updated_at: "2026-07-28T10:05:00.000Z",
} satisfies ProjectResource;

function listResult(projects: ProjectResource[]) {
  return {
    ok: true as const,
    data: {
      data: projects,
      meta: {
        request_id: "project-list",
        pagination: {
          limit: 100,
          offset: 0,
          total: projects.length,
          has_more: false,
        },
      },
    },
    status: 200,
    requestId: "project-list",
  };
}

function dataResult(value: ProjectResource) {
  return {
    ok: true as const,
    data: {
      data: value,
      meta: { request_id: "project-mutation" },
    },
    status: 200,
    requestId: "project-mutation",
  };
}

function mockClient(projects: ProjectResource[] = []) {
  return {
    archiveProject: vi.fn(() => Promise.resolve(dataResult(project))),
    createProject: vi.fn(() => Promise.resolve(dataResult(project))),
    listProjects: vi.fn(() => Promise.resolve(listResult(projects))),
    unarchiveProject: vi.fn(() =>
      Promise.resolve(dataResult({ ...project, status: "CREATED" })),
    ),
  } satisfies ProjectClient;
}

afterEach(() => {
  cleanup();
});

describe("project dashboard", () => {
  it("renders loading and project list states", async () => {
    const client = mockClient([project]);

    render(<ProjectDashboard client={client} />);

    expect(screen.getByRole("status").textContent).toContain("Loading projects");
    expect(await screen.findByText("System Design Book")).toBeTruthy();
    expect(screen.getAllByText("25%")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
  });

  it("creates a project and refreshes the persisted list", async () => {
    const client = mockClient();
    client.listProjects
      .mockResolvedValueOnce(listResult([]))
      .mockResolvedValue(listResult([project]));

    render(<ProjectDashboard client={client} />);
    await screen.findByText("No projects yet");

    fireEvent.change(screen.getByLabelText("Project name"), {
      target: { value: "System Design Book" },
    });
    fireEvent.change(screen.getByLabelText(/Description/), {
      target: { value: "A local translation project." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      expect(client.createProject).toHaveBeenCalledWith({
        name: "System Design Book",
        description: "A local translation project.",
        source_language: "en",
        target_language: "id",
        document_type: "TECHNICAL_BOOK",
        translation_style: "PROFESSIONAL",
        reconstruction_mode: "HYBRID",
      });
    });
    expect(await screen.findByText("System Design Book")).toBeTruthy();
    expect(client.listProjects).toHaveBeenCalledTimes(2);
  });

  it("blocks an invalid create request before contacting the API", async () => {
    const client = mockClient();

    render(<ProjectDashboard client={client} />);
    await screen.findByText("No projects yet");
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Project name is required.")).toBeTruthy();
    expect(client.createProject).not.toHaveBeenCalled();
  });

  it("renders a safe API failure with a retry action", async () => {
    const client = {
      ...mockClient(),
      listProjects: vi.fn(() =>
        Promise.resolve({
          ok: false as const,
          error: {
            kind: "network" as const,
            message: "The local API could not be reached.",
          },
          status: null,
          requestId: null,
        }),
      ),
    } satisfies ProjectClient;

    render(<ProjectDashboard client={client} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Projects could not be loaded.");
    expect(alert.textContent).toContain("The local API could not be reached.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("separates archived projects and renders an archive indicator", async () => {
    const archivedProject = {
      ...project,
      status: "ARCHIVED",
    } satisfies ProjectResource;
    const client = mockClient([archivedProject]);

    render(<ProjectDashboard client={client} />);

    expect(await screen.findByText("System Design Book")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Archived projects" })).toBeTruthy();
    expect(screen.getByText("Archived")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Restore" })).toBeTruthy();
  });
});
