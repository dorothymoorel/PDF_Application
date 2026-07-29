"""Create the stored files table.

Revision ID: 0004_stored_files
Revises: 0003_projects
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stored_files"
down_revision: str | Sequence[str] | None = "0003_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FILE_ROLES = (
    "'ORIGINAL', 'PAGE_RENDER', 'THUMBNAIL', 'EXTRACTED_ASSET', 'OCR_INPUT', "
    "'OCR_OUTPUT', 'IR_SNAPSHOT', 'RECONSTRUCTED_PAGE', 'EXPORT', 'BACKUP', "
    "'TEMPORARY', 'BENCHMARK_REPORT'"
)
_FILE_STATUSES = (
    "'CREATED', 'AVAILABLE', 'VALIDATED', 'MISSING', 'CORRUPTED', 'DELETION_QUEUED', 'DELETED'"
)


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("file_role", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("safe_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("is_immutable", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'fil_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_stored_files_prefixed_uuid",
        ),
        sa.CheckConstraint(
            f"file_role IN ({_FILE_ROLES})",
            name="ck_stored_files_role",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "trim(safe_filename) <> ''",
            name="ck_stored_files_safe_filename",
        ),
        sa.CheckConstraint("trim(mime_type) <> ''", name="ck_stored_files_mime_type"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_stored_files_size"),
        sa.CheckConstraint(
            "length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_stored_files_checksum",
        ),
        sa.CheckConstraint(
            "is_immutable IN (0, 1)",
            name="ck_stored_files_immutable",
        ),
        sa.CheckConstraint(
            f"status IN ({_FILE_STATUSES})",
            name="ck_stored_files_status",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_stored_files_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_stored_files_project_id_projects",
            ondelete="CASCADE",
        ),
        # ponytail: M3-T06 adds this FK with documents; SQLite blocks inserts
        # while the referenced table does not exist.
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_stored_files_storage_key",
        "stored_files",
        ["storage_key"],
        unique=True,
    )
    op.create_index(
        "ix_stored_files_project_role",
        "stored_files",
        ["project_id", "file_role"],
    )
    op.create_index(
        "ix_stored_files_checksum",
        "stored_files",
        ["checksum_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_stored_files_checksum", table_name="stored_files")
    op.drop_index("ix_stored_files_project_role", table_name="stored_files")
    op.drop_index("uq_stored_files_storage_key", table_name="stored_files")
    op.drop_table("stored_files")
