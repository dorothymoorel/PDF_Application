"use client";

import {
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  createTransLokaClient,
  DEFAULT_API_BASE_URL,
  REQUEST_ID_HEADER,
  type DocumentResource,
  type JobResource,
} from "@transloka/api-client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type DocumentThumbnail = {
  id: string;
  pageNumber: number;
  url: string;
};

export type DocumentOverview = {
  originalFilename: string;
  sizeBytes: number;
  title: string | null;
  pageCount: number | null;
  analysisStatus: string;
  thumbnails: readonly DocumentThumbnail[];
};

export type UploadDocument = (
  projectId: string,
  file: File,
  onProgress: (progress: number) => void,
) => Promise<DocumentOverview>;

const PDF_MIME_TYPE = "application/pdf";
const JOB_STATUSES = new Set([
  "QUEUED",
  "RUNNING",
  "RETRYING",
  "CANCELLATION_REQUESTED",
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);
const TERMINAL_JOB_STATUSES = new Set([
  "COMPLETED",
  "COMPLETED_WITH_WARNINGS",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "STALE",
]);
const SAFE_PROJECT_ID =
  /^prj_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SAFE_DOCUMENT_ID =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function validPdf(file: File): boolean {
  return (
    !/[\\/:]/u.test(file.name) &&
    file.name.toLowerCase().endsWith(".pdf") &&
    (file.type === "" || file.type.toLowerCase() === PDF_MIME_TYPE)
  );
}

function safeMessage(value: unknown): string | null {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > 300 ||
    /[\u0000-\u001f\u007f\\]/u.test(value) ||
    value.includes("/") ||
    /(?:[a-z]:\/|file:\/\/)/iu.test(value)
  ) {
    return null;
  }
  return value;
}

function uploadErrorMessage(xhr: XMLHttpRequest): string {
  const payload: unknown = xhr.response;
  if (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "object" &&
    payload.error !== null &&
    "message" in payload.error
  ) {
    const message = safeMessage(payload.error.message);
    if (message !== null) {
      return message;
    }
  }
  return "The local API rejected the PDF. Check the file and try again.";
}

function isDocumentImport(value: unknown): value is {
  data: {
    document: {
      original_filename: string;
      page_count: number;
      size_bytes: number;
      title: string | null;
    };
    job: { status: string };
  };
} {
  if (typeof value !== "object" || value === null || !("data" in value)) {
    return false;
  }
  const data = value.data;
  if (
    typeof data !== "object" ||
    data === null ||
    !("document" in data) ||
    !("job" in data)
  ) {
    return false;
  }
  const document = data.document;
  const job = data.job;
  return (
    typeof document === "object" &&
    document !== null &&
    "original_filename" in document &&
    typeof document.original_filename === "string" &&
    document.original_filename.length > 0 &&
    "page_count" in document &&
    typeof document.page_count === "number" &&
    Number.isSafeInteger(document.page_count) &&
    document.page_count >= 0 &&
    "size_bytes" in document &&
    typeof document.size_bytes === "number" &&
    Number.isSafeInteger(document.size_bytes) &&
    document.size_bytes >= 0 &&
    "title" in document &&
    (document.title === null || typeof document.title === "string") &&
    typeof job === "object" &&
    job !== null &&
    "status" in job &&
    typeof job.status === "string" &&
    JOB_STATUSES.has(job.status)
  );
}

