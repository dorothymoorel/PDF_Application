// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type {
  ApiResult,
  components,
  createTransLokaClient,
  DocumentDetailResponse,
  JobResource,
} from "@transloka/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DocumentImport,
  type DocumentOverview,
  type UploadDocument,
  uploadDocument,
} from "./document-import";

const PROJECT_ID = "prj_00000000-0000-4000-8000-000000000001";
const SECOND_PROJECT_ID = "prj_00000000-0000-4000-8000-000000000004";
const DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000002";
const JOB_ID = "job_00000000-0000-4000-8000-000000000003";
type SuccessfulApiResult<T> = Extract<ApiResult<T>, { ok: true }>;
type ProjectDataResponse = components["schemas"]["ProjectDataResponse"];
type JobDataResponse = components["schemas"]["JobDataResponse"];
type JobListResponse = components["schemas"]["JobListResponse"];
type WorkspaceClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "getDocument" | "getJob" | "getProject" | "listJobs"
>;
const overview: DocumentOverview = {
  originalFilename: "guide.pdf",
  sizeBytes: 2_097_152,
  title: "System Guide",
  pageCount: 2,
  analysisStatus: "ANALYZING",
  thumbnails: [
    {
      id: "pag_1",
      pageNumber: 1,
      url: "/api/v1/pages/pag_1/thumbnail",
    },
    {
      id: "pag_2",
      pageNumber: 2,
      url: "/api/v1/pages/pag_2/thumbnail",
    },
  ],
};

function pdfFile(): File {
  return new File(["%PDF-1.7"], "guide.pdf", { type: "application/pdf" });
}

function uploadButton(): HTMLButtonElement {
  const element = screen.getByRole("button", { name: "Upload PDF" });
  if (!(element instanceof HTMLButtonElement)) {
    throw new TypeError("Upload control is not a button.");
  }
  return element;
}

function createEmptyClient(): WorkspaceClient {
  return {
    getProject: vi.fn<WorkspaceClient["getProject"]>(() =>
      Promise.resolve(createProjectWithDocument(null)),
    ),
    getDocument: vi.fn<WorkspaceClient["getDocument"]>(),
    listJobs: vi.fn(() =>
      Promise.resolve({
        ok: true as const,
        data: {
          data: [],
          meta: {
            request_id: "req-1",
            pagination: { limit: 1, next_cursor: null, has_more: false },
          },
        },
        status: 200,
        requestId: "req-1",
      }),
    ),
    getJob: vi.fn<WorkspaceClient["getJob"]>(),
  };
}

function createProjectWithDocument(
  activeId: string | null = DOCUMENT_ID,
): SuccessfulApiResult<ProjectDataResponse> {
  return {
    ok: true as const,
    data: {
      data: {
        id: PROJECT_ID,
        name: "Test Project",
        description: null,
        status: "ANALYZING",
        source_language: "en",
        target_language: "id",
        document_type: "TECHNICAL_BOOK",
        translation_style: "PROFESSIONAL",
        reconstruction_mode: "HYBRID",
        progress: 0,
        active_document_id: activeId,
        settings: {},
        created_at: "2026-08-28T00:00:00.000Z",
        updated_at: "2026-08-28T00:00:00.000Z",
      },
      meta: { request_id: "req-1" },
    },
    status: 200,
    requestId: "req-1",
  };
}

function documentResponse(): SuccessfulApiResult<DocumentDetailResponse> {
  return {
    ok: true as const,
    data: {
      data: {
        id: DOCUMENT_ID,
        project_id: PROJECT_ID,
        original_file_id: "fil_00000000-0000-4000-8000-000000000010",
        status: "CREATED",
        original_filename: "guide.pdf",
        size_bytes: 612,
        checksum_sha256: "0".repeat(64),
        page_count: 1,
        title: null,
      },
      meta: { request_id: "req-1" },
    },
    status: 200,
    requestId: "req-1",
  };
}

