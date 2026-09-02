"use client";

import type { DocumentResource, ProjectResource } from "@transloka/api-client";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BackupPanel } from "../../src/features/backups";
import { ReviewEditor } from "../../src/features/editor";
import { ExportPanel } from "../../src/features/exports";
import {
  createLocalModelsClient,
  ModelsWorkspace,
  type LocalModel,
  type ModelsUiClient,
} from "../../src/features/models";
import { OCRReview } from "../../src/features/ocr";
import { ReconstructionWorkspace } from "../../src/features/reconstruction";
import { ReviewQueue } from "../../src/features/review-queue";
import { TranslationProgress, TranslationSettings } from "../../src/features/translation";
import { DocumentImport } from "../documents/document-import";
import {
  createWorkspaceClient,
  type OCRStatus,
  type WorkspaceClient,
  type WorkspacePage,
} from "./workspace-client";

type WorkspaceTab =
  | "import"
  | "ocr"
  | "translation"
  | "review"
  | "reconstruction"
  | "export"
  | "backup";

const TABS: readonly { id: WorkspaceTab; label: string; needsDocument: boolean }[] = [
  { id: "import", label: "Import", needsDocument: false },
  { id: "ocr", label: "OCR", needsDocument: true },
  { id: "translation", label: "Translation", needsDocument: true },
  { id: "review", label: "Review", needsDocument: true },
  { id: "reconstruction", label: "Reconstruction", needsDocument: true },
  { id: "export", label: "Export", needsDocument: true },
  { id: "backup", label: "Backup", needsDocument: false },
];

const ACTIVE_OCR_STATUSES = new Set(["CREATED", "QUEUED", "RUNNING", "RETRYING"]);
const defaultClient = createWorkspaceClient();
const defaultModelsClient = createLocalModelsClient();

