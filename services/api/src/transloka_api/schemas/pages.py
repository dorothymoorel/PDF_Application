from typing import Any

from pydantic import BaseModel, Field
from transloka_core.database.models.document_ir import (
    BlockType,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import DocumentStatus
from transloka_core.database.models.pages import PageType

from transloka_api.schemas.projects import ResponseMeta


class GeometryResponse(BaseModel):
    coordinate_system: str = Field(min_length=1)
    x: float = Field(ge=0.0)
    y: float = Field(ge=0.0)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)


class PageConfidenceResponse(BaseModel):
    native_extraction: float | None = Field(default=None, ge=0.0, le=1.0)
    ocr: float | None = Field(default=None, ge=0.0, le=1.0)
    structure: float | None = Field(default=None, ge=0.0, le=1.0)


class PagePreviewResponse(BaseModel):
    thumbnail_url: str | None
    render_url: str | None


class PageEditorPageResponse(BaseModel):
    id: str
    document_id: str
    source_page_number: int = Field(ge=1)
    logical_page_number: str | None
    width_points: float = Field(gt=0.0)
    height_points: float = Field(gt=0.0)
    rotation_degrees: float
    page_type: PageType
    page_classification: str | None
    column_count: int = Field(ge=0)
    reading_direction: str
    status: DocumentStatus
    confidence: PageConfidenceResponse
    preview: PagePreviewResponse


class PageEditorBlockResponse(BaseModel):
    id: str
    page_id: str
    section_id: str | None
    parent_block_id: str | None
    block_type: BlockType
    semantic_role: SemanticRole | None
    page_reading_order: int = Field(ge=0)
    global_reading_order: int | None = Field(default=None, ge=0)
    source_text: str | None
    normalized_source_text: str | None
    source_geometry: GeometryResponse
    target_geometry: GeometryResponse | None
    status: DocumentStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SegmentConfidenceResponse(BaseModel):
    overall: float | None = Field(default=None, ge=0.0, le=1.0)


class PageEditorSegmentResponse(BaseModel):
    id: str
    block_id: str
    section_id: str | None
    segment_order: int = Field(ge=0)
    global_order: int | None = Field(default=None, ge=0)
    source_text: str
    resolved_source_text: str
    machine_translation: str | None
    reviewed_translation: str | None
    final_text: str | None
    source_language: str
    target_language: str
    status: SegmentStatus
    review_status: ReviewStatus
    is_locked: bool
    current_revision: int = Field(ge=0)
    confidence: SegmentConfidenceResponse
    warning_count: int = Field(ge=0)


class PageEditorWarningResponse(BaseModel):
    id: str
    project_id: str
    document_id: str
    page_id: str | None
    segment_id: str | None
    warning_type: str
    severity: str
    message: str
    details: dict[str, Any]
    status: str
    created_at: str
    resolved_at: str | None


class PageEditorViewData(BaseModel):
    page: PageEditorPageResponse
    blocks: list[PageEditorBlockResponse]
    segments: list[PageEditorSegmentResponse]
    warnings: list[PageEditorWarningResponse]


class PageEditorViewResponse(BaseModel):
    data: PageEditorViewData
    meta: ResponseMeta
