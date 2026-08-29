"use client";

import {
  CLIENT_HEADER,
  CLIENT_HEADER_VALUE,
  CLIENT_VERSION_HEADER,
  CLIENT_VERSION_HEADER_VALUE,
  DEFAULT_API_BASE_URL,
  REQUEST_ID_HEADER,
} from "@transloka/api-client";
import { useState } from "react";

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
const SAFE_PROJECT_ID =
  /^prj_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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

export function DocumentImport({
  projectId,
  uploader = uploadDocument,
}: Readonly<{
  projectId: string;
  uploader?: UploadDocument;
}>) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [overview, setOverview] = useState<DocumentOverview | null>(null);

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
      setOverview(await uploader(projectId, selectedFile, setProgress));
    } catch (error) {
      setUploadError(
        safeMessage(error instanceof Error ? error.message : null) ??
          "The PDF could not be uploaded safely.",
      );
    } finally {
      setUploading(false);
    }
  };

  const thumbnails = overview?.thumbnails.filter((item) => safeThumbnailUrl(item.url)) ?? [];

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

      {overview ? (
        <section
          aria-labelledby="document-overview-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-950" id="document-overview-heading">
                {overview.title ?? overview.originalFilename}
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                {fileSize(overview.sizeBytes)} · {overview.pageCount ?? "Page count pending"}
              </p>
            </div>
            <span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-semibold text-blue-800">
              Analysis: {statusLabel(overview.analysisStatus)}
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
    </div>
  );
}
