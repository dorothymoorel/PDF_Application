from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class SegmentRevisionType(StrEnum):
    MACHINE_TRANSLATION = "MACHINE_TRANSLATION"
    AUTOMATIC_RETRY = "AUTOMATIC_RETRY"
    GLOSSARY_REAPPLICATION = "GLOSSARY_REAPPLICATION"
    USER_EDIT = "USER_EDIT"
    APPROVE = "APPROVE"
    UNAPPROVE = "UNAPPROVE"
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"
    RESTORE_VERSION = "RESTORE_VERSION"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class SegmentRevision(Base):
    __tablename__ = "segment_revisions"
    __table_args__ = (
        CheckConstraint("revision_number >= 1", name="ck_segment_revisions_number"),
        CheckConstraint(
            f"revision_type IN ({_sql_values(SegmentRevisionType)})",
            name="ck_segment_revisions_type",
        ),
        CheckConstraint(
            "new_text IS NOT NULL AND trim(new_text) <> ''", name="ck_segment_revisions_new_text"
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_segment_revisions_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("document_segments.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_type: Mapped[str] = mapped_column(Text, nullable=False)
    previous_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_translation_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("segment_translations.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_segment_revisions_number",
    SegmentRevision.segment_id,
    SegmentRevision.revision_number,
    unique=True,
)
