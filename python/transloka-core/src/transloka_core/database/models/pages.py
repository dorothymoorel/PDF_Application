from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class PageType(StrEnum):
    DIGITAL = "DIGITAL"
    SCANNED = "SCANNED"
    HYBRID = "HYBRID"
    IMAGE_ONLY = "IMAGE_ONLY"
    FORM = "FORM"
    COVER = "COVER"
    TABLE_OF_CONTENTS = "TABLE_OF_CONTENTS"
    INDEX = "INDEX"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    BLANK = "BLANK"
    UNKNOWN = "UNKNOWN"


_PAGE_TYPE_VALUES = ", ".join(f"'{page_type.value}'" for page_type in PageType)


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'pag_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_document_pages_prefixed_uuid",
        ),
        CheckConstraint(
            "source_page_number >= 1",
            name="ck_document_pages_source_number",
        ),
        CheckConstraint(
            "width_points > 0 AND height_points > 0",
            name="ck_document_pages_geometry",
        ),
        CheckConstraint(
            "rotation_degrees IN (0.0, 90.0, 180.0, 270.0)",
            name="ck_document_pages_rotation",
        ),
        CheckConstraint(
            f"page_type IN ({_PAGE_TYPE_VALUES})",
            name="ck_document_pages_type",
        ),
        CheckConstraint("column_count >= 0", name="ck_document_pages_column_count"),
        CheckConstraint(
            "trim(reading_direction) <> ''",
            name="ck_document_pages_reading_direction",
        ),
        CheckConstraint("trim(status) <> ''", name="ck_document_pages_status"),
        CheckConstraint(
            "native_extraction_confidence IS NULL "
            "OR native_extraction_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_native_confidence",
        ),
        CheckConstraint(
            "ocr_confidence IS NULL OR ocr_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_ocr_confidence",
        ),
        CheckConstraint(
            "structure_confidence IS NULL OR structure_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_structure_confidence",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_pages_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_page_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    width_points: Mapped[float] = mapped_column(REAL, nullable=False)
    height_points: Mapped[float] = mapped_column(REAL, nullable=False)
    rotation_degrees: Mapped[float] = mapped_column(REAL, nullable=False)
    page_type: Mapped[str] = mapped_column(Text, nullable=False)
    page_classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_direction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    render_file_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    thumbnail_file_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    native_extraction_confidence: Mapped[float | None] = mapped_column(
        REAL,
        nullable=True,
    )
    ocr_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    structure_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_document_pages_number",
    DocumentPage.document_id,
    DocumentPage.source_page_number,
    unique=True,
)
Index(
    "ix_document_pages_status",
    DocumentPage.document_id,
    DocumentPage.status,
)
Index(
    "ix_document_pages_type",
    DocumentPage.document_id,
    DocumentPage.page_type,
)