function label(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function errorMessage(result: { error: { message: string } }): string {
  return result.error.message;
}

function PageSelector({
  onChange,
  pages,
  value,
}: Readonly<{
  onChange(pageId: string): void;
  pages: readonly WorkspacePage[];
  value: string | null;
}>) {
  if (pages.length === 0) return null;
  return (
    <label className="block text-sm font-medium text-slate-800" htmlFor="workspace-page">
      Source page
      <select
        className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal"
        id="workspace-page"
        onChange={(event) => onChange(event.target.value)}
        value={value ?? pages[0]?.id}
      >
        {pages.map((page) => (
          <option key={page.id} value={page.id}>
            Page {page.source_page_number} · {label(page.page_type)}
          </option>
        ))}
      </select>
    </label>
  );
}

function OCRWorkspace({
  client,
  document,
  onPageChange,
  page,
  pages,
}: Readonly<{
  client: WorkspaceClient;
  document: DocumentResource;
  onPageChange(pageId: string): void;
  page: WorkspacePage | null;
  pages: readonly WorkspacePage[];
}>) {
  const [status, setStatus] = useState<OCRStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const poll = async () => {
      const result = await client.getDocumentOcrStatus(document.id, {
        signal: controller.signal,
      });
      if (!active) return;
      if (!result.ok) {
        if (result.error.kind !== "aborted") setError(errorMessage(result));
        return;
      }
      setStatus(result.data.data);
      setError(null);
      if (ACTIVE_OCR_STATUSES.has(result.data.data.status)) {
        timer = setTimeout(() => void poll(), 2_000);
      }
    };
    void poll();
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [client, document.id, refresh]);

  const startOcr = async () => {
    setStarting(true);
    setError(null);
    const result = await client.startDocumentOcr(
      document.id,
      `ocr-ui-${document.id}-${Date.now().toString(36)}`,
    );
    setStarting(false);
    if (!result.ok) {
      setError(errorMessage(result));
      return;
    }
    setRefresh((value) => value + 1);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">OCR runtime</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              {status === null ? "Checking OCR…" : label(status.status)}
            </h2>
            {status !== null ? (
              <p className="mt-1 text-sm text-slate-600">
                {status.completed_pages} of {status.selected_pages} selected page(s) completed · {Math.round(status.progress * 100)}%
              </p>
            ) : null}
          </div>
          <button
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={starting || (status !== null && ACTIVE_OCR_STATUSES.has(status.status))}
            onClick={() => void startOcr()}
            type="button"
          >
            {starting ? "Starting…" : status?.status === "NOT_STARTED" ? "Start automatic OCR" : "Run OCR again"}
          </button>
        </div>
        {error !== null ? (
          <p className="mt-4 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
      </section>

      <PageSelector onChange={onPageChange} pages={pages} value={page?.id ?? null} />
      {page !== null ? (
        <OCRReview
          client={client}
          pageId={page.id}
          pageImageUrl={page.preview.render_url ?? page.preview.thumbnail_url ?? ""}
          pageNumber={page.source_page_number}
          pagePdfUrl={client.documentSourceUrl(document.id)}
        />
      ) : (
        <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          Pages appear here after document analysis completes.
        </p>
      )}
    </div>
  );
}

export function ProjectWorkspace({
  client = defaultClient,
  modelsClient = defaultModelsClient,
  projectId,
  pollIntervalMs = 3_000,
}: Readonly<{
  client?: WorkspaceClient;
  modelsClient?: ModelsUiClient;
  projectId: string;
  pollIntervalMs?: number;
}>) {
  const [tab, setTab] = useState<WorkspaceTab>("import");
  const [project, setProject] = useState<ProjectResource | null>(null);
  const [document, setDocument] = useState<DocumentResource | null>(null);
  const [pages, setPages] = useState<WorkspacePage[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [models, setModels] = useState<readonly LocalModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [translationRefreshToken, setTranslationRefreshToken] = useState(0);

  const loadModels = useCallback(async () => {
    const result = await modelsClient.listModels();
    if (result.ok) setModels(result.data);
  }, [modelsClient]);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const load = async () => {
      const projectResult = await client.getProject(projectId, { signal: controller.signal });
      if (!active) return;
      if (!projectResult.ok) {
        if (projectResult.error.kind !== "aborted") setError(errorMessage(projectResult));
        setLoading(false);
        return;
      }
      const nextProject = projectResult.data.data;
      setProject(nextProject);
      setError(null);
      if (nextProject.active_document_id === null) {
        setDocument(null);
        setPages([]);
        setSelectedPageId(null);
      } else {
        const [documentResult, pagesResult] = await Promise.all([
          client.getDocument(nextProject.active_document_id, { signal: controller.signal }),
          client.listDocumentPages(nextProject.active_document_id, { signal: controller.signal }),
        ]);
        if (!active) return;
        if (!documentResult.ok) {
          if (documentResult.error.kind !== "aborted") setError(errorMessage(documentResult));
        } else {
          setDocument(documentResult.data.data);
        }
        if (!pagesResult.ok) {
          if (pagesResult.error.kind !== "aborted") setError(errorMessage(pagesResult));
        } else {
          setPages(pagesResult.data.data);
          setSelectedPageId((current) =>
            pagesResult.data.data.some((page) => page.id === current)
              ? current
              : (pagesResult.data.data[0]?.id ?? null),
          );
        }
      }
      setLoading(false);
      timer = setTimeout(() => setRefresh((value) => value + 1), pollIntervalMs);
    };
    void load();
    return () => {
      active = false;
      controller.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [client, pollIntervalMs, projectId, refresh]);

  const selectedPage = useMemo(
    () => pages.find((page) => page.id === selectedPageId) ?? null,
    [pages, selectedPageId],
  );

  const selectReviewSegment = useCallback((segmentId: string, pageId: string) => {
    setSelectedPageId(pageId);
    setSelectedSegmentId(segmentId);
  }, []);

  const documentRequired = document === null ? (
    <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
      Import a PDF and wait for analysis before opening this workflow step.
    </p>
  ) : null;

  return (
    <div className="mt-8 space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Project state</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">
              {project?.name ?? (loading ? "Loading project…" : "Project unavailable")}
            </h2>
            {project !== null ? (
              <p className="mt-1 text-sm text-slate-600">
                {label(project.status)} · {Math.round(project.progress * 100)}% · {document?.original_filename ?? "No active PDF"}
              </p>
            ) : null}
          </div>
          <button
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-50"
            onClick={() => setRefresh((value) => value + 1)}
            type="button"
          >
            Refresh project
          </button>
        </div>
        {error !== null ? (
          <p className="mt-4 text-sm text-red-700" role="alert">
            {error}
          </p>
        ) : null}
      </section>

      <nav aria-label="Project workflow" className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            aria-current={tab === item.id ? "page" : undefined}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
              tab === item.id
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            } disabled:cursor-not-allowed disabled:opacity-45`}
            disabled={item.needsDocument && document === null}
            key={item.id}
            onClick={() => setTab(item.id)}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "import" ? <DocumentImport projectId={projectId} /> : null}
      {tab === "ocr" && document !== null ? (
        <OCRWorkspace
          client={client}
          document={document}
          onPageChange={setSelectedPageId}
          page={selectedPage}
          pages={pages}
        />
      ) : null}
      {tab === "translation" && document !== null ? (
        <div className="space-y-6">
          <ModelsWorkspace
            client={modelsClient}
            onModelSelected={(model) => {
              setModels((current) =>
                current.map((candidate) => ({
                  ...candidate,
                  is_selected_translation: candidate.id === model.id,
                })),
              );
              void loadModels();
            }}
          />
          <TranslationSettings
            client={client}
            models={models}
            onStarted={() => setTranslationRefreshToken((value) => value + 1)}
            projectId={projectId}
          />
          <TranslationProgress
            client={client}
            projectId={projectId}
            refreshToken={translationRefreshToken}
          />
        </div>
      ) : null}
      {tab === "review" && document !== null ? (
        <div className="space-y-6">
          <PageSelector onChange={setSelectedPageId} pages={pages} value={selectedPageId} />
          <ReviewQueue client={client} onSelectSegment={selectReviewSegment} projectId={projectId} />
          {selectedPage !== null ? (
            <ReviewEditor
              client={client}
              initialSegmentId={selectedSegmentId}
              pageId={selectedPage.id}
              pdfUrl={client.documentSourceUrl(document.id)}
            />
          ) : (
            <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              Pages appear here after analysis completes.
            </p>
          )}
        </div>
      ) : null}
      {tab === "reconstruction" && document !== null ? (
        <ReconstructionWorkspace
          client={client}
          {...(selectedPage === null ? {} : { pageId: selectedPage.id })}
          projectId={projectId}
        />
      ) : null}
      {tab === "export" && document !== null ? (
        <ExportPanel client={client} projectId={projectId} />
      ) : null}
      {tab === "backup" ? <BackupPanel client={client} /> : null}
      {documentRequired !== null && tab !== "import" && tab !== "backup" ? documentRequired : null}
    </div>
  );
}
