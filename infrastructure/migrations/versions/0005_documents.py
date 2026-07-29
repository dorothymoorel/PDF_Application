"""Create the documents table.

Revision ID: 0005_documents
Revises: 0004_stored_files
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_documents"
down_revision: str | Sequence[str] | None = "0004_stored_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOCUMENT_TYPES = (
    "'ACADEMIC_PAPER', 'ACADEMIC_BOOK', 'TECHNICAL_BOOK', 'USER_MANUAL', "
    "'BUSINESS_REPORT', 'LEGAL_DOCUMENT', 'FICTION_BOOK', 'NONFICTION_BOOK', "
    "'PRESENTATION_EXPORT', 'BROCHURE', 'FORM', 'COMIC_OR_GRAPHIC_BOOK', "
    "'GENERAL_DOCUMENT', 'UNKNOWN'"
)
_DOCUMENT_CLASSES = (
    "'DIGITAL_PDF', 'SCANNED_PDF', 'HYBRID_PDF', 'UNSUPPORTED', 'CORRUPTED', 'PASSWORD_PROTECTED'"
)
_DOCUMENT_STATUSES = (
    "'CREATED', 'ANALYZED', 'EXTRACTED', 'OCR_PARTIAL', 'OCR_COMPLETE', "
    "'STRUCTURED', 'TERMS_DETECTED', 'READY_FOR_TRANSLATION', 'TRANSLATING', "
    "'TRANSLATED', 'PARTIALLY_TRANSLATED', 'REVIEWING', 'REVIEWED', "
    "'RECONSTRUCTING', 'RECONSTRUCTED', 'QUALITY_CHECKED', 'READY_FOR_EXPORT', "
    "'EXPORTED', 'FAILED', 'ARCHIVED'"
)
_FILE_ROLES = (
    "'ORIGINAL', 'PAGE_RENDER', 'THUMBNAIL', 'EXTRACTED_ASSET', 'OCR_INPUT', "
    "'OCR_OUTPUT', 'IR_SNAPSHOT', 'RECONSTRUCTED_PAGE', 'EXPORT', 'BACKUP', "
    "'TEMPORARY', 'BENCHMARK_REPORT'"
)
_FILE_STATUSES = (
    "'CREATED', 'AVAILABLE', 'VALIDATED', 'MISSING', 'CORRUPTED', 'DELETION_QUEUED', 'DELETED'"
)
_STORED_FILE_DOCUMENT_FK = "fk_stored_files_document_id_documents"


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("original_file_id", sa.Text(), nullable=False),
        sa.Column("ir_version", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("document_class", sa.Text(), nullable=False),
        sa.Column("source_language", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("word_count_estimate", sa.Integer(), nullable=True),
        sa.Column("has_text_layer", sa.Integer(), nullable=False),
        sa.Column("scanned_page_count", sa.Integer(), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("analysis_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'doc_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_documents_prefixed_uuid",
        ),
        sa.CheckConstraint("trim(ir_version) <> ''", name="ck_documents_ir_version"),
        sa.CheckConstraint(
            f"document_type IN ({_DOCUMENT_TYPES})",
            name="ck_documents_type",
        ),
        sa.CheckConstraint(
            f"document_class IN ({_DOCUMENT_CLASSES})",
            name="ck_documents_class",
        ),
        sa.CheckConstraint(
            "trim(source_language) <> ''",
            name="ck_documents_source_language",
        ),
        sa.CheckConstraint(
            "trim(target_language) <> ''",
            name="ck_documents_target_language",
        ),
        sa.CheckConstraint("page_count >= 0", name="ck_documents_page_count"),
        sa.CheckConstraint(
            "word_count_estimate IS NULL OR word_count_estimate >= 0",
            name="ck_documents_word_count",
        ),
        sa.CheckConstraint(
            "has_text_layer IN (0, 1)",
            name="ck_documents_has_text_layer",
        ),
        sa.CheckConstraint(
            "scanned_page_count >= 0 AND scanned_page_count <= page_count",
            name="ck_documents_scanned_page_count",
        ),
        sa.CheckConstraint("image_count >= 0", name="ck_documents_image_count"),
        sa.CheckConstraint("table_count >= 0", name="ck_documents_table_count"),
        sa.CheckConstraint(
            f"status IN ({_DOCUMENT_STATUSES})",
            name="ck_documents_status",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_documents_metadata_json_valid",
        ),
        sa.CheckConstraint(
            "analysis_json IS NULL OR json_valid(analysis_json)",
            name="ck_documents_analysis_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_documents_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["original_file_id"],
            ["stored_files.id"],
            name="fk_documents_original_file_id_stored_files",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_documents_project_original_file",
        "documents",
        ["project_id", "original_file_id"],
        unique=True,
    )

    with op.batch_alter_table(
        "stored_files",
        recreate="always",
        copy_from=_stored_files_table(include_document_fk=False),
    ) as batch_op:
        batch_op.create_foreign_key(
            _STORED_FILE_DOCUMENT_FK,
            "documents",
            ["document_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Documents are removed by this downgrade; clear their back-references first.
    op.execute(sa.text("DELETE FROM documents"))
    with op.batch_alter_table(
        "stored_files",
        recreate="always",
        copy_from=_stored_files_table(include_document_fk=True),
    ) as batch_op:
        batch_op.drop_constraint(_STORED_FILE_DOCUMENT_FK, type_="foreignkey")

    op.drop_index("uq_documents_project_original_file", table_name="documents")
    op.drop_table("documents")


def _stored_files_table(*, include_document_fk: bool) -> sa.Table:
    metadata = sa.MetaData()
    constraints: list[sa.Constraint] = [
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
        sa.PrimaryKeyConstraint("id"),
    ]
    if include_document_fk:
        constraints.append(
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["documents.id"],
                name=_STORED_FILE_DOCUMENT_FK,
                ondelete="SET NULL",
            )
        )

    table = sa.Table(
        "stored_files",
        metadata,
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
        *constraints,
        sqlite_strict=True,
    )
    sa.Index("uq_stored_files_storage_key", table.c.storage_key, unique=True)
    sa.Index("ix_stored_files_project_role", table.c.project_id, table.c.file_role)
    sa.Index("ix_stored_files_checksum", table.c.checksum_sha256)
    return table
