from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    IMPORTING = "IMPORTING"
    ANALYZING = "ANALYZING"
    WAITING_FOR_SETTINGS = "WAITING_FOR_SETTINGS"
    EXTRACTING = "EXTRACTING"
    OCR_PROCESSING = "OCR_PROCESSING"
    TERMS_DETECTED = "TERMS_DETECTED"
    WAITING_FOR_GLOSSARY = "WAITING_FOR_GLOSSARY"
    TRANSLATING = "TRANSLATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REVIEWING = "REVIEWING"
    RECONSTRUCTING = "RECONSTRUCTING"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"
    DELETION_QUEUED = "DELETION_QUEUED"


class DocumentType(StrEnum):
    ACADEMIC_PAPER = "ACADEMIC_PAPER"
    ACADEMIC_BOOK = "ACADEMIC_BOOK"
    TECHNICAL_BOOK = "TECHNICAL_BOOK"
    USER_MANUAL = "USER_MANUAL"
    BUSINESS_REPORT = "BUSINESS_REPORT"
    LEGAL_DOCUMENT = "LEGAL_DOCUMENT"
    FICTION_BOOK = "FICTION_BOOK"
    NONFICTION_BOOK = "NONFICTION_BOOK"
    PRESENTATION_EXPORT = "PRESENTATION_EXPORT"
    BROCHURE = "BROCHURE"
    FORM = "FORM"
    COMIC_OR_GRAPHIC_BOOK = "COMIC_OR_GRAPHIC_BOOK"
    GENERAL_DOCUMENT = "GENERAL_DOCUMENT"
    UNKNOWN = "UNKNOWN"


class TranslationStyle(StrEnum):
    LITERAL = "LITERAL"
    PROFESSIONAL = "PROFESSIONAL"
    ACADEMIC = "ACADEMIC"
    NATURAL = "NATURAL"


class ReconstructionMode(StrEnum):
    OVERLAY = "OVERLAY"
    REFLOW = "REFLOW"
    HYBRID = "HYBRID"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'prj_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_projects_prefixed_uuid",
        ),
        CheckConstraint("trim(name) <> ''", name="ck_projects_name"),
        CheckConstraint(
            f"status IN ({_sql_values(ProjectStatus)})",
            name="ck_projects_status",
        ),
        CheckConstraint("trim(source_language) <> ''", name="ck_projects_source_language"),
        CheckConstraint("trim(target_language) <> ''", name="ck_projects_target_language"),
        CheckConstraint(
            f"document_type IN ({_sql_values(DocumentType)})",
            name="ck_projects_document_type",
        ),
        CheckConstraint(
            f"translation_style IN ({_sql_values(TranslationStyle)})",
            name="ck_projects_translation_style",
        ),
        CheckConstraint(
            f"reconstruction_mode IN ({_sql_values(ReconstructionMode)})",
            name="ck_projects_reconstruction_mode",
        ),
        CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name="ck_projects_progress",
        ),
        CheckConstraint("json_valid(settings_json)", name="ck_projects_settings_json_valid"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    translation_style: Mapped[str] = mapped_column(Text, nullable=False)
    reconstruction_mode: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[float] = mapped_column(REAL, nullable=False)
    active_document_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    archived_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_projects_status", Project.status)
Index("ix_projects_updated_at", Project.updated_at.desc())
