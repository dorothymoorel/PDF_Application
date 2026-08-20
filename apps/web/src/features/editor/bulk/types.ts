import type { ApiResult } from "@transloka/api-client";

export type BulkSegmentAction = "approve" | "lock" | "retranslate";

export type BulkSegment = {
  id: string;
  current_revision: number;
  is_locked: boolean;
  source_text?: string;
};

export type BulkSegmentActionInput = {
  action: BulkSegmentAction;
  selected_ids: string[];
  expected_revisions: Record<string, number>;
};

export type BulkSegmentActionResult = {
  segment_id: string;
  status: "FAILED" | "QUEUED" | "SUCCEEDED";
  current_revision: number | null;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  } | null;
};

export type BulkSegmentActionResponse = {
  data: {
    action: BulkSegmentAction;
    results: BulkSegmentActionResult[];
    succeeded: number;
    failed: number;
    queued: number;
    job_id: string | null;
  };
  meta: { request_id: string };
};

export type BulkSegmentActionClient = {
  bulkSegmentAction(
    input: BulkSegmentActionInput,
    options?: { idempotencyKey?: string; signal?: AbortSignal },
  ): Promise<ApiResult<BulkSegmentActionResponse>>;
};
