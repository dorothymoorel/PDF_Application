"""Export metadata and immutable versioning values."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.projects import Project
from transloka_core.database.models.reconstruction import ReconstructionJob

_PARENT_MODELS = (Project, Document, ReconstructionJob, StoredFile)


class ExportType(StrEnum):
    """Artifacts that can be produced by an export job."""

    TRANSLATED_PDF = "TRANSLATED_PDF"
    BILINGUAL_PDF = "BILINGUAL_PDF"
    QUALITY_REPORT = "QUALITY_REPORT"
    GLOSSARY_CSV = "GLOSSARY_CSV"
    DOCUMENT_IR_PACKAGE = "DOCUMENT_IR_PACKAGE"


class ExportStatus(StrEnum):
    """Lifecycle states persisted for one export version."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExportProfile(StrEnum):
    """Named output profiles understood by the Personal MVP."""

    STANDARD = "STANDARD"
    HIGH_QUALITY = "HIGH_QUALITY"
    ARCHIVAL = "ARCHIVAL"
    COMPACT = "COMPACT"
    CUSTOM = "CUSTOM"


OutputProfile = ExportProfile


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Export(Base):
    """One immutable export record; every new version gets a new row."""

    __tablename__ = "exports"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'exp_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_exports_prefixed_uuid",
        ),
        CheckConstraint(
            f"export_type IN ({_sql_values(ExportType)})",
            name="ck_exports_type",
        ),
        CheckConstraint(
            "trim(output_profile) <> ''",
            name="ck_exports_profile",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_exports_version",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(ExportStatus)})",
            name="ck_exports_status",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_exports_page_count",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_exports_size",
        ),
        CheckConstraint(
            "checksum_sha256 IS NULL OR "
            "(length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="ck_exports_checksum",
        ),
        CheckConstraint(
            "validation_report_id IS NULL OR trim(validation_report_id) <> ''",
            name="ck_exports_validation_report",
        ),
        CheckConstraint(
            "json_valid(settings_json)",
            name="ck_exports_settings_json_valid",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND (completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_exports_timestamps",
        ),
        CheckConstraint(
            "status NOT IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS') OR "
            "(file_id IS NOT NULL AND page_count IS NOT NULL AND size_bytes IS NOT NULL "
            "AND checksum_sha256 IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_exports_completed_requirements",
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
    reconstruction_job_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("reconstruction_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    export_type: Mapped[str] = mapped_column(Text, nullable=False)
    output_profile: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_report_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "uq_exports_project_type_version",
    Export.project_id,
    Export.export_type,
    Export.version_number,
    unique=True,
)
Index("ix_exports_project_status", Export.project_id, Export.status)
