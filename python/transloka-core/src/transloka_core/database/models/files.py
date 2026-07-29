from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class FileRole(StrEnum):
    ORIGINAL = "ORIGINAL"
    PAGE_RENDER = "PAGE_RENDER"
    THUMBNAIL = "THUMBNAIL"
    EXTRACTED_ASSET = "EXTRACTED_ASSET"
    OCR_INPUT = "OCR_INPUT"
    OCR_OUTPUT = "OCR_OUTPUT"
    IR_SNAPSHOT = "IR_SNAPSHOT"
    RECONSTRUCTED_PAGE = "RECONSTRUCTED_PAGE"
    EXPORT = "EXPORT"
    BACKUP = "BACKUP"
    TEMPORARY = "TEMPORARY"
    BENCHMARK_REPORT = "BENCHMARK_REPORT"


class FileStatus(StrEnum):
    CREATED = "CREATED"
    AVAILABLE = "AVAILABLE"
    VALIDATED = "VALIDATED"
    MISSING = "MISSING"
    CORRUPTED = "CORRUPTED"
    DELETION_QUEUED = "DELETION_QUEUED"
    DELETED = "DELETED"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'fil_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_stored_files_prefixed_uuid",
        ),
        CheckConstraint(
            f"file_role IN ({_sql_values(FileRole)})",
            name="ck_stored_files_role",
        ),
        CheckConstraint(
            "trim(storage_key) <> '' AND storage_key = trim(storage_key) "
            "AND substr(storage_key, 1, 1) <> '/' "
            "AND instr(storage_key, '\\') = 0 "
            "AND instr(storage_key, ':') = 0 "
            "AND instr(storage_key, char(0)) = 0 "
            "AND storage_key <> '..' "
            "AND storage_key NOT LIKE '../%' "
            "AND storage_key NOT LIKE '%/../%' "
            "AND storage_key NOT LIKE '%/..' "
            "AND storage_key NOT LIKE './%' "
            "AND storage_key NOT LIKE '%/./%' "
            "AND storage_key NOT LIKE '%/.' "
            "AND storage_key NOT LIKE '%//%'",
            name="ck_stored_files_relative_storage_key",
        ),
        CheckConstraint("trim(safe_filename) <> ''", name="ck_stored_files_safe_filename"),
        CheckConstraint("trim(mime_type) <> ''", name="ck_stored_files_mime_type"),
        CheckConstraint("size_bytes >= 0", name="ck_stored_files_size"),
        CheckConstraint(
            "length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_stored_files_checksum",
        ),
        CheckConstraint(
            "is_immutable IN (0, 1)",
            name="ck_stored_files_immutable",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(FileStatus)})",
            name="ck_stored_files_status",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_stored_files_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_role: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    safe_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    is_immutable: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("uq_stored_files_storage_key", StoredFile.storage_key, unique=True)
Index("ix_stored_files_project_role", StoredFile.project_id, StoredFile.file_role)
Index("ix_stored_files_checksum", StoredFile.checksum_sha256)
