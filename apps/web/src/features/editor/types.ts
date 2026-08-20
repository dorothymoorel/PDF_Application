import type { ApiResult, components } from "@transloka/api-client";

export type ReviewPageData = components["schemas"]["PageEditorViewData"];
export type ReviewSegment = components["schemas"]["PageEditorSegmentResponse"];
export type ReviewWarning = components["schemas"]["PageEditorWarningResponse"];
export type ReviewPageResponse = components["schemas"]["PageEditorViewResponse"];

export type SaveSegmentTranslationInput = {
  expected_revision: number;
  reason?: string;
  reviewed_translation: string;
};

export type SegmentDataResponse = {
  data: ReviewSegment;
  meta: components["schemas"]["ResponseMeta"];
};

export interface ReviewEditorClient {
  getPageEditorView(
    this: void,
    pageId: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<ReviewPageResponse>>;
  editSegmentTranslation(
    this: void,
    segmentId: string,
    input: SaveSegmentTranslationInput,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<SegmentDataResponse>>;
}

export interface ReviewEditorContext {
  heading?: string | null;
  nextSegment?: string | null;
  previousSegment?: string | null;
  sectionSummary?: string | null;
}

export interface ReviewGlossaryItem {
  id: string;
  sourceTerm: string;
  targetTerm: string | null;
}
