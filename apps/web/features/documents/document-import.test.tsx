// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DocumentImport,
  type DocumentOverview,
  type UploadDocument,
  uploadDocument,
} from "./document-import";

const PROJECT_ID = "prj_00000000-0000-4000-8000-000000000001";
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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("document import", () => {
  it("accepts a valid PDF selection", () => {
    const uploader = vi.fn<UploadDocument>();
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} />);

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
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} />);

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
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} />);
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
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} />);
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
    render(<DocumentImport projectId={PROJECT_ID} uploader={uploader} />);
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