function jobResponse(overrides: Partial<JobResource> = {}): SuccessfulApiResult<JobDataResponse> {
  return {
    ok: true as const,
    data: {
      data: {
        id: JOB_ID,
        job_type: "ANALYZE_DOCUMENT",
        status: "QUEUED",
        progress: 0,
        current_stage: "QUEUED",
        project_id: PROJECT_ID,
        document_id: DOCUMENT_ID,
        retry_count: 0,
        max_retries: 3,
        created_at: "2026-08-28T00:00:00.000Z",
        started_at: null,
        completed_at: null,
        error: null,
        ...overrides,
      },
      meta: { request_id: "req-1" },
    },
    status: 200,
    requestId: "req-1",
  };
}

function jobListResponse(job: JobResource): SuccessfulApiResult<JobListResponse> {
  return {
    ok: true as const,
    data: {
      data: [job],
      meta: {
        request_id: "req-1",
        pagination: { limit: 1, next_cursor: null, has_more: false },
      },
    },
    status: 200,
    requestId: "req-1",
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("document import", () => {
  it("accepts a valid PDF selection", () => {
    const uploader = vi.fn<UploadDocument>();
    const client = createEmptyClient();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);

    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [pdfFile()] },
    });

    expect(screen.getByText(/Selected:/).textContent).toContain("guide.pdf");
    expect(uploadButton().disabled).toBe(false);
  });

  it.each([
    new File(["hello"], "notes.txt", { type: "text/plain" }),
    new File(["%PDF-1.7"], "C:\\Users\\local\\private.pdf", {
      type: "application/pdf",
    }),
  ])("explains why an unsafe selection is rejected", (file) => {
    const uploader = vi.fn<UploadDocument>();
    const client = createEmptyClient();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);

    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [file] },
    });

    expect(screen.getByRole("alert").textContent).toContain("Choose a PDF file");
    expect(uploadButton().disabled).toBe(true);
    expect(uploader).not.toHaveBeenCalled();
  });

  it("renders a safe upload error", async () => {
    const uploader = vi.fn<UploadDocument>(() =>
      Promise.reject(new Error("The local API could not be reached.")),
    );
    const client = createEmptyClient();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);
    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [pdfFile()] },
    });

    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "The local API could not be reached.",
    );
  });

  it("shows upload progress and the analysis status", async () => {
    let finish: ((value: DocumentOverview) => void) | undefined;
    const uploader = vi.fn<UploadDocument>(
      (_projectId, _file, onProgress) =>
        new Promise((resolve) => {
          finish = resolve;
          onProgress(45);
        }),
    );
    const client = createEmptyClient();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);
    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [pdfFile()] },
    });

    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));

    await waitFor(() => {
      const progress = screen.getByRole("progressbar", { name: "Upload progress" });
      if (!(progress instanceof HTMLProgressElement)) {
        throw new TypeError("Upload progress is not a progress element.");
      }
      expect(progress.value).toBe(45);
    });
    finish?.(overview);
    expect(await screen.findByText("Analysis: Analyzing")).toBeTruthy();
  });

  it("renders the thumbnail list from the document overview", async () => {
    const uploader = vi.fn<UploadDocument>(() => Promise.resolve(overview));
    const client = createEmptyClient();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);
    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [pdfFile()] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));

    await waitFor(() => {
      expect(screen.getAllByRole("img")).toHaveLength(2);
    });
    expect(screen.getByText("System Guide")).toBeTruthy();
    expect(screen.getByText("Page 1")).toBeTruthy();
    expect(screen.getByText("Page 2")).toBeTruthy();
  });

  it("accepts the persisted document and queued analysis response", async () => {
    vi.stubGlobal("XMLHttpRequest", SuccessfulXMLHttpRequest);
    const progress = vi.fn();

    const result = await uploadDocument(PROJECT_ID, pdfFile(), progress);

    expect(result).toEqual({
      originalFilename: "guide.pdf",
      sizeBytes: 612,
      title: null,
      pageCount: 1,
      analysisStatus: "QUEUED",
      thumbnails: [],
    });
    expect(progress).toHaveBeenLastCalledWith(100);
  });
});

