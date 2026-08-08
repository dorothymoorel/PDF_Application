from pydantic import BaseModel, Field
from transloka_core.database.models.jobs import JobAttemptStatus, JobStatus, JobType

from transloka_api.schemas.projects import ResponseMeta


class JobErrorResponse(BaseModel):
    code: str
    message: str


class JobResponse(BaseModel):
    id: str
    job_type: JobType
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    current_stage: str | None
    project_id: str | None
    document_id: str | None
    retry_count: int = Field(ge=0)
    max_retries: int = Field(ge=0)
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: JobErrorResponse | None


class CursorPagination(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class JobCollectionMeta(ResponseMeta):
    pagination: CursorPagination


class JobDataResponse(BaseModel):
    data: JobResponse
    meta: ResponseMeta


class JobListResponse(BaseModel):
    data: list[JobResponse]
    meta: JobCollectionMeta


class JobAttemptErrorResponse(BaseModel):
    code: str
    message: str


class JobAttemptResponse(BaseModel):
    attempt_number: int = Field(ge=1)
    status: JobAttemptStatus
    started_at: str
    completed_at: str | None
    duration_ms: int | None = Field(default=None, ge=0)
    error: JobAttemptErrorResponse | None


class JobAttemptListResponse(BaseModel):
    data: list[JobAttemptResponse]
    meta: ResponseMeta
