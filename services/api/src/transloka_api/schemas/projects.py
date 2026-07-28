from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from transloka_core.database.models.projects import (
    DocumentType,
    ProjectStatus,
    ReconstructionMode,
    TranslationStyle,
)

type ProjectSortField = Literal["updated_at", "name", "status", "progress"]
type SortOrder = Literal["asc", "desc"]


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    document_type: DocumentType
    translation_style: TranslationStyle
    reconstruction_mode: ReconstructionMode


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    translation_style: TranslationStyle | None = None
    reconstruction_mode: ReconstructionMode | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: ProjectStatus
    source_language: str
    target_language: str
    document_type: DocumentType
    translation_style: TranslationStyle
    reconstruction_mode: ReconstructionMode
    progress: float
    active_document_id: str | None
    settings: dict[str, object]
    created_at: str
    updated_at: str


class ResponseMeta(BaseModel):
    request_id: str


class OffsetPagination(BaseModel):
    limit: int
    offset: int
    total: int
    has_more: bool


class CollectionMeta(ResponseMeta):
    pagination: OffsetPagination


class ProjectDataResponse(BaseModel):
    data: ProjectResponse
    meta: ResponseMeta


class ProjectListResponse(BaseModel):
    data: list[ProjectResponse]
    meta: CollectionMeta
