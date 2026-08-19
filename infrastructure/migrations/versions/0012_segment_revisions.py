"""Create append-only segment revision history.

Revision ID: 0012_segment_revisions
Revises: 0011_translation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_segment_revisions"
down_revision: str | Sequence[str] | None = "0011_translation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVISION_TYPES = (
    "'MACHINE_TRANSLATION', 'AUTOMATIC_RETRY', 'GLOSSARY_REAPPLICATION', 'USER_EDIT', "
    "'APPROVE', 'UNAPPROVE', 'LOCK', 'UNLOCK', 'RESTORE_VERSION'"
)


def upgrade() -> None:
    op.create_table(
        "segment_revisions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_type", sa.Text(), nullable=False),
        sa.Column("previous_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=False),
        sa.Column("source_translation_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number >= 1", name="ck_segment_revisions_number"),
        sa.CheckConstraint(
            f"revision_type IN ({_REVISION_TYPES})",
            name="ck_segment_revisions_type",
        ),
        sa.CheckConstraint(
            "new_text IS NOT NULL AND trim(new_text) <> ''",
            name="ck_segment_revisions_new_text",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_segment_revisions_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["document_segments.id"],
            name="fk_segment_revisions_segment_id_document_segments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_translation_id"],
            ["segment_translations.id"],
            name="fk_segment_revisions_source_translation_id_segment_translations",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_segment_revisions_number",
        "segment_revisions",
        ["segment_id", "revision_number"],
        unique=True,
    )
    op.execute(
        "CREATE TRIGGER trg_segment_revisions_no_update "
        "BEFORE UPDATE ON segment_revisions "
        "BEGIN SELECT RAISE(ABORT, 'segment revisions are append-only'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_segment_revisions_no_update")
    op.drop_index("uq_segment_revisions_number", table_name="segment_revisions")
    op.drop_table("segment_revisions")
