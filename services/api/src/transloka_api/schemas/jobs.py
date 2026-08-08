from pydantic import BaseModel, ConfigDict, Field, field_validator
from transloka_core.database.models.jobs import JobAttemptStatus, JobStatus, JobType

from transloka_api.schemas.projects import ResponseMeta


class CancelJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value.isprintable():
            raise ValueError("The cancellation reason contains invalid characters.")
        return value


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
