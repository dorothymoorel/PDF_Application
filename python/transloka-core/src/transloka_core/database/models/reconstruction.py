from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.document_ir import DocumentBlock
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.jobs import ApplicationJob
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project, ReconstructionMode

_PARENT_MODELS = (Project, Document, ApplicationJob, DocumentPage, DocumentBlock, StoredFile)


class ReconstructionStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PREPARING = "PREPARING"
    MEASURING = "MEASURING"
    LAYING_OUT = "LAYING_OUT"
    RENDERING = "RENDERING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReconstructionBlockStatus(StrEnum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    REFLOWED = "REFLOWED"
    PRESERVED = "PRESERVED"
    RENDERED_AS_IMAGE = "RENDERED_AS_IMAGE"
    OVERFLOW = "OVERFLOW"
    COLLISION = "COLLISION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class ReconstructionStrategy(StrEnum):
    PRESERVE = "PRESERVE"
    OVERLAY = "OVERLAY"
    REFLOW = "REFLOW"
    RECONSTRUCT = "RECONSTRUCT"
    RENDER_AS_IMAGE = "RENDER_AS_IMAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class TargetPageMappingType(StrEnum):
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    UNMAPPED = "UNMAPPED"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


def _prefixed_uuid(prefix: str, table_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


class ReconstructionJob(Base):
    __tablename__ = "reconstruction_jobs"
    __table_args__ = (
        _prefixed_uuid("rcj_", "reconstruction_jobs"),
        CheckConstraint(
            f"mode IN ({_sql_values(ReconstructionMode)})",
            name="ck_reconstruction_jobs_mode",
        ),
        CheckConstraint(
            "trim(settings_version) <> ''",
            name="ck_reconstruction_jobs_settings_version",
        ),
        CheckConstraint(
            "json_valid(settings_json)",
            name="ck_reconstruction_jobs_settings_json_valid",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ReconstructionStatus)})",
            name="ck_reconstruction_jobs_status",
        ),
        CheckConstraint(
            "progress BETWEEN 0.0 AND 1.0",
            name="ck_reconstruction_jobs_progress",
        ),
        CheckConstraint(
            "trim(reconstruction_hash) <> ''",
            name="ck_reconstruction_jobs_hash",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND "
            "(started_at IS NULL OR trim(started_at) <> '') AND "
            "(completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_reconstruction_jobs_timestamps",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_job_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("application_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    settings_version: Mapped[str] = mapped_column(Text, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[float] = mapped_column(REAL, nullable=False)
    reconstruction_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReconstructionPage(Base):
    __tablename__ = "reconstruction_pages"
    __table_args__ = (
        _prefixed_uuid("rcp_", "reconstruction_pages"),
        CheckConstraint(
            "target_page_start >= 1 AND target_page_end >= target_page_start",
            name="ck_reconstruction_pages_target_range",
        ),
        CheckConstraint(
            f"strategy IN ({_sql_values(ReconstructionStrategy)})",
            name="ck_reconstruction_pages_strategy",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ReconstructionStatus)})",
            name="ck_reconstruction_pages_status",
        ),
        CheckConstraint(
            "trim(page_hash) <> ''",
            name="ck_reconstruction_pages_hash",
        ),
        CheckConstraint(
            "warning_count >= 0",
            name="ck_reconstruction_pages_warning_count",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_reconstruction_pages_metadata_json_valid",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND trim(updated_at) <> ''",
            name="ck_reconstruction_pages_timestamps",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    reconstruction_job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("reconstruction_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    target_page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    output_file_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    page_hash: Mapped[str] = mapped_column(Text, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ReconstructionBlock(Base):
    __tablename__ = "reconstruction_blocks"
    __table_args__ = (
        _prefixed_uuid("rcb_", "reconstruction_blocks"),
        CheckConstraint(
            f"strategy IN ({_sql_values(ReconstructionStrategy)})",
            name="ck_reconstruction_blocks_strategy",
        ),
        CheckConstraint(
            "fit_strategy IS NULL OR trim(fit_strategy) <> ''",
            name="ck_reconstruction_blocks_fit_strategy",
        ),
        CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_reconstruction_blocks_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_reconstruction_blocks_target_geometry_json_valid",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ReconstructionBlockStatus)})",
            name="ck_reconstruction_blocks_status",
        ),
        CheckConstraint(
            "font_mapping_json IS NULL OR json_valid(font_mapping_json)",
            name="ck_reconstruction_blocks_font_mapping_json_valid",
        ),
        CheckConstraint(
            "overflow_json IS NULL OR json_valid(overflow_json)",
            name="ck_reconstruction_blocks_overflow_json_valid",
        ),
        CheckConstraint(
            "collision_json IS NULL OR json_valid(collision_json)",
            name="ck_reconstruction_blocks_collision_json_valid",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND trim(updated_at) <> ''",
            name="ck_reconstruction_blocks_timestamps",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    reconstruction_page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("reconstruction_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    block_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    fit_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_geometry_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    font_mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    overflow_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    collision_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class TargetPageMapping(Base):
    __tablename__ = "target_page_mappings"
    __table_args__ = (
        _prefixed_uuid("tpm_", "target_page_mappings"),
        CheckConstraint(
            "target_page_number >= 1",
            name="ck_target_page_mappings_target_page_number",
        ),
        CheckConstraint(
            f"mapping_type IN ({_sql_values(TargetPageMappingType)})",
            name="ck_target_page_mappings_type",
        ),
        CheckConstraint(
            "mapping_order >= 0",
            name="ck_target_page_mappings_order",
        ),
        CheckConstraint(
            "trim(created_at) <> ''",
            name="ck_target_page_mappings_created_at",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    reconstruction_job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("reconstruction_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_type: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_reconstruction_jobs_hash",
    ReconstructionJob.project_id,
    ReconstructionJob.reconstruction_hash,
    unique=True,
    sqlite_where=text("status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')"),
)
Index(
    "uq_reconstruction_blocks_page_block",
    ReconstructionBlock.reconstruction_page_id,
    ReconstructionBlock.block_id,
    unique=True,
)
