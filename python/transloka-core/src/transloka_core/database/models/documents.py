from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.projects import DocumentType


class DocumentClass(StrEnum):
    DIGITAL_PDF = "DIGITAL_PDF"
    SCANNED_PDF = "SCANNED_PDF"
    HYBRID_PDF = "HYBRID_PDF"
    UNSUPPORTED = "UNSUPPORTED"
    CORRUPTED = "CORRUPTED"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"


class DocumentStatus(StrEnum):
    CREATED = "CREATED"
    ANALYZED = "ANALYZED"
    EXTRACTED = "EXTRACTED"
    OCR_PARTIAL = "OCR_PARTIAL"
    OCR_COMPLETE = "OCR_COMPLETE"
    STRUCTURED = "STRUCTURED"
    TERMS_DETECTED = "TERMS_DETECTED"
    READY_FOR_TRANSLATION = "READY_FOR_TRANSLATION"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    PARTIALLY_TRANSLATED = "PARTIALLY_TRANSLATED"
    REVIEWING = "REVIEWING"
    REVIEWED = "REVIEWED"
    RECONSTRUCTING = "RECONSTRUCTING"
    RECONSTRUCTED = "RECONSTRUCTED"
    QUALITY_CHECKED = "QUALITY_CHECKED"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'doc_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_documents_prefixed_uuid",
        ),
        CheckConstraint("trim(ir_version) <> ''", name="ck_documents_ir_version"),
        CheckConstraint(
            f"document_type IN ({_sql_values(DocumentType)})",
            name="ck_documents_type",
        ),
        CheckConstraint(
            f"document_class IN ({_sql_values(DocumentClass)})",
            name="ck_documents_class",
        ),
        CheckConstraint(
            "trim(source_language) <> ''",
            name="ck_documents_source_language",
        ),
        CheckConstraint(
            "trim(target_language) <> ''",
            name="ck_documents_target_language",
        ),
        CheckConstraint("page_count >= 0", name="ck_documents_page_count"),
        CheckConstraint(
            "word_count_estimate IS NULL OR word_count_estimate >= 0",
            name="ck_documents_word_count",
        ),
        CheckConstraint(
            "has_text_layer IN (0, 1)",
            name="ck_documents_has_text_layer",
        ),
        CheckConstraint(
            "scanned_page_count >= 0 AND scanned_page_count <= page_count",
            name="ck_documents_scanned_page_count",
        ),
        CheckConstraint("image_count >= 0", name="ck_documents_image_count"),
        CheckConstraint("table_count >= 0", name="ck_documents_table_count"),
        CheckConstraint(
            f"status IN ({_sql_values(DocumentStatus)})",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_documents_metadata_json_valid",
        ),
        CheckConstraint(
            "analysis_json IS NULL OR json_valid(analysis_json)",
            name="ck_documents_analysis_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_file_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("stored_files.id"),
        nullable=False,
    )
    ir_version: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    document_class: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_text_layer: Mapped[int] = mapped_column(Integer, nullable=False)
    scanned_page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_documents_project_original_file",
    Document.project_id,
    Document.original_file_id,
    unique=True,
)
