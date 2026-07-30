"""Create the document pages table.

Revision ID: 0007_document_pages
Revises: 0006_application_jobs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_document_pages"
down_revision: str | Sequence[str] | None = "0006_application_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAGE_TYPES = (
    "'DIGITAL', 'SCANNED', 'HYBRID', 'IMAGE_ONLY', 'FORM', 'COVER', "
    "'TABLE_OF_CONTENTS', 'INDEX', 'BIBLIOGRAPHY', 'BLANK', 'UNKNOWN'"
)


def upgrade() -> None:
    op.create_table(
        "document_pages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_page_number", sa.Integer(), nullable=False),
        sa.Column("logical_page_number", sa.Text(), nullable=True),
        sa.Column("width_points", sa.REAL(), nullable=False),
        sa.Column("height_points", sa.REAL(), nullable=False),
        sa.Column("rotation_degrees", sa.REAL(), nullable=False),
        sa.Column("page_type", sa.Text(), nullable=False),
        sa.Column("page_classification", sa.Text(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("reading_direction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("render_file_id", sa.Text(), nullable=True),
        sa.Column("thumbnail_file_id", sa.Text(), nullable=True),
        sa.Column("native_extraction_confidence", sa.REAL(), nullable=True),
        sa.Column("ocr_confidence", sa.REAL(), nullable=True),
        sa.Column("structure_confidence", sa.REAL(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'pag_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_document_pages_prefixed_uuid",
        ),
        sa.CheckConstraint(
            "source_page_number >= 1",
            name="ck_document_pages_source_number",
        ),
        sa.CheckConstraint(
            "width_points > 0 AND height_points > 0",
            name="ck_document_pages_geometry",
        ),
        sa.CheckConstraint(
            "rotation_degrees IN (0.0, 90.0, 180.0, 270.0)",
            name="ck_document_pages_rotation",
        ),
        sa.CheckConstraint(
            f"page_type IN ({_PAGE_TYPES})",
            name="ck_document_pages_type",
        ),
        sa.CheckConstraint(
            "column_count >= 0",
            name="ck_document_pages_column_count",
        ),
        sa.CheckConstraint(
            "trim(reading_direction) <> ''",
            name="ck_document_pages_reading_direction",
        ),
        sa.CheckConstraint(
            "trim(status) <> ''",
            name="ck_document_pages_status",
        ),
        sa.CheckConstraint(
            "native_extraction_confidence IS NULL "
            "OR native_extraction_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_native_confidence",
        ),
        sa.CheckConstraint(
            "ocr_confidence IS NULL OR ocr_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_ocr_confidence",
        ),
        sa.CheckConstraint(
            "structure_confidence IS NULL OR structure_confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_pages_structure_confidence",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_pages_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_pages_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["render_file_id"],
            ["stored_files.id"],
            name="fk_document_pages_render_file_id_stored_files",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["thumbnail_file_id"],
            ["stored_files.id"],
            name="fk_document_pages_thumbnail_file_id_stored_files",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_document_pages_number",
        "document_pages",
        ["document_id", "source_page_number"],
        unique=True,
    )
    op.create_index(
        "ix_document_pages_status",
        "document_pages",
        ["document_id", "status"],
    )
    op.create_index(
        "ix_document_pages_type",
        "document_pages",
        ["document_id", "page_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_pages_type", table_name="document_pages")
    op.drop_index("ix_document_pages_status", table_name="document_pages")
    op.drop_index("uq_document_pages_number", table_name="document_pages")
    op.drop_table("document_pages")