describe("persisted workspace", () => {
  it("loads persisted document on mount", async () => {
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() =>
        Promise.resolve(jobListResponse(jobResponse().data.data as never)),
      ),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);

    expect(await screen.findByText("guide.pdf")).toBeTruthy();
    expect(await screen.findByText("Analysis: Queued")).toBeTruthy();
    expect(client.getProject).toHaveBeenCalledWith(PROJECT_ID, expect.any(Object));
    expect(client.getDocument).toHaveBeenCalledWith(DOCUMENT_ID, expect.any(Object));
    expect(client.listJobs).toHaveBeenCalledWith(
      { documentId: DOCUMENT_ID, jobType: "ANALYZE_DOCUMENT", limit: 1 },
      expect.any(Object),
    );
  });

  it("keeps persisted document visible after refresh", async () => {
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() =>
        Promise.resolve(jobListResponse(jobResponse().data.data as never)),
      ),
      getJob: vi.fn(),
    };
    const { unmount } = render(
      <DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />,
    );
    expect(await screen.findByText("guide.pdf")).toBeTruthy();
    expect(await screen.findByText("Analysis: Queued")).toBeTruthy();
    unmount();
    cleanup();
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    expect(await screen.findByText("guide.pdf")).toBeTruthy();
    expect(await screen.findByText("Analysis: Queued")).toBeTruthy();
  });

  it("shows no-document state when project has no active document", async () => {
    const client = {
      getProject: vi.fn(() =>
        Promise.resolve(createProjectWithDocument(null)),
      ),
      getDocument: vi.fn(),
      listJobs: vi.fn(),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    expect(await screen.findByText("No document yet")).toBeTruthy();
    expect(client.getDocument).not.toHaveBeenCalled();
  });

  it("shows missing document error and allows retry", async () => {
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() =>
        Promise.resolve({
          ok: false as const,
          error: { kind: "api" as const, code: "DOCUMENT_NOT_FOUND", message: "The requested document was not found.", details: {}, requestId: "req-1" },
          status: 404,
          requestId: "req-1",
        }),
      ),
      listJobs: vi.fn(),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    expect(await screen.findByText("Document could not be loaded")).toBeTruthy();
    expect(screen.getByText("The requested document was not found.")).toBeTruthy();
    // retry should re-fetch
    const before = client.getDocument.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry document load" }));
    await waitFor(() => expect(client.getDocument.mock.calls.length).toBeGreaterThan(before));
  });

  it("polls RUNNING every 2 seconds", async () => {
    vi.useFakeTimers();
    const running = jobResponse({ status: "RUNNING", progress: 0.42, current_stage: "ANALYZE_DOCUMENT" });
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(running.data.data as never))),
      getJob: vi.fn(() => Promise.resolve(running)),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("guide.pdf")).toBeTruthy();
    expect(client.getJob).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_999);
    });
    expect(client.getJob).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(client.getJob).toHaveBeenCalledTimes(1);
    expect(client.getJob).toHaveBeenCalledWith(JOB_ID, expect.any(Object));
  });

  it("polls QUEUED every 5 seconds", async () => {
    vi.useFakeTimers();
    const queued = jobResponse({ status: "QUEUED", progress: 0 });
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(queued.data.data as never))),
      getJob: vi.fn(() => Promise.resolve(queued)),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("guide.pdf")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_999);
    });
    expect(client.getJob).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(client.getJob).toHaveBeenCalledTimes(1);
  });

  it("stops polling at terminal status", async () => {
    vi.useFakeTimers();
    const completed = jobResponse({ status: "COMPLETED", progress: 1, current_stage: "COMPLETED" });
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(completed.data.data as never))),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("Analysis: Completed")).toBeTruthy();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(client.getJob).not.toHaveBeenCalled();
  });

  it("shows failed job details", async () => {
    const failed = jobResponse({
      status: "FAILED",
      progress: 0.5,
      current_stage: "ANALYZE_DOCUMENT",
      error: { code: "DOCUMENT_ANALYSIS_FAILED", message: "The document could not be analyzed safely." },
    });
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(failed.data.data as never))),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Failed")).toBeTruthy());
    expect(screen.getByText("DOCUMENT_ANALYSIS_FAILED")).toBeTruthy();
    expect(screen.getByText("The document could not be analyzed safely.")).toBeTruthy();
    expect(screen.getByRole("alert", { name: "Failure details" })).toBeTruthy();
  });

  it("handles API failure with retry", async () => {
    const client = {
      getProject: vi.fn(() =>
        Promise.resolve({
          ok: false as const,
          error: { kind: "api" as const, code: "INTERNAL_ERROR", message: "An internal server error occurred.", details: {}, requestId: "req-1" },
          status: 500,
          requestId: "req-1",
        }),
      ),
      getDocument: vi.fn(),
      listJobs: vi.fn(),
      getJob: vi.fn(),
    };
    render(<DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />);
    expect(await screen.findByText("Project could not be loaded")).toBeTruthy();
    expect(screen.getByText("An internal server error occurred.")).toBeTruthy();
    const before = client.getProject.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry project load" }));
    await waitFor(() => expect(client.getProject.mock.calls.length).toBeGreaterThan(before));
  });

  it("cleans up polling on unmount", async () => {
    vi.useFakeTimers();
    const running = jobResponse({ status: "RUNNING", progress: 0.3 });
    const signals: AbortSignal[] = [];
    const client = {
      getProject: vi.fn(() => Promise.resolve(createProjectWithDocument())),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(running.data.data as never))),
      getJob: vi.fn((_id: string, opts?: { signal?: AbortSignal }) => {
        if (opts?.signal) signals.push(opts.signal);
        return Promise.resolve(running);
      }),
    };
    const { unmount } = render(
      <DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("guide.pdf")).toBeTruthy();
    expect(signals.length).toBe(0);
    // first poll scheduled after 2s, unmount before it fires
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(client.getJob).not.toHaveBeenCalled();
  });

  it("isolates document state and polling when navigating to another project", async () => {
    vi.useFakeTimers();
    const running = jobResponse({ status: "RUNNING", progress: 0.3 });
    const pendingProject = new Promise<ReturnType<typeof createProjectWithDocument>>(
      () => undefined,
    );
    const client = {
      getProject: vi.fn((projectId: string) =>
        projectId === PROJECT_ID
          ? Promise.resolve(createProjectWithDocument())
          : pendingProject,
      ),
      getDocument: vi.fn(() => Promise.resolve(documentResponse())),
      listJobs: vi.fn(() => Promise.resolve(jobListResponse(running.data.data as never))),
      getJob: vi.fn(() => Promise.resolve(running)),
    };
    const { rerender } = render(
      <DocumentImport projectId={PROJECT_ID} client={client} uploader={vi.fn()} />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("guide.pdf")).toBeTruthy();

    rerender(
      <DocumentImport projectId={SECOND_PROJECT_ID} client={client} uploader={vi.fn()} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText("Loading project…")).toBeTruthy();
    expect(screen.queryByText("guide.pdf")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(client.getJob).not.toHaveBeenCalled();
  });

  it("preserves upload flow while showing persisted state", async () => {
    const client = createEmptyClient();
    const uploader = vi.fn<UploadDocument>(() => Promise.resolve(overview));
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} client={client} />);
    fireEvent.change(screen.getByLabelText("PDF file"), {
      target: { files: [pdfFile()] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload PDF" }));
    await waitFor(() => expect(screen.getByText("System Guide")).toBeTruthy());
    expect(uploader).toHaveBeenCalled();
  });
});

class SuccessfulXMLHttpRequest {
  response = {
    data: {
      document: {
        checksum_sha256: "0".repeat(64),
        id: "doc_00000000-0000-4000-8000-000000000001",
        original_file_id: "fil_00000000-0000-4000-8000-000000000001",
        original_filename: "guide.pdf",
        page_count: 1,
        project_id: PROJECT_ID,
        size_bytes: 612,
        status: "CREATED",
        title: null,
      },
      job: {
        id: "job_00000000-0000-4000-8000-000000000001",
        job_type: "ANALYZE_DOCUMENT",
        status: "QUEUED",
      },
    },
    meta: { request_id: "request-1" },
  };
  responseType = "";
  status = 202;
  timeout = 0;
  upload = { onprogress: null };
  onabort: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onload: (() => void) | null = null;
  ontimeout: (() => void) | null = null;

  open(): void {}

  send(): void {
    this.onload?.();
  }

  setRequestHeader(): void {}
}
