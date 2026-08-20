from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class WarningSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WarningStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    IGNORED_BY_POLICY = "IGNORED_BY_POLICY"


class WarningResolutionType(StrEnum):
    AUTO_FIXED = "AUTO_FIXED"
    USER_FIXED = "USER_FIXED"
    USER_ACCEPTED = "USER_ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    IGNORED_BY_POLICY = "IGNORED_BY_POLICY"
    REQUIRES_REPROCESSING = "REQUIRES_REPROCESSING"


class WarningType(StrEnum):
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    READING_ORDER_UNCERTAIN = "READING_ORDER_UNCERTAIN"
    UNKNOWN_CHARACTER = "UNKNOWN_CHARACTER"
    FONT_MAPPING_FAILED = "FONT_MAPPING_FAILED"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    OCR_TEXT_CONFLICT = "OCR_TEXT_CONFLICT"
    UNREADABLE_REGION = "UNREADABLE_REGION"
    ROTATION_UNCERTAIN = "ROTATION_UNCERTAIN"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"
    LOW_TRANSLATION_CONFIDENCE = "LOW_TRANSLATION_CONFIDENCE"
    UNTRANSLATED_TEXT = "UNTRANSLATED_TEXT"
    TARGET_LANGUAGE_MISMATCH = "TARGET_LANGUAGE_MISMATCH"
    POSSIBLE_HALLUCINATION = "POSSIBLE_HALLUCINATION"
    SOURCE_MEANING_DRIFT = "SOURCE_MEANING_DRIFT"
    GLOSSARY_NOT_APPLIED = "GLOSSARY_NOT_APPLIED"
    TERM_INCONSISTENT = "TERM_INCONSISTENT"
    PLACEHOLDER_MISSING = "PLACEHOLDER_MISSING"
    PLACEHOLDER_DUPLICATED = "PLACEHOLDER_DUPLICATED"
    CASE_MISMATCH = "CASE_MISMATCH"
    NUMBER_CHANGED = "NUMBER_CHANGED"
    DATE_CHANGED = "DATE_CHANGED"
    UNIT_CHANGED = "UNIT_CHANGED"
    URL_CHANGED = "URL_CHANGED"
    CITATION_CHANGED = "CITATION_CHANGED"
    CODE_CHANGED = "CODE_CHANGED"
    TEXT_OVERFLOW = "TEXT_OVERFLOW"
    TEXT_CLIPPED = "TEXT_CLIPPED"
    TEXT_OVERLAP = "TEXT_OVERLAP"
    MISSING_TRANSLATED_SEGMENT = "MISSING_TRANSLATED_SEGMENT"
    PLACEHOLDER_RESTORATION_FAILED = "PLACEHOLDER_RESTORATION_FAILED"
    OUTPUT_PDF_CORRUPTED = "OUTPUT_PDF_CORRUPTED"
    ORIGINAL_FILE_CHECKSUM_MISMATCH = "ORIGINAL_FILE_CHECKSUM_MISMATCH"
    PATH_TRAVERSAL_DETECTED = "PATH_TRAVERSAL_DETECTED"
    TABLE_STRUCTURE_CORRUPTED_CRITICAL = "TABLE_STRUCTURE_CORRUPTED_CRITICAL"
    CRITICAL_TEXT_CLIPPING = "CRITICAL_TEXT_CLIPPING"
    CRITICAL_LAYOUT_COLLISION = "CRITICAL_LAYOUT_COLLISION"
    IMAGE_OVERLAP = "IMAGE_OVERLAP"
    MISSING_IMAGE = "MISSING_IMAGE"
    TABLE_OVERFLOW = "TABLE_OVERFLOW"
    FONT_TOO_SMALL = "FONT_TOO_SMALL"
    PAGE_ADDED = "PAGE_ADDED"
    LAYOUT_SHIFT = "LAYOUT_SHIFT"
    HEADING_LEVEL_CHANGED = "HEADING_LEVEL_CHANGED"
    LIST_NUMBERING_CHANGED = "LIST_NUMBERING_CHANGED"
    TABLE_STRUCTURE_CHANGED = "TABLE_STRUCTURE_CHANGED"
    FOOTNOTE_LINK_BROKEN = "FOOTNOTE_LINK_BROKEN"
    READING_ORDER_CHANGED = "READING_ORDER_CHANGED"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Warning(Base):
    __tablename__ = "warnings"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'wrn_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_warnings_prefixed_uuid",
        ),
        CheckConstraint(
            f"warning_type IN ({_sql_values(WarningType)})",
            name="ck_warnings_type",
        ),
        CheckConstraint(
            f"severity IN ({_sql_values(WarningSeverity)})",
            name="ck_warnings_severity",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(WarningStatus)})",
            name="ck_warnings_status",
        ),
        CheckConstraint(
            f"resolution_type IS NULL OR resolution_type IN ({_sql_values(WarningResolutionType)})",
            name="ck_warnings_resolution_type",
        ),
        CheckConstraint("trim(message) <> ''", name="ck_warnings_message"),
        CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_warnings_details_json_valid",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND (resolved_at IS NULL OR trim(resolved_at) <> '')",
            name="ck_warnings_timestamps",
        ),
        CheckConstraint(
            "(status = 'OPEN' AND resolved_at IS NULL AND resolution_type IS NULL) OR "
            "(status <> 'OPEN' AND resolved_at IS NOT NULL AND resolution_type IS NOT NULL)",
            name="ck_warnings_resolution_consistency",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    page_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="SET NULL"),
        nullable=True,
    )
    block_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_blocks.id", ondelete="SET NULL"),
        nullable=True,
    )
    segment_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("application_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    warning_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_warnings_project_open", Warning.project_id, Warning.status, Warning.severity)
Index("ix_warnings_segment", Warning.segment_id)
Index("ix_warnings_page", Warning.page_id)
