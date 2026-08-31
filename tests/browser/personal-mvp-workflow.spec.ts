import { expect, test, type Route } from "@playwright/test";

const PROJECT_ID = "prj_00000000-0000-4000-8000-000000000001";
const DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000002";
const PAGE_ID = "pag_00000000-0000-4000-8000-000000000003";
const BLOCK_ID = "blk_00000000-0000-4000-8000-000000000004";
const SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000005";
const MODEL_ID = "mdl_00000000-0000-4000-8000-000000000006";
const JOB_ID = "job_00000000-0000-4000-8000-000000000007";
const EXPORT_ID = "exp_00000000-0000-4000-8000-000000000008";
const BACKUP_ID = "bkp_00000000-0000-4000-8000-000000000009";
const PRE_RESTORE_BACKUP_ID = "bkp_00000000-0000-4000-8000-000000000010";
const CHECKSUM = "a".repeat(64);

const META = { request_id: "req_browser_e2e" };
const CORS_HEADERS = {
  "access-control-allow-headers": "Content-Type, Idempotency-Key, X-Request-ID, X-TransLoka-Client, X-TransLoka-Client-Version",
  "access-control-allow-methods": "GET, POST, PATCH, OPTIONS",
  "access-control-allow-origin": "http://127.0.0.1:3100",
  "access-control-expose-headers": "X-Request-ID",
  "x-request-id": META.request_id,
};

function project(activeDocumentId: string | null) {
  return {
    active_document_id: activeDocumentId,
    created_at: "2026-08-31T00:00:00.000Z",
    description: "Browser acceptance workflow",
    document_type: "TECHNICAL_BOOK",
    id: PROJECT_ID,
    name: "Release Trial",
    progress: activeDocumentId === null ? 0 : 1,
    reconstruction_mode: "HYBRID",
    settings: {},
    source_language: "en",
    status: activeDocumentId === null ? "CREATED" : "READY_FOR_EXPORT",
    target_language: "id",
    translation_style: "PROFESSIONAL",
    updated_at: "2026-08-31T00:05:00.000Z",
  };
}

const document = {
  checksum_sha256: CHECKSUM,
  id: DOCUMENT_ID,
  original_file_id: "fil_00000000-0000-4000-8000-000000000011",
  original_filename: "release-trial.pdf",
  page_count: 1,
  project_id: PROJECT_ID,
  size_bytes: 612,
  status: "READY_FOR_EXPORT",
  title: "Release Trial PDF",
};

const pageResource = {
  column_count: 1,
  confidence: { native_extraction: 1, ocr: 0.99, structure: 0.98 },
  document_id: DOCUMENT_ID,
  height_points: 792,
  id: PAGE_ID,
  logical_page_number: "1",
  page_classification: "SINGLE_COLUMN",
  page_type: "DIGITAL",
  preview: { render_url: null, thumbnail_url: null },
  reading_direction: "LTR",
  rotation_degrees: 0,
  source_page_number: 1,
  status: "STRUCTURED",
  width_points: 612,
};

const segment = {
  block_id: BLOCK_ID,
  confidence: { overall: 0.91 },
  current_revision: 1,
  final_text: null,
  global_order: 0,
  id: SEGMENT_ID,
  is_locked: false,
  machine_translation: "Dokumen uji rilis.",
  normalized_source_text: "Release trial document.",
  raw_ocr_text: "Release trial document.",
  resolved_source_text: "Release trial document.",
  review_status: "REVIEW_REQUIRED",
  reviewed_translation: null,
  section_id: null,
  segment_order: 0,
  source_language: "eng",
  source_text: "Release trial document.",
  status: "NEEDS_REVIEW",
  target_language: "ind",
  warning_count: 0,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    headers: { ...CORS_HEADERS, "content-type": "application/json" },
    status,
  });
}

