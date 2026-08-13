"""Create local model persistence.

Revision ID: 0010_local_models
Revises: 0009_glossary
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_local_models"
down_revision: str | Sequence[str] | None = "0009_glossary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LICENSE_STATUSES = (
    "'APPROVED', 'APPROVED_FOR_PERSONAL_USE', 'REVIEW_REQUIRED', 'REJECTED', 'UNKNOWN'"
)


def upgrade() -> None:
    op.create_table(
        "local_models",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("ollama_model_name", sa.Text(), nullable=False),
        sa.Column("model_family", sa.Text(), nullable=True),
        sa.Column("parameter_class", sa.Text(), nullable=True),
        sa.Column("quantization", sa.Text(), nullable=True),
        sa.Column("disk_size_bytes", sa.Integer(), nullable=True),
        sa.Column("license_name", sa.Text(), nullable=True),
        sa.Column("license_status", sa.Text(), nullable=False),
        sa.Column("is_installed", sa.Integer(), nullable=False),
        sa.Column("is_selected_translation", sa.Integer(), nullable=False),
        sa.Column("is_selected_validation", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("last_detected_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'mdl_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_local_models_prefixed_uuid",
        ),
        sa.CheckConstraint(
            "trim(ollama_model_name) <> ''",
            name="ck_local_models_name",
        ),
        sa.CheckConstraint(
            "disk_size_bytes IS NULL OR disk_size_bytes >= 0",
            name="ck_local_models_disk_size",
        ),
        sa.CheckConstraint(
            f"license_status IN ({_LICENSE_STATUSES})",
            name="ck_local_models_license_status",
        ),
        sa.CheckConstraint(
            "is_installed IN (0, 1)",
            name="ck_local_models_installed",
        ),
        sa.CheckConstraint(
            "is_selected_translation IN (0, 1)",
            name="ck_local_models_selected_translation",
        ),
        sa.CheckConstraint(
            "is_selected_validation IN (0, 1)",
            name="ck_local_models_selected_validation",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_local_models_metadata_json_valid",
        ),
        sa.CheckConstraint(
            "trim(last_detected_at) <> ''",
            name="ck_local_models_last_detected",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_local_models_ollama_name",
        "local_models",
        ["ollama_model_name"],
        unique=True,
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_local_models_selected_translation "
        "ON local_models(is_selected_translation) WHERE is_selected_translation = 1"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_local_models_selected_validation "
        "ON local_models(is_selected_validation) WHERE is_selected_validation = 1"
    )


def downgrade() -> None:
    op.drop_index("uq_local_models_selected_validation", table_name="local_models")
    op.drop_index("uq_local_models_selected_translation", table_name="local_models")
    op.drop_index("uq_local_models_ollama_name", table_name="local_models")
    op.drop_table("local_models")
