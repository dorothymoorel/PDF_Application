"""Create durable backup metadata records.

Revision ID: 0017_backups
Revises: 0016_quality
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_backups"
down_revision: str | Sequence[str] | None = "0016_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKUP_TYPES = "'DATABASE_ONLY', 'METADATA', 'FULL_PROJECTS', 'FULL_APPLICATION', 'PRE_RESTORE'"
_BACKUP_STATUSES = "'CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'"


def upgrade() -> None:
    op.create_table(
        "backups",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("backup_type", sa.Text(), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=True),
        sa.Column("application_version", sa.Text(), nullable=False),
        sa.Column("database_schema_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("included_content_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'bkp_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_backups_prefixed_uuid",
        ),
        sa.CheckConstraint(
            f"backup_type IN ({_BACKUP_TYPES})",
            name="ck_backups_type",
        ),
        sa.CheckConstraint(
            "trim(application_version) <> ''",
            name="ck_backups_application_version",
        ),
        sa.CheckConstraint(
            "trim(database_schema_version) <> ''",
            name="ck_backups_schema_version",
        ),
        sa.CheckConstraint(
            f"status IN ({_BACKUP_STATUSES})",
            name="ck_backups_status",
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_backups_size",
        ),
        sa.CheckConstraint(
            "checksum_sha256 IS NULL OR "
            "(length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="ck_backups_checksum",
        ),
        sa.CheckConstraint(
            "json_valid(included_content_json) AND json_type(included_content_json) = 'array'",
            name="ck_backups_included_content_json_valid",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND (completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_backups_timestamps",
        ),
        sa.CheckConstraint(
            "status NOT IN ('COMPLETED') OR "
            "(file_id IS NOT NULL AND size_bytes IS NOT NULL AND "
            "checksum_sha256 IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_backups_completed_requirements",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_files.id"],
            name="fk_backups_file_id_stored_files",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index("ix_backups_status", "backups", ["status"])
    op.create_index("ix_backups_type", "backups", ["backup_type"])


def downgrade() -> None:
    op.drop_index("ix_backups_type", table_name="backups")
    op.drop_index("ix_backups_status", table_name="backups")
    op.drop_table("backups")
