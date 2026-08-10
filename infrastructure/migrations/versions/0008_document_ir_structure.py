"""Create the persisted Document IR structure.

Revision ID: 0008_document_ir_structure
Revises: 0007_document_pages
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_document_ir_structure"
down_revision: str | Sequence[str] | None = "0007_document_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SECTION_TYPES = (
    "FRONT_MATTER",
    "PREFACE",
    "TABLE_OF_CONTENTS",
    "PART",
    "CHAPTER",
    "SECTION",
    "SUBSECTION",
    "APPENDIX",
    "BIBLIOGRAPHY",
    "INDEX",
    "BACK_MATTER",
    "UNKNOWN",
)
_BLOCK_TYPES = (
    "DOCUMENT_TITLE",
    "SUBTITLE",
    "HEADING_1",
    "HEADING_2",
    "HEADING_3",
    "HEADING_4",
    "HEADING_5",
    "HEADING_6",
    "PARAGRAPH",
    "BLOCKQUOTE",
    "LIST",
    "LIST_ITEM",
    "TABLE",
    "TABLE_ROW",
    "TABLE_CELL",
    "IMAGE",
    "FIGURE",
    "CAPTION",
    "HEADER",
    "FOOTER",
    "PAGE_NUMBER",
    "FOOTNOTE",
    "ENDNOTE",
    "CODE_BLOCK",
    "INLINE_CODE_CONTAINER",
    "FORMULA",
    "EQUATION_LABEL",
    "BIBLIOGRAPHY_ENTRY",
    "INDEX_ENTRY",
    "TABLE_OF_CONTENTS_ENTRY",
    "SIDEBAR",
    "CALLOUT",
    "TEXTBOX",
    "FORM_FIELD",
    "SIGNATURE_FIELD",
    "DECORATIVE_TEXT",
    "UNKNOWN",
)
_SEMANTIC_ROLES = (
    "TITLE",
    "CHAPTER_TITLE",
    "SECTION_TITLE",
    "BODY_TEXT",
    "DEFINITION",
    "EXAMPLE",
    "WARNING",
    "NOTE",
    "TIP",
    "QUOTE",
    "CAPTION",
    "REFERENCE",
    "CODE",
    "FORMULA",
    "NAVIGATION",
    "DECORATION",
)
_DOCUMENT_STATUSES = (
    "CREATED",
    "ANALYZED",
    "EXTRACTED",
    "OCR_PARTIAL",
    "OCR_COMPLETE",
    "STRUCTURED",
    "TERMS_DETECTED",
    "READY_FOR_TRANSLATION",
    "TRANSLATING",
    "TRANSLATED",
    "PARTIALLY_TRANSLATED",
    "REVIEWING",
    "REVIEWED",
    "RECONSTRUCTING",
    "RECONSTRUCTED",
    "QUALITY_CHECKED",
    "READY_FOR_EXPORT",
    "EXPORTED",
    "FAILED",
    "ARCHIVED",
)
_SEGMENT_STATUSES = (
    "CREATED",
    "EXTRACTED",
    "OCR_REQUIRED",
    "OCR_COMPLETED",
    "NORMALIZED",
    "TERMS_DETECTED",
    "PROTECTED",
    "READY_FOR_TRANSLATION",
    "TRANSLATING",
    "MACHINE_TRANSLATED",
    "TRANSLATION_FAILED",
    "NEEDS_REVIEW",
    "USER_EDITED",
    "APPROVED",
    "LOCKED",
    "IGNORED",
    "NOT_TRANSLATABLE",
)
_REVIEW_STATUSES = (
    "NOT_REVIEWED",
    "REVIEW_REQUIRED",
    "IN_REVIEW",
    "EDITED",
    "APPROVED",
    "REJECTED",
)
_ASSET_TYPES = (
    "RASTER_IMAGE",
    "VECTOR_IMAGE",
    "CHART",
    "DIAGRAM",
    "LOGO",
    "ICON",
    "BACKGROUND",
    "DECORATIVE_ELEMENT",
    "FONT",
    "EMBEDDED_FILE",
    "UNKNOWN",
)
_ASSET_POLICIES = (
    "KEEP_UNCHANGED",
    "RECOMPRESS_LOSSLESS",
    "RECOMPRESS_STANDARD",
    "RENDER_AS_IMAGE",
    "REPLACE_WITH_TRANSLATED_VERSION",
    "REMOVE",
)
_TABLE_COMPLEXITIES = ("SIMPLE", "MODERATE", "COMPLEX", "UNRECOGNIZED")
_CELL_ROLES = ("HEADER", "ROW_HEADER", "DATA")
_ANNOTATION_TYPES = (
    "HYPERLINK",
    "INTERNAL_LINK",
    "COMMENT",
    "HIGHLIGHT",
    "UNDERLINE",
    "STRIKEOUT",
    "STAMP",
    "FORM_FIELD",
    "BOOKMARK",
)
_RELATIONSHIP_TYPES = (
    "CAPTION_OF",
    "FOOTNOTE_OF",
    "CONTINUATION_OF",
    "CHILD_OF",
    "REFERENCES",
    "LINKS_TO",
    "LABEL_OF",
    "HEADER_FOR",
    "BELONGS_TO_SECTION",
    "PRECEDES",
    "FOLLOWS",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _prefixed_uuid(prefix: str, table_name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


def upgrade() -> None:
    op.create_table(
        "document_sections",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("parent_section_id", sa.Text(), nullable=True),
        sa.Column("section_type", sa.Text(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("section_order", sa.Integer(), nullable=False),
        sa.Column("title_segment_id", sa.Text(), nullable=True),
        sa.Column("start_page_id", sa.Text(), nullable=True),
        sa.Column("end_page_id", sa.Text(), nullable=True),
        sa.Column("source_summary", sa.Text(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("sec_", "document_sections"),
        sa.CheckConstraint(
            f"section_type IN ({_values(_SECTION_TYPES)})",
            name="ck_document_sections_type",
        ),
        sa.CheckConstraint("level >= 0", name="ck_document_sections_level"),
        sa.CheckConstraint(
            "section_order >= 0",
            name="ck_document_sections_order",
        ),
        sa.CheckConstraint(
            "context_json IS NULL OR json_valid(context_json)",
            name="ck_document_sections_context_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_sections_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_section_id"],
            ["document_sections.id"],
            name="fk_document_sections_parent_section_id_document_sections",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_document_sections_order",
        "document_sections",
        ["document_id", "section_order"],
        unique=True,
    )

    op.create_table(
        "document_blocks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=True),
        sa.Column("parent_block_id", sa.Text(), nullable=True),
        sa.Column("block_type", sa.Text(), nullable=False),
        sa.Column("semantic_role", sa.Text(), nullable=True),
        sa.Column("page_reading_order", sa.Integer(), nullable=False),
        sa.Column("global_reading_order", sa.Integer(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("normalized_source_text", sa.Text(), nullable=True),
        sa.Column("source_geometry_json", sa.Text(), nullable=False),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("style_json", sa.Text(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("blk_", "document_blocks"),
        sa.CheckConstraint(
            f"block_type IN ({_values(_BLOCK_TYPES)})",
            name="ck_document_blocks_type",
        ),
        sa.CheckConstraint(
            f"semantic_role IS NULL OR semantic_role IN ({_values(_SEMANTIC_ROLES)})",
            name="ck_document_blocks_semantic_role",
        ),
        sa.CheckConstraint(
            "page_reading_order >= 0",
            name="ck_document_blocks_page_order",
        ),
        sa.CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_blocks_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_blocks_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "style_json IS NULL OR json_valid(style_json)",
            name="ck_document_blocks_style_json_valid",
        ),
        sa.CheckConstraint(
            "detail_json IS NULL OR json_valid(detail_json)",
            name="ck_document_blocks_detail_json_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_values(_DOCUMENT_STATUSES)})",
            name="ck_document_blocks_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_blocks_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_document_blocks_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            name="fk_document_blocks_section_id_document_sections",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_block_id"],
            ["document_blocks.id"],
            name="fk_document_blocks_parent_block_id_document_blocks",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_document_blocks_page_order",
        "document_blocks",
        ["page_id", "page_reading_order"],
        unique=True,
    )
    op.create_index(
        "ix_document_blocks_page_type",
        "document_blocks",
        ["page_id", "block_type"],
    )
    op.create_index(
        "ix_document_blocks_section",
        "document_blocks",
        ["section_id", "global_reading_order"],
    )

    op.create_table(
        "document_segments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("block_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=True),
        sa.Column("segment_order", sa.Integer(), nullable=False),
        sa.Column("global_order", sa.Integer(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("native_text", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("resolved_source_text", sa.Text(), nullable=False),
        sa.Column("normalized_source_text", sa.Text(), nullable=False),
        sa.Column("protected_source_text", sa.Text(), nullable=True),
        sa.Column("machine_translation", sa.Text(), nullable=True),
        sa.Column("reviewed_translation", sa.Text(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("is_locked", sa.Integer(), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("confidence_overall", sa.REAL(), nullable=True),
        sa.Column("confidence_json", sa.Text(), nullable=True),
        sa.Column("translation_settings_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("seg_", "document_segments"),
        sa.CheckConstraint(
            "segment_order >= 0",
            name="ck_document_segments_order",
        ),
        sa.CheckConstraint(
            f"status IN ({_values(_SEGMENT_STATUSES)})",
            name="ck_document_segments_status",
        ),
        sa.CheckConstraint(
            f"review_status IN ({_values(_REVIEW_STATUSES)})",
            name="ck_document_segments_review_status",
        ),
        sa.CheckConstraint(
            "is_locked IN (0, 1)",
            name="ck_document_segments_is_locked",
        ),
        sa.CheckConstraint(
            "current_revision >= 0",
            name="ck_document_segments_revision",
        ),
        sa.CheckConstraint(
            "confidence_overall IS NULL OR confidence_overall BETWEEN 0.0 AND 1.0",
            name="ck_document_segments_confidence",
        ),
        sa.CheckConstraint(
            "confidence_json IS NULL OR json_valid(confidence_json)",
            name="ck_document_segments_confidence_json_valid",
        ),
        sa.CheckConstraint(
            "trim(source_language) <> '' AND trim(target_language) <> ''",
            name="ck_document_segments_languages",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.id"],
            name="fk_document_segments_block_id_document_blocks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            name="fk_document_segments_section_id_document_sections",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_document_segments_block_order",
        "document_segments",
        ["block_id", "segment_order"],
        unique=True,
    )
    op.create_index("ix_document_segments_status", "document_segments", ["status"])
    op.create_index(
        "ix_document_segments_review_status",
        "document_segments",
        ["review_status"],
    )
    op.create_index(
        "ix_document_segments_section_order",
        "document_segments",
        ["section_id", "global_order"],
    )
    op.create_index("ix_document_segments_block", "document_segments", ["block_id"])

    op.create_table(
        "document_assets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=False),
        sa.Column("source_geometry_json", sa.Text(), nullable=True),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("width_pixels", sa.Integer(), nullable=True),
        sa.Column("height_pixels", sa.Integer(), nullable=True),
        sa.Column("dpi", sa.REAL(), nullable=True),
        sa.Column("rotation_degrees", sa.REAL(), nullable=False),
        sa.Column("z_index", sa.Integer(), nullable=False),
        sa.Column("caption_block_id", sa.Text(), nullable=True),
        sa.Column("preservation_policy", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("ast_", "document_assets"),
        sa.CheckConstraint(
            f"asset_type IN ({_values(_ASSET_TYPES)})",
            name="ck_document_assets_type",
        ),
        sa.CheckConstraint(
            "source_geometry_json IS NULL OR json_valid(source_geometry_json)",
            name="ck_document_assets_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_assets_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "width_pixels IS NULL OR width_pixels >= 0",
            name="ck_document_assets_width",
        ),
        sa.CheckConstraint(
            "height_pixels IS NULL OR height_pixels >= 0",
            name="ck_document_assets_height",
        ),
        sa.CheckConstraint(
            f"preservation_policy IN ({_values(_ASSET_POLICIES)})",
            name="ck_document_assets_preservation_policy",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_assets_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_assets_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_document_assets_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_files.id"],
            name="fk_document_assets_file_id_stored_files",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index("ix_document_assets_page", "document_assets", ["page_id"])
    op.create_index(
        "ix_document_assets_type",
        "document_assets",
        ["document_id", "asset_type"],
    )

    op.create_table(
        "document_tables",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("block_id", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("complexity", sa.Text(), nullable=False),
        sa.Column("has_header_row", sa.Integer(), nullable=False),
        sa.Column("has_header_column", sa.Integer(), nullable=False),
        sa.Column("source_geometry_json", sa.Text(), nullable=False),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("continuation_of_table_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("tbl_", "document_tables"),
        sa.CheckConstraint("row_count >= 0", name="ck_document_tables_rows"),
        sa.CheckConstraint("column_count >= 0", name="ck_document_tables_columns"),
        sa.CheckConstraint(
            f"complexity IN ({_values(_TABLE_COMPLEXITIES)})",
            name="ck_document_tables_complexity",
        ),
        sa.CheckConstraint(
            "has_header_row IN (0, 1)",
            name="ck_document_tables_header_row",
        ),
        sa.CheckConstraint(
            "has_header_column IN (0, 1)",
            name="ck_document_tables_header_column",
        ),
        sa.CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_tables_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_tables_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_values(_DOCUMENT_STATUSES)})",
            name="ck_document_tables_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_tables_confidence",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_tables_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.id"],
            name="fk_document_tables_block_id_document_blocks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", name="uq_document_tables_block"),
        sqlite_strict=True,
    )

    op.create_table(
        "document_table_cells",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("row_span", sa.Integer(), nullable=False),
        sa.Column("column_span", sa.Integer(), nullable=False),
        sa.Column("cell_role", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.Text(), nullable=True),
        sa.Column("source_geometry_json", sa.Text(), nullable=False),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("style_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("cel_", "document_table_cells"),
        sa.CheckConstraint("row_index >= 0", name="ck_document_table_cells_row"),
        sa.CheckConstraint(
            "column_index >= 0",
            name="ck_document_table_cells_column",
        ),
        sa.CheckConstraint(
            "row_span >= 1",
            name="ck_document_table_cells_row_span",
        ),
        sa.CheckConstraint(
            "column_span >= 1",
            name="ck_document_table_cells_column_span",
        ),
        sa.CheckConstraint(
            f"cell_role IN ({_values(_CELL_ROLES)})",
            name="ck_document_table_cells_role",
        ),
        sa.CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_table_cells_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_table_cells_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "style_json IS NULL OR json_valid(style_json)",
            name="ck_document_table_cells_style_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            ["document_tables.id"],
            name="fk_document_table_cells_table_id_document_tables",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["document_segments.id"],
            name="fk_document_table_cells_segment_id_document_segments",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_document_table_cells_position",
        "document_table_cells",
        ["table_id", "row_index", "column_index"],
        unique=True,
    )

    op.create_table(
        "document_annotations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("annotation_type", sa.Text(), nullable=False),
        sa.Column("source_geometry_json", sa.Text(), nullable=False),
        sa.Column("target_geometry_json", sa.Text(), nullable=True),
        sa.Column("visible_text", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Text(), nullable=True),
        sa.Column("preservation_policy", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("ann_", "document_annotations"),
        sa.CheckConstraint(
            f"annotation_type IN ({_values(_ANNOTATION_TYPES)})",
            name="ck_document_annotations_type",
        ),
        sa.CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_annotations_source_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_annotations_target_geometry_json_valid",
        ),
        sa.CheckConstraint(
            "trim(preservation_policy) <> ''",
            name="ck_document_annotations_preservation_policy",
        ),
        sa.CheckConstraint(
            "trim(status) <> ''",
            name="ck_document_annotations_status",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_annotations_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_document_annotations_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )

    op.create_table(
        "document_relationships",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("relationship_type", sa.Text(), nullable=False),
        sa.Column("source_entity_type", sa.Text(), nullable=False),
        sa.Column("source_entity_id", sa.Text(), nullable=False),
        sa.Column("target_entity_type", sa.Text(), nullable=False),
        sa.Column("target_entity_id", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        _prefixed_uuid("rel_", "document_relationships"),
        sa.CheckConstraint(
            f"relationship_type IN ({_values(_RELATIONSHIP_TYPES)})",
            name="ck_document_relationships_type",
        ),
        sa.CheckConstraint(
            "trim(source_entity_type) <> '' AND trim(source_entity_id) <> '' "
            "AND trim(target_entity_type) <> '' AND trim(target_entity_id) <> ''",
            name="ck_document_relationships_endpoints",
        ),
        sa.CheckConstraint(
            "source_entity_type <> target_entity_type OR source_entity_id <> target_entity_id",
            name="ck_document_relationships_distinct_endpoints",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_relationships_confidence",
        ),
        sa.CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_relationships_metadata_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_relationships_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )


def downgrade() -> None:
    op.drop_table("document_relationships")
    op.drop_table("document_annotations")
    op.drop_index(
        "uq_document_table_cells_position",
        table_name="document_table_cells",
    )
    op.drop_table("document_table_cells")
    op.drop_table("document_tables")
    op.drop_index("ix_document_assets_type", table_name="document_assets")
    op.drop_index("ix_document_assets_page", table_name="document_assets")
    op.drop_table("document_assets")
    op.drop_index("ix_document_segments_block", table_name="document_segments")
    op.drop_index(
        "ix_document_segments_section_order",
        table_name="document_segments",
    )
    op.drop_index(
        "ix_document_segments_review_status",
        table_name="document_segments",
    )
    op.drop_index("ix_document_segments_status", table_name="document_segments")
    op.drop_index(
        "uq_document_segments_block_order",
        table_name="document_segments",
    )
    op.drop_table("document_segments")
    op.drop_index("ix_document_blocks_section", table_name="document_blocks")
    op.drop_index("ix_document_blocks_page_type", table_name="document_blocks")
    op.drop_index(
        "uq_document_blocks_page_order",
        table_name="document_blocks",
    )
    op.drop_table("document_blocks")
    op.drop_index(
        "uq_document_sections_order",
        table_name="document_sections",
    )
    op.drop_table("document_sections")
