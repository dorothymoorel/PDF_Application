"""Durable backup metadata and lifecycle values."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.backup.manifest import BackupType
from transloka_core.database.models.application import Base
from transloka_core.database.models.files import StoredFile

_PARENT_MODELS = (StoredFile,)


class BackupStatus(StrEnum):
    """Lifecycle states persisted for a backup operation."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class Backup(Base):
    """One backup archive record and the manifest metadata it represents."""

    __tablename__ = "backups"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'bkp_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_backups_prefixed_uuid",
        ),
        CheckConstraint(
            f"backup_type IN ({_sql_values(BackupType)})",
            name="ck_backups_type",
        ),
        CheckConstraint("trim(application_version) <> ''", name="ck_backups_application_version"),
        CheckConstraint(
            "trim(database_schema_version) <> ''",
            name="ck_backups_schema_version",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(BackupStatus)})",
            name="ck_backups_status",
        ),
        CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_backups_size",
        ),
        CheckConstraint(
            "checksum_sha256 IS NULL OR "
            "(length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="ck_backups_checksum",
        ),
        CheckConstraint(
            "json_valid(included_content_json) AND json_type(included_content_json) = 'array'",
            name="ck_backups_included_content_json_valid",
        ),
        CheckConstraint(
            "trim(created_at) <> '' AND (completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_backups_timestamps",
        ),
        CheckConstraint(
            "status NOT IN ('COMPLETED') OR "
            "(file_id IS NOT NULL AND size_bytes IS NOT NULL AND "
            "checksum_sha256 IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_backups_completed_requirements",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    backup_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    application_version: Mapped[str] = mapped_column(Text, nullable=False)
    database_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    included_content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


BackupRecord = Backup
BackupLifecycleStatus = BackupStatus

Index("ix_backups_status", Backup.status)
Index("ix_backups_type", Backup.backup_type)


__all__ = [
    "Backup",
    "BackupLifecycleStatus",
    "BackupRecord",
    "BackupStatus",
    "BackupType",
]