export const uploadDocument: UploadDocument = (projectId, file, onProgress) => {
  if (!SAFE_PROJECT_ID.test(projectId)) {
    return Promise.reject(new Error("The project identifier is invalid."));
  }

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(
      "POST",
      `${DEFAULT_API_BASE_URL}/api/v1/projects/${encodeURIComponent(projectId)}/documents/import`,
    );
    request.responseType = "json";
    request.timeout = 60_000;
    request.setRequestHeader(CLIENT_HEADER, CLIENT_HEADER_VALUE);
    request.setRequestHeader(CLIENT_VERSION_HEADER, CLIENT_VERSION_HEADER_VALUE);
    request.setRequestHeader(REQUEST_ID_HEADER, globalThis.crypto.randomUUID());
    request.setRequestHeader("Idempotency-Key", globalThis.crypto.randomUUID());
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    request.onerror = () => reject(new Error("The local API could not be reached."));
    request.ontimeout = () => reject(new Error("The upload timed out."));
    request.onabort = () => reject(new Error("The upload was cancelled."));
    request.onload = () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(uploadErrorMessage(request)));
        return;
      }
      if (!isDocumentImport(request.response)) {
        reject(new Error("The local API returned an invalid upload response."));
        return;
      }
      onProgress(100);
      resolve({
        originalFilename: request.response.data.document.original_filename,
        sizeBytes: request.response.data.document.size_bytes,
        title: request.response.data.document.title,
        pageCount: request.response.data.document.page_count,
        analysisStatus: request.response.data.job.status,
        thumbnails: [],
      });
    };

    const body = new FormData();
    body.set("file", file, file.name);
    body.set("set_as_active", "true");
    request.send(body);
  });
};