test("completes the persisted Personal MVP browser workflow", async ({ page }) => {
  let created = false;
  let imported = false;

  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname;

    if (method === "OPTIONS") {
      await route.fulfill({ headers: CORS_HEADERS, status: 204 });
      return;
    }

    if (path === "/api/v1/projects" && method === "POST") {
      created = true;
      await fulfillJson(route, { data: project(null), meta: META }, 201);
      return;
    }
    if (path === "/api/v1/projects" && method === "GET") {
      await fulfillJson(route, {
        data: created ? [project(imported ? DOCUMENT_ID : null)] : [],
        meta: { ...META, pagination: { has_more: false, limit: 100, offset: 0, total: created ? 1 : 0 } },
      });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}` && method === "GET") {
      await fulfillJson(route, { data: project(imported ? DOCUMENT_ID : null), meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/documents/import` && method === "POST") {
      imported = true;
      await fulfillJson(route, {
        data: {
          document,
          job: {
            completed_at: "2026-08-31T00:06:00.000Z",
            created_at: "2026-08-31T00:05:00.000Z",
            current_stage: "COMPLETED",
            document_id: DOCUMENT_ID,
            error: null,
            id: JOB_ID,
            job_type: "ANALYZE_DOCUMENT",
            max_retries: 3,
            progress: 1,
            project_id: PROJECT_ID,
            retry_count: 0,
            started_at: "2026-08-31T00:05:10.000Z",
            status: "COMPLETED",
          },
        },
        meta: META,
      }, 201);
      return;
    }
    if (path === `/api/v1/documents/${DOCUMENT_ID}` && method === "GET") {
      await fulfillJson(route, { data: document, meta: META });
      return;
    }
    if (path === `/api/v1/documents/${DOCUMENT_ID}/pages` && method === "GET") {
      await fulfillJson(route, { data: [pageResource], meta: META });
      return;
    }
    if (path === "/api/v1/jobs" && method === "GET") {
      await fulfillJson(route, {
        data: [{
          completed_at: "2026-08-31T00:06:00.000Z",
          created_at: "2026-08-31T00:05:00.000Z",
          current_stage: "COMPLETED",
          document_id: DOCUMENT_ID,
          error: null,
          id: JOB_ID,
          job_type: "ANALYZE_DOCUMENT",
          max_retries: 3,
          progress: 1,
          project_id: PROJECT_ID,
          retry_count: 0,
          started_at: "2026-08-31T00:05:10.000Z",
          status: "COMPLETED",
        }],
        meta: { ...META, pagination: { has_more: false, limit: 1, next_cursor: null } },
      });
      return;
    }
    if (path === "/api/v1/models/ollama/health") {
      await fulfillJson(route, { data: { base_url: "http://127.0.0.1:11434", status: "AVAILABLE", version: "test" }, meta: META });
      return;
    }
    if (path === "/api/v1/models" || path === "/api/v1/models/refresh") {
      await fulfillJson(route, { data: [{
        disk_size_bytes: 1_000_000,
        id: MODEL_ID,
        is_installed: true,
        is_selected_translation: true,
        is_selected_validation: false,
        license_status: "APPROVED",
        model_family: "qwen",
        ollama_model_name: "qwen3:1.7b",
        parameter_class: "1.7b",
        quantization: "Q4_K_M",
      }], meta: META });
      return;
    }
    if (path === `/api/v1/documents/${DOCUMENT_ID}/ocr/status`) {
      await fulfillJson(route, { data: { active_job_id: null, completed_pages: 1, current_stage: "COMPLETED", failed_pages: 0, progress: 1, selected_pages: 1, status: "COMPLETED" }, meta: META });
      return;
    }
    if (path === `/api/v1/documents/${DOCUMENT_ID}/ocr/start`) {
      await fulfillJson(route, { data: { job_id: JOB_ID, status: "QUEUED" }, meta: META }, 202);
      return;
    }
    if (path === `/api/v1/pages/${PAGE_ID}/ocr`) {
      await fulfillJson(route, { data: {
        page_id: PAGE_ID,
        ocr_confidence: 0.99,
        raw_text: "Release trial document.",
        resolved_source_text: "Release trial document.",
        segments: [segment],
        warnings: [],
      }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/translation-readiness`) {
      await fulfillJson(route, { data: { blocking_issues: [], estimated_batches: 1, ready: true, segment_count: 1, warnings: [] }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/translation/start`) {
      await fulfillJson(route, { data: { job_id: JOB_ID, status: "QUEUED" }, meta: META }, 202);
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/translation/status`) {
      await fulfillJson(route, { data: { active_job_id: null, completed_segments: 1, current_batch: 1, failed_segments: 0, progress: 1, review_required_segments: 1, status: "COMPLETED", total_batches: 1, total_segments: 1 }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/review-queue`) {
      await fulfillJson(route, { data: [{
        page_id: PAGE_ID,
        segment,
        source_context: { heading: null, next_segment: null, previous_segment: null },
        warnings: [],
      }], meta: { ...META, pagination: { has_more: false, limit: 20, next_cursor: null } } });
      return;
    }
    if (path === `/api/v1/pages/${PAGE_ID}/editor-view`) {
      await fulfillJson(route, { data: {
        blocks: [{
          block_type: "PARAGRAPH",
          confidence: 0.98,
          global_reading_order: 0,
          id: BLOCK_ID,
          normalized_source_text: "Release trial document.",
          page_id: PAGE_ID,
          page_reading_order: 0,
          parent_block_id: null,
          section_id: null,
          semantic_role: "BODY_TEXT",
          source_geometry: { coordinate_system: "TOP_LEFT", height: 40, width: 400, x: 50, y: 80 },
          source_text: "Release trial document.",
          status: "STRUCTURED",
          target_geometry: null,
        }],
        page: pageResource,
        segments: [segment],
        warnings: [],
      }, meta: META });
      return;
    }
    if (path === `/api/v1/segments/${SEGMENT_ID}/translation` && method === "PATCH") {
      await fulfillJson(route, { data: { ...segment, current_revision: 2, review_status: "APPROVED", reviewed_translation: "Dokumen uji rilis." }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/reconstruction-readiness`) {
      await fulfillJson(route, { data: { available_modes: ["OVERLAY", "HYBRID"], blocking_issues: [], ready: true, warnings: [] }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/reconstruction/status`) {
      await fulfillJson(route, { data: { active_job_id: null, completed_pages: 1, critical_warning_count: 0, generated_target_pages: 1, progress: 1, status: "COMPLETED", total_source_pages: 1, warning_count: 0 }, meta: META });
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/reconstruction/start`) {
      await fulfillJson(route, { data: { job_id: JOB_ID, status: "QUEUED" }, meta: META }, 202);
      return;
    }
    if (path === `/api/v1/projects/${PROJECT_ID}/exports`) {
      await fulfillJson(route, { data: [{
        checksum_sha256: CHECKSUM,
        created_at: "2026-08-31T00:10:00.000Z",
        filename: "release-trial-translated.pdf",
        id: EXPORT_ID,
        output_profile: "STANDARD",
        status: "COMPLETED",
        version_number: 1,
      }], meta: META });
      return;
    }
    if (path === `/api/v1/exports/${EXPORT_ID}/download`) {
      await route.fulfill({ body: "%PDF-1.7\n%%EOF", headers: { ...CORS_HEADERS, "content-type": "application/pdf" }, status: 200 });
      return;
    }
    if (path === "/api/v1/backups" && method === "GET") {
      await fulfillJson(route, { data: [{
        application_version: "0.1.0",
        backup_type: "DATABASE_ONLY",
        checksum_sha256: CHECKSUM,
        completed_at: "2026-08-31T00:15:00.000Z",
        created_at: "2026-08-31T00:14:00.000Z",
        database_schema_version: "head",
        filename: "transloka-backup.zip",
        id: BACKUP_ID,
        size_bytes: 4096,
        status: "COMPLETED",
      }], meta: META });
      return;
    }
    if (path === "/api/v1/backups" && method === "POST") {
      await fulfillJson(route, { data: { backup_id: null, job_id: JOB_ID, status: "QUEUED" }, meta: META }, 202);
      return;
    }
    if (path === `/api/v1/backups/${BACKUP_ID}/verify`) {
      await fulfillJson(route, { data: { backup_id: BACKUP_ID, message: "Backup archive verified.", status: "VERIFIED" }, meta: META });
      return;
    }
    if (path === `/api/v1/backups/${BACKUP_ID}/restore`) {
      await fulfillJson(route, { data: { backup_id: BACKUP_ID, backup_type: "DATABASE_ONLY", job_id: JOB_ID, pre_restore_backup_id: PRE_RESTORE_BACKUP_ID, status: "COMPLETED" }, meta: META });
      return;
    }
    if (path === `/api/v1/documents/${DOCUMENT_ID}/source`) {
      await route.fulfill({ body: "%PDF-1.7\n%%EOF", headers: { ...CORS_HEADERS, "content-type": "application/pdf" }, status: 200 });
      return;
    }

    await fulfillJson(route, { error: { code: "UNMOCKED_ROUTE", details: { method, path }, message: "Browser E2E route is not mocked.", request_id: META.request_id } }, 500);
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { exact: true, name: "Projects" })).toBeVisible();
  await page.getByLabel("Project name").fill("Release Trial");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText("Project created.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Release Trial" })).toBeVisible();
  await page.getByRole("link", { name: "Open Release Trial" }).click();

  await expect(page.getByRole("heading", { name: "Translation workspace" })).toBeVisible();
  await page.getByLabel("PDF file").setInputFiles({
    buffer: Buffer.from("%PDF-1.7\n%%EOF"),
    mimeType: "application/pdf",
    name: "release-trial.pdf",
  });
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await expect(page.getByText("Document analysis")).toBeVisible();
  await expect(page.getByRole("button", { name: "OCR" })).toBeEnabled({ timeout: 10_000 });

  await page.getByRole("button", { name: "OCR" }).click();
  await expect(page.getByRole("heading", { name: "Correct recognized source text" })).toBeVisible();
  await expect(page.getByText("Release trial document.").first()).toBeVisible();

  await page.getByRole("button", { name: "Translation" }).click();
  await expect(page.getByRole("heading", { name: "Start local translation" })).toBeVisible();
  await page.getByRole("button", { name: "Start translation" }).click();
  await expect(page.getByText(`Translation started. Job: ${JOB_ID}`)).toBeVisible();

  await page.getByRole("button", { name: "Review" }).click();
  await expect(page.getByRole("heading", { name: "Segments requiring review" })).toBeVisible();
  await page.getByRole("button", { name: /Release trial document\./ }).first().click();
  await expect(page.getByRole("heading", { name: "Side-by-side review" })).toBeVisible();

  await page.getByRole("button", { name: "Reconstruction" }).click();
  await expect(page.getByRole("heading", { name: "Preserve the document while making translated pages readable" })).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Reconstruction progress" })).toBeVisible();

  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByText(`SHA-256: ${CHECKSUM}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Download PDF" })).toBeEnabled();

  await page.getByRole("button", { name: "Backup" }).click();
  await expect(page.getByRole("heading", { name: "Backup and restore" })).toBeVisible();
  await page.getByRole("button", { name: "Create backup" }).click();
  await expect(page.getByText(`Backup job QUEUED: ${JOB_ID}`)).toBeVisible();
  await page.getByRole("button", { name: "Verify backup" }).click();
  await expect(page.getByText("Backup archive verified.")).toBeVisible();
  await page.getByRole("button", { name: "Restore backup" }).click();
  await page.getByLabel("Restore confirmation").fill("RESTORE");
  await page.getByRole("button", { name: "Confirm restore" }).click();
  await expect(page.getByText(`Restore accepted: ${JOB_ID}`)).toBeVisible();
});
