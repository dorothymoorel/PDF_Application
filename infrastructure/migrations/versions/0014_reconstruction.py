"""Create reconstruction job, page, block, and mapping tables.

Revision ID: 0014_reconstruction
Revises: 0013_warnings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_reconstruction"
down_revision: str | Sequence[str] | None = "0013_warnings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODES = "'OVERLAY', 'REFLOW', 'HYBRID'"
_STATUSES = (
    "'NOT_STARTED', 'PREPARING', 'MEASURING', 'LAYING_OUT', 'RENDERING', 'VALIDATING', "
    "'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED'"
)
_BLOCK_STATUSES = (
    "'PENDING', 'PLACED', 'REFLOWED', 'PRESERVED', 'RENDERED_AS_IMAGE', 'OVERFLOW', "
    "'COLLISION', 'NEEDS_REVIEW', 'FAILED'"
)
_STRATEGIES = "'PRESERVE', 'OVERLAY', 'REFLOW', 'RECONSTRUCT', 'RENDER_AS_IMAGE', 'MANUAL_REVIEW'"
_MAPPING_TYPES = "'ONE_TO_ONE', 'ONE_TO_MANY', 'MANY_TO_ONE', 'UNMAPPED'"


def upgrade() -> None:
    op.create_table(
        "reconstruction_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("application_job_id", sa.Text(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("settings_version", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", sa.REAL(), nullable=False),
        sa.Column("reconstruction_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'rcj_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_reconstruction_jobs_prefixed_uuid",
        ),
        sa.CheckConstraint(f"mode IN ({_MODES})", name="ck_reconstruction_jobs_mode"),
        sa.CheckConstraint(
            "trim(settings_version) <> ''",
            name="ck_reconstruction_jobs_settings_version",
        ),
        sa.CheckConstraint(
            "json_valid(settings_json)",
            name="ck_reconstruction_jobs_settings_json_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUSES})",
            name="ck_reconstruction_jobs_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0.0 AND 1.0",
            name="ck_reconstruction_jobs_progress",
        ),
        sa.CheckConstraint(
            "trim(reconstruction_hash) <> ''",
            name="ck_reconstruction_jobs_hash",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND "
            "(started_at IS NULL OR trim(started_at) <> '') AND "
            "(completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_reconstruction_jobs_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_reconstruction_jobs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_reconstruction_jobs_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["application_job_id"],
            ["application_jobs.id"],
            name="fk_reconstruction_jobs_application_job_id_application_jobs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_reconstruction_jobs_hash "
        "ON reconstruction_jobs(project_id, reconstruction_hash) "
        "WHERE status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS')"
    )

    op.create_table(
        "reconstruction_pages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("reconstruction_job_id", sa.Text(), nullable=False),
        sa.Column("source_page_id", sa.Text(), nullable=False),
        sa.Column("target_page_start", sa.Integer(), nullable=False),
        sa.Column("target_page_end", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("output_file_id", sa.Text(), nullable=True),
        sa.Column("page_hash", sa.Text(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'rcp_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_reconstruction_pages_prefixed_uuid",
        ),
        sa.CheckConstraint(
            "target_page_start >= 1 AND target_page_end >= target_page_start",
            name="ck_reconstruction_pages_target_range",
        ),
        sa.CheckConstraint(
            f"strategy IN ({_STRATEGIES})",
            name="ck_reconstruction_pages_strategy",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUSES})",
            name="ck_reconstruction_pages_status",
        ),
        sa.CheckConstraint("trim(page_hash) <> ''", name="ck_reconstruction_pages_hash"),
        sa.CheckConstraint(
            "warning_count >= 0",
            name="ck_reconstruction_pages_warning_count",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_reconstruction_pages_metadata_json_valid",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND trim(updated_at) <> ''",
            name="ck_reconstruction_pages_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["reconstruction_job_id"],
            ["reconstruction_jobs.id"],
            name="fk_reconstruction_pages_job_id_reconstruction_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["document_pages.id"],
            name="fk_reconstruction_pages_source_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["output_file_id"],
            ["stored_files.id"],
            name="fk_reconstruction_pages_output_file_id_stored_files",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )

    op.create_table(
        "reconstruction_blocks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("reconstruction_page_id", sa.Text(), nullable=False),
        sa.Column("block_id", sa.Text(), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=False),
        sa.Column("fit_strategy", sa.Text(), nullable=True),
        sa.Column("source_geometry_json", sa.Text(), nullable=False),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("font_mapping_json", sa.Text(), nullable=True),
        sa.Column("overflow_json", sa.Text(), nullable=True),
        sa.Column("collision_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'rcb_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_reconstruction_blocks_prefixed_uuid",
        ),
        sa.CheckConstraint(
            f"strategy IN ({_STRATEGIES})",
            name="ck_reconstruction_blocks_strategy",
        ),
        sa.CheckConstraint(
            "fit_strategy IS NULL OR trim(fit_strategy) <> ''",
            name="ck_reconstruction_blocks_fit_strategy",
        ),
        sa.CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_reconstruction_blocks_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_reconstruction_blocks_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_BLOCK_STATUSES})",
            name="ck_reconstruction_blocks_status",
        ),
        sa.CheckConstraint(
            "font_mapping_json IS NULL OR json_valid(font_mapping_json)",
            name="ck_reconstruction_blocks_font_mapping_json_valid",
        ),
        sa.CheckConstraint(
            "overflow_json IS NULL OR json_valid(overflow_json)",
            name="ck_reconstruction_blocks_overflow_json_valid",
        ),
        sa.CheckConstraint(
            "collision_json IS NULL OR json_valid(collision_json)",
            name="ck_reconstruction_blocks_collision_json_valid",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND trim(updated_at) <> ''",
            name="ck_reconstruction_blocks_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["reconstruction_page_id"],
            ["reconstruction_pages.id"],
            name="fk_reconstruction_blocks_page_id_reconstruction_pages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.id"],
            name="fk_reconstruction_blocks_block_id_document_blocks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_reconstruction_blocks_page_block",
        "reconstruction_blocks",
        ["reconstruction_page_id", "block_id"],
        unique=True,
    )

    op.create_table(
        "target_page_mappings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("reconstruction_job_id", sa.Text(), nullable=False),
        sa.Column("source_page_id", sa.Text(), nullable=False),
        sa.Column("target_page_number", sa.Integer(), nullable=False),
        sa.Column("mapping_type", sa.Text(), nullable=False),
        sa.Column("mapping_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'tpm_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_target_page_mappings_prefixed_uuid",
        ),
        sa.CheckConstraint(
            "target_page_number >= 1",
            name="ck_target_page_mappings_target_page_number",
        ),
        sa.CheckConstraint(
            f"mapping_type IN ({_MAPPING_TYPES})",
            name="ck_target_page_mappings_type",
        ),
        sa.CheckConstraint(
            "mapping_order >= 0",
            name="ck_target_page_mappings_order",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> ''",
            name="ck_target_page_mappings_created_at",
        ),
        sa.ForeignKeyConstraint(
            ["reconstruction_job_id"],
            ["reconstruction_jobs.id"],
            name="fk_target_page_mappings_job_id_reconstruction_jobs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_page_id"],
            ["document_pages.id"],
            name="fk_target_page_mappings_source_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )


def downgrade() -> None:
    op.drop_table("target_page_mappings")
    op.drop_index("uq_reconstruction_blocks_page_block", table_name="reconstruction_blocks")
    op.drop_table("reconstruction_blocks")
    op.drop_table("reconstruction_pages")
    op.drop_index("uq_reconstruction_jobs_hash", table_name="reconstruction_jobs")
    op.drop_table("reconstruction_jobs")