function statusLabel(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function fileSize(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function safeThumbnailUrl(value: string): boolean {
  return /^\/api\/v1\/pages\/[^/]+\/thumbnail$/u.test(value);
}

function isTerminalStatus(status: string): boolean {
  return TERMINAL_JOB_STATUSES.has(status);
}

function pollIntervalFor(status: string): number | null {
  if (isTerminalStatus(status)) {
    return null;
  }
  return status === "RUNNING" ? 2_000 : 5_000;
}

type WorkspaceClient = Pick<
  ReturnType<typeof createTransLokaClient>,
  "getDocument" | "getJob" | "getProject" | "listJobs"
>;

const defaultClient = createTransLokaClient();

export function DocumentImport({
  projectId,
  uploader = uploadDocument,
  client,
}: Readonly<{
  projectId: string;
  uploader?: UploadDocument;
  client?: WorkspaceClient;
}>) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [overview, setOverview] = useState<DocumentOverview | null>(null);
  const [persistedDocument, setPersistedDocument] = useState<DocumentResource | null>(null);
  const [persistedJob, setPersistedJob] = useState<JobResource | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [jobLoading, setJobLoading] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [projectReload, setProjectReload] = useState(0);
  const [documentReload, setDocumentReload] = useState(0);
  const [jobReload, setJobReload] = useState(0);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const activeClient = client ?? defaultClient;
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const retryProject = useCallback(() => {
    setProjectReload((value) => value + 1);
  }, []);

  const retryDocument = useCallback(() => {
    setDocumentReload((value) => value + 1);
  }, []);

  const retryJob = useCallback(() => {
    setJobReload((value) => value + 1);
  }, []);

  useEffect(() => {
    setActiveDocumentId(null);
    setPersistedDocument(null);
    setPersistedJob(null);
    setDocumentError(null);
    setJobError(null);
    setDocumentLoading(false);
    setJobLoading(false);
    setOverview(null);
  }, [projectId]);

  // Load project
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    if (!SAFE_PROJECT_ID.test(projectId)) {
      setProjectError("The project identifier is invalid.");
      setProjectLoading(false);
      return () => {
        cancelled = true;
        controller.abort();
      };
    }
    setProjectLoading(true);
    setProjectError(null);
    activeClient
      .getProject(projectId, { signal: controller.signal })
      .then((result) => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        if (!result.ok) {
          if (result.error.kind === "aborted") {
            return;
          }
          setProjectError(result.error.message);
          setActiveDocumentId(null);
          setPersistedDocument(null);
          setPersistedJob(null);
        } else {
          setProjectError(null);
          const activeId = result.data.data.active_document_id;
          if (activeId !== null && !SAFE_DOCUMENT_ID.test(activeId)) {
            setProjectError("The linked document identifier is invalid.");
            setPersistedDocument(null);
            setPersistedJob(null);
          } else if (activeId === null) {
            setPersistedDocument(null);
            setPersistedJob(null);
            setDocumentError(null);
            setJobError(null);
          } else {
            setDocumentError(null);
            setJobError(null);
          }
          setActiveDocumentId(activeId);
        }
        setProjectLoading(false);
      })
      .catch(() => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        setProjectError("The project could not be loaded.");
        setActiveDocumentId(null);
        setPersistedDocument(null);
        setPersistedJob(null);
        setProjectLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [projectId, activeClient, projectReload]);

  // Load persisted document when activeDocumentId changes
  useEffect(() => {
    if (projectLoading) {
      return;
    }
    if (projectError !== null) {
      setDocumentLoading(false);
      return;
    }
    if (activeDocumentId === null) {
      setPersistedDocument(null);
      setDocumentLoading(false);
      setDocumentError(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setDocumentLoading(true);
    setDocumentError(null);
    activeClient
      .getDocument(activeDocumentId, { signal: controller.signal })
      .then((result) => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        if (!result.ok) {
          if (result.error.kind === "aborted") {
            return;
          }
          setDocumentError(result.error.message);
          setPersistedDocument(null);
          setPersistedJob(null);
        } else {
          setPersistedDocument(result.data.data);
          setDocumentError(null);
        }
        setDocumentLoading(false);
      })
      .catch(() => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        setDocumentError("The document could not be loaded.");
        setDocumentLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeDocumentId, projectLoading, projectError, activeClient, documentReload]);

  // Load current ANALYZE_DOCUMENT job for the persisted document
  useEffect(() => {
    if (documentLoading) {
      return;
    }
    if (documentError !== null) {
      setJobLoading(false);
      return;
    }
    if (persistedDocument === null) {
      setPersistedJob(null);
      setJobLoading(false);
      setJobError(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setJobLoading(true);
    setJobError(null);
    activeClient
      .listJobs(
        { documentId: persistedDocument.id, jobType: "ANALYZE_DOCUMENT", limit: 1 },
        { signal: controller.signal },
      )
      .then((result) => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        if (!result.ok) {
          if (result.error.kind === "aborted") {
            return;
          }
          setJobError(result.error.message);
          setPersistedJob(null);
        } else {
          const jobs = result.data.data as readonly JobResource[];
          if (jobs.length === 0) {
            setPersistedJob(null);
          } else {
            setPersistedJob(jobs[0] as JobResource);
          }
          setJobError(null);
        }
        setJobLoading(false);
      })
      .catch(() => {
        if (cancelled || !mountedRef.current) {
          return;
        }
        setJobError("The analysis status could not be loaded.");
        setJobLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [persistedDocument, documentLoading, documentError, activeClient, jobReload]);

  // Poll running analysis job
  useEffect(() => {
    if (persistedJob === null) {
      return;
    }
    if (isTerminalStatus(persistedJob.status)) {
      return;
    }
    const interval = pollIntervalFor(persistedJob.status);
    if (interval === null) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      activeClient
        .getJob(persistedJob.id, { signal: controller.signal })
        .then((result) => {
          if (controller.signal.aborted || !mountedRef.current) {
            return;
          }
          if (!result.ok) {
            if (result.error.kind === "aborted") {
              return;
            }
            setJobError(result.error.message);
            return;
          }
          const nextJob = result.data.data;
          setPersistedJob(nextJob);
          setJobError(null);
        })
        .catch(() => {
          if (controller.signal.aborted || !mountedRef.current) {
            return;
          }
          setJobError("The analysis status could not be updated.");
        });
    }, interval);
    return () => {
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [persistedJob, activeClient]);

  const selectFile = (file: File | undefined) => {
    setOverview(null);
    setUploadError(null);
    setProgress(0);
    if (file === undefined) {
      setSelectedFile(null);
      setSelectionError(null);
      return;
    }
    if (!validPdf(file)) {
      setSelectedFile(null);
      setSelectionError("Choose a PDF file. Other file types are not supported.");
      return;
    }
    setSelectedFile(file);
    setSelectionError(null);
  };

  const startUpload = async () => {
    if (selectedFile === null || uploading) {
      return;
    }
    setUploading(true);
    setUploadError(null);
    setProgress(0);
    try {
      const result = await uploader(projectId, selectedFile, setProgress);
      if (!mountedRef.current) {
        return;
      }
      setOverview(result);
      setProjectReload((value) => value + 1);
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      setUploadError(
        safeMessage(error instanceof Error ? error.message : null) ??
          "The PDF could not be uploaded safely.",
      );
    } finally {
      if (mountedRef.current) {
        setUploading(false);
      }
    }
  };

  const persistedOverview: DocumentOverview | null = useMemo(() => {
    if (persistedDocument === null) {
      return null;
    }
    return {
      originalFilename: persistedDocument.original_filename,
      sizeBytes: persistedDocument.size_bytes,
      title: persistedDocument.title,
      pageCount: persistedDocument.page_count,
      analysisStatus: persistedJob?.status ?? persistedDocument.status,
      thumbnails: [],
    };
  }, [persistedDocument, persistedJob]);

  const displayedOverview = persistedOverview ?? overview;
  const thumbnails = displayedOverview?.thumbnails.filter((item) => safeThumbnailUrl(item.url)) ?? [];

  return (
    <div className="mt-8 space-y-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-950">Select source PDF</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Choose one English PDF. The browser sends the file directly to the local API.
        </p>
        <label className="mt-6 block text-sm font-medium text-slate-800" htmlFor="pdf-file">
          PDF file
        </label>
        <input
          accept=".pdf,application/pdf"
          aria-describedby={selectionError ? "pdf-file-error" : "pdf-file-help"}
          aria-invalid={selectionError ? "true" : "false"}
          className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800 file:mr-4 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-2 file:font-medium file:text-white"
          disabled={uploading}
          id="pdf-file"
          onChange={(event) => selectFile(event.target.files?.[0])}
          type="file"
        />
        <p className="mt-2 text-xs text-slate-500" id="pdf-file-help">
          Only the filename is displayed; local filesystem paths are never shown.
        </p>
        {selectionError ? (
          <p className="mt-2 text-sm text-red-700" id="pdf-file-error" role="alert">
            {selectionError}
          </p>
        ) : null}
        {selectedFile ? (
          <p className="mt-4 text-sm text-slate-700">
            Selected: <strong>{selectedFile.name}</strong> ({fileSize(selectedFile.size)})
          </p>
        ) : null}
        <button
          className="mt-5 rounded-lg bg-slate-900 px-4 py-2.5 font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={selectedFile === null || uploading}
          onClick={() => void startUpload()}
          type="button"
        >
          {uploading ? "Uploading…" : "Upload PDF"}
        </button>
        {uploading || progress > 0 ? (
          <div className="mt-5" role="status">
            <div className="flex justify-between text-sm text-slate-600">
              <span>Upload progress</span>
              <span>{progress}%</span>
            </div>
            <progress
              aria-label="Upload progress"
              className="mt-2 h-2 w-full accent-slate-900"
              max={100}
              value={progress}
            >
              {progress}%
            </progress>
          </div>
        ) : null}
        {uploadError ? (
          <p className="mt-4 text-sm text-red-700" role="alert">
            {uploadError}
          </p>
        ) : null}
      </section>

      {projectLoading ? (
        <section
          aria-busy="true"
          aria-labelledby="project-state-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2 className="text-lg font-semibold text-slate-950" id="project-state-heading">
            Project workspace
          </h2>
          <p className="mt-3 text-sm text-slate-600" role="status">
            Loading project…
          </p>
        </section>
      ) : null}

      {projectError ? (
        <section
          aria-labelledby="project-error-heading"
          className="rounded-2xl border border-red-200 bg-red-50 p-6 shadow-sm"
          role="alert"
        >
          <h2 className="text-lg font-semibold text-red-900" id="project-error-heading">
            Project could not be loaded
          </h2>
          <p className="mt-2 text-sm text-red-800">{projectError}</p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={retryProject}
            type="button"
          >
            Retry project load
          </button>
        </section>
      ) : null}

      {!projectLoading && !projectError && activeDocumentId === null && !documentLoading ? (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">No document yet</h2>
          <p className="mt-2 text-sm text-slate-600">
            This project has no active document. Upload a PDF to create the persisted document and
            start analysis.
          </p>
        </section>
      ) : null}

      {documentLoading ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" role="status">
          <p className="text-sm text-slate-600">Loading document…</p>
        </section>
      ) : null}

      {documentError ? (
        <section
          aria-labelledby="document-error-heading"
          className="rounded-2xl border border-red-200 bg-red-50 p-6 shadow-sm"
          role="alert"
        >
          <h2 className="text-lg font-semibold text-red-900" id="document-error-heading">
            Document could not be loaded
          </h2>
          <p className="mt-2 text-sm text-red-800">{documentError}</p>
          <p className="mt-2 text-sm text-red-700">
            The document may have been deleted. You can upload a new PDF.
          </p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={retryDocument}
            type="button"
          >
            Retry document load
          </button>
        </section>
      ) : null}

      {displayedOverview ? (
        <section
          aria-labelledby="document-overview-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-950" id="document-overview-heading">
                {displayedOverview.title ?? displayedOverview.originalFilename}
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                {fileSize(displayedOverview.sizeBytes)} ·{" "}
                {displayedOverview.pageCount ?? "Page count pending"}
              </p>
            </div>
            <span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-semibold text-blue-800">
              Analysis: {statusLabel(displayedOverview.analysisStatus)}
            </span>
          </div>

          <h3 className="mt-8 text-lg font-semibold text-slate-900">Page thumbnails</h3>
          {thumbnails.length > 0 ? (
            <ul
              aria-label="Page thumbnails"
              className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
            >
              {thumbnails.map((thumbnail) => (
                <li className="rounded-lg border border-slate-200 p-2" key={thumbnail.id}>
                  <img
                    alt={`Page ${thumbnail.pageNumber} thumbnail`}
                    className="aspect-[3/4] w-full rounded bg-slate-100 object-contain"
                    src={thumbnail.url}
                  />
                  <p className="mt-2 text-center text-xs text-slate-600">
                    Page {thumbnail.pageNumber}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-slate-600">
              Thumbnails will appear after local analysis completes.
            </p>
          )}
        </section>
      ) : null}

      {persistedDocument && jobLoading ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" role="status">
          <p className="text-sm text-slate-600">Loading analysis status…</p>
        </section>
      ) : null}

      {jobError ? (
        <section
          aria-labelledby="job-error-heading"
          className="rounded-2xl border border-red-200 bg-red-50 p-6 shadow-sm"
          role="alert"
        >
          <h2 className="text-lg font-semibold text-red-900" id="job-error-heading">
            Analysis status could not be loaded
          </h2>
          <p className="mt-2 text-sm text-red-800">{jobError}</p>
          <button
            className="mt-4 rounded-lg border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
            onClick={retryJob}
            type="button"
          >
            Retry analysis status
          </button>
        </section>
      ) : null}

      {persistedJob ? (
        <section
          aria-labelledby="analysis-job-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-950" id="analysis-job-heading">
                Document analysis
              </h2>
              <p className="mt-1 text-sm text-slate-500">{persistedJob.job_type.replaceAll("_", " ")}</p>
            </div>
            <span
              aria-live="polite"
              className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-800"
              role="status"
            >
              {statusLabel(persistedJob.status)}
            </span>
          </div>

          <div className="mt-5">
            <div className="flex justify-between gap-4 text-sm font-medium text-slate-700">
              <span>{statusLabel(persistedJob.current_stage ?? persistedJob.status)}</span>
              <span>{Math.round(persistedJob.progress * 100)}%</span>
            </div>
            <progress
              aria-label="Analysis progress"
              className="mt-2 h-3 w-full accent-slate-900"
              max={100}
              value={Math.round(persistedJob.progress * 100)}
            >
              {Math.round(persistedJob.progress * 100)}%
            </progress>
          </div>

          {!isTerminalStatus(persistedJob.status) ? (
            <p className="mt-3 text-sm text-slate-600" role="status">
              Analysis is in progress. Status updates automatically.
            </p>
          ) : null}

          {persistedJob.error !== null ? (
            <div
              aria-label="Failure details"
              className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4"
              role="alert"
            >
              <p className="font-semibold text-red-900">Analysis could not complete</p>
              <p className="mt-1 font-mono text-xs text-red-700">{persistedJob.error.code}</p>
              <p className="mt-2 text-sm leading-6 text-red-800">{persistedJob.error.message}</p>
            </div>
          ) : null}
        </section>
      ) : null}

      {persistedDocument && !jobLoading && !jobError && persistedJob === null ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-600">No analysis job found for this document.</p>
        </section>
      ) : null}
    </div>
  );
}
