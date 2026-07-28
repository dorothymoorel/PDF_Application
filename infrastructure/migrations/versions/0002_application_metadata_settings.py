"""Create application metadata and settings tables.

Revision ID: 0002_application_settings
Revises: 0001_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_application_settings"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORIES = "'GENERAL', 'STORAGE', 'TRANSLATION', 'OCR', 'RECONSTRUCTION', 'BACKUP', 'ADVANCED'"


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        sqlite_strict=True,
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "json_valid(value_json)",
            name="ck_app_settings_value_json_valid",
        ),
        sa.CheckConstraint(
            f"category IN ({_CATEGORIES})",
            name="ck_app_settings_category",
        ),
        sa.CheckConstraint(
            "(key = 'translation_batch_size' AND category = 'TRANSLATION') OR "
            "(key = 'ocr_concurrency' AND category = 'OCR')",
            name="ck_app_settings_key_category",
        ),
        sa.PrimaryKeyConstraint("key"),
        sqlite_strict=True,
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("app_metadata")
