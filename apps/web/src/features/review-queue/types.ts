import type { ApiResult, components } from "@transloka/api-client";

export type ReviewQueueSegment = components["schemas"]["PageEditorSegmentResponse"];
export type ReviewQueueWarning = components["schemas"]["PageEditorWarningResponse"];

export type ReviewQueueSourceContext = {
  previous_segment: string | null;
  next_segment: string | null;
  heading: string | null;
};

export type ReviewQueueItem = {
  segment: ReviewQueueSegment;
  warnings: ReviewQueueWarning[];
  source_context: ReviewQueueSourceContext;
};

export type ReviewQueueResponse = {
  data: ReviewQueueItem[];
  meta: {
    request_id: string;
    pagination: {
      limit: number;
      next_cursor: string | null;
      has_more: boolean;
    };
  };
};

export type ReviewQueueQueryFilters = {
  confidence_max?: number;
  page_id?: string;
  section_id?: string;
  status?: string;
  warning?: boolean;
};

export interface ReviewQueueClient {
  listReviewQueue(
    this: void,
    projectId: string,
    filters: ReviewQueueQueryFilters,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<ReviewQueueResponse>>;
}
