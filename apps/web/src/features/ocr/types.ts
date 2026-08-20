import type { ApiResult } from "@transloka/api-client";

export type OCRReviewConfidence = {
  overall: number | null;
};

export type OCRReviewSegment = {
  id: string;
  block_id: string;
  source_text: string;
  resolved_source_text: string;
  raw_ocr_text: string | null;
  normalized_source_text: string;
  current_revision: number;
  is_locked: boolean;
  confidence: OCRReviewConfidence;
  status: string;
};

export type OCRReviewPage = {
  page_id: string;
  raw_text: string;
  resolved_source_text: string;
  ocr_confidence: number | null;
  segments: OCRReviewSegment[];
};

export type OCRReviewResponse = {
  data: OCRReviewPage;
  meta: { request_id: string };
};

export type SourceResolutionInput = {
  resolved_source_text: string;
  resolution_source: "MANUAL";
  expected_revision: number;
};

export type SourceResolutionResponse = {
  data: OCRReviewSegment & { resolution_source: string };
  meta: { request_id: string };
};

export interface OCRReviewClient {
  getPageOcr(
    this: void,
    pageId: string,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<OCRReviewResponse>>;
  resolveSegmentSource(
    this: void,
    segmentId: string,
    input: SourceResolutionInput,
    options?: { signal?: AbortSignal },
  ): Promise<ApiResult<SourceResolutionResponse>>;
}
