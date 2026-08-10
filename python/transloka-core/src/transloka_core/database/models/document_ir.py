from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.documents import DocumentStatus


class SectionType(StrEnum):
    FRONT_MATTER = "FRONT_MATTER"
    PREFACE = "PREFACE"
    TABLE_OF_CONTENTS = "TABLE_OF_CONTENTS"
    PART = "PART"
    CHAPTER = "CHAPTER"
    SECTION = "SECTION"
    SUBSECTION = "SUBSECTION"
    APPENDIX = "APPENDIX"
    BIBLIOGRAPHY = "BIBLIOGRAPHY"
    INDEX = "INDEX"
    BACK_MATTER = "BACK_MATTER"
    UNKNOWN = "UNKNOWN"


class BlockType(StrEnum):
    DOCUMENT_TITLE = "DOCUMENT_TITLE"
    SUBTITLE = "SUBTITLE"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    HEADING_4 = "HEADING_4"
    HEADING_5 = "HEADING_5"
    HEADING_6 = "HEADING_6"
    PARAGRAPH = "PARAGRAPH"
    BLOCKQUOTE = "BLOCKQUOTE"
    LIST = "LIST"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    IMAGE = "IMAGE"
    FIGURE = "FIGURE"
    CAPTION = "CAPTION"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    FOOTNOTE = "FOOTNOTE"
    ENDNOTE = "ENDNOTE"
    CODE_BLOCK = "CODE_BLOCK"
    INLINE_CODE_CONTAINER = "INLINE_CODE_CONTAINER"
    FORMULA = "FORMULA"
    EQUATION_LABEL = "EQUATION_LABEL"
    BIBLIOGRAPHY_ENTRY = "BIBLIOGRAPHY_ENTRY"
    INDEX_ENTRY = "INDEX_ENTRY"
    TABLE_OF_CONTENTS_ENTRY = "TABLE_OF_CONTENTS_ENTRY"
    SIDEBAR = "SIDEBAR"
    CALLOUT = "CALLOUT"
    TEXTBOX = "TEXTBOX"
    FORM_FIELD = "FORM_FIELD"
    SIGNATURE_FIELD = "SIGNATURE_FIELD"
    DECORATIVE_TEXT = "DECORATIVE_TEXT"
    UNKNOWN = "UNKNOWN"


class SemanticRole(StrEnum):
    TITLE = "TITLE"
    CHAPTER_TITLE = "CHAPTER_TITLE"
    SECTION_TITLE = "SECTION_TITLE"
    BODY_TEXT = "BODY_TEXT"
    DEFINITION = "DEFINITION"
    EXAMPLE = "EXAMPLE"
    WARNING = "WARNING"
    NOTE = "NOTE"
    TIP = "TIP"
    QUOTE = "QUOTE"
    CAPTION = "CAPTION"
    REFERENCE = "REFERENCE"
    CODE = "CODE"
    FORMULA = "FORMULA"
    NAVIGATION = "NAVIGATION"
    DECORATION = "DECORATION"


class SegmentStatus(StrEnum):
    CREATED = "CREATED"
    EXTRACTED = "EXTRACTED"
    OCR_REQUIRED = "OCR_REQUIRED"
    OCR_COMPLETED = "OCR_COMPLETED"
    NORMALIZED = "NORMALIZED"
    TERMS_DETECTED = "TERMS_DETECTED"
    PROTECTED = "PROTECTED"
    READY_FOR_TRANSLATION = "READY_FOR_TRANSLATION"
    TRANSLATING = "TRANSLATING"
    MACHINE_TRANSLATED = "MACHINE_TRANSLATED"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    USER_EDITED = "USER_EDITED"
    APPROVED = "APPROVED"
    LOCKED = "LOCKED"
    IGNORED = "IGNORED"
    NOT_TRANSLATABLE = "NOT_TRANSLATABLE"


class ReviewStatus(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    IN_REVIEW = "IN_REVIEW"
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AssetType(StrEnum):
    RASTER_IMAGE = "RASTER_IMAGE"
    VECTOR_IMAGE = "VECTOR_IMAGE"
    CHART = "CHART"
    DIAGRAM = "DIAGRAM"
    LOGO = "LOGO"
    ICON = "ICON"
    BACKGROUND = "BACKGROUND"
    DECORATIVE_ELEMENT = "DECORATIVE_ELEMENT"
    FONT = "FONT"
    EMBEDDED_FILE = "EMBEDDED_FILE"
    UNKNOWN = "UNKNOWN"


class AssetPreservationPolicy(StrEnum):
    KEEP_UNCHANGED = "KEEP_UNCHANGED"
    RECOMPRESS_LOSSLESS = "RECOMPRESS_LOSSLESS"
    RECOMPRESS_STANDARD = "RECOMPRESS_STANDARD"
    RENDER_AS_IMAGE = "RENDER_AS_IMAGE"
    REPLACE_WITH_TRANSLATED_VERSION = "REPLACE_WITH_TRANSLATED_VERSION"
    REMOVE = "REMOVE"


class TableComplexity(StrEnum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    COMPLEX = "COMPLEX"
    UNRECOGNIZED = "UNRECOGNIZED"


class CellRole(StrEnum):
    HEADER = "HEADER"
    ROW_HEADER = "ROW_HEADER"
    DATA = "DATA"


class AnnotationType(StrEnum):
    HYPERLINK = "HYPERLINK"
    INTERNAL_LINK = "INTERNAL_LINK"
    COMMENT = "COMMENT"
    HIGHLIGHT = "HIGHLIGHT"
    UNDERLINE = "UNDERLINE"
    STRIKEOUT = "STRIKEOUT"
    STAMP = "STAMP"
    FORM_FIELD = "FORM_FIELD"
    BOOKMARK = "BOOKMARK"


class RelationshipType(StrEnum):
    CAPTION_OF = "CAPTION_OF"
    FOOTNOTE_OF = "FOOTNOTE_OF"
    CONTINUATION_OF = "CONTINUATION_OF"
    CHILD_OF = "CHILD_OF"
    REFERENCES = "REFERENCES"
    LINKS_TO = "LINKS_TO"
    LABEL_OF = "LABEL_OF"
    HEADER_FOR = "HEADER_FOR"
    BELONGS_TO_SECTION = "BELONGS_TO_SECTION"
    PRECEDES = "PRECEDES"
    FOLLOWS = "FOLLOWS"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


def _prefixed_uuid(prefix: str, table_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


class DocumentSection(Base):
    __tablename__ = "document_sections"
    __table_args__ = (
        _prefixed_uuid("sec_", "document_sections"),
        CheckConstraint(
            f"section_type IN ({_sql_values(SectionType)})",
            name="ck_document_sections_type",
        ),
        CheckConstraint("level >= 0", name="ck_document_sections_level"),
        CheckConstraint(
            "section_order >= 0",
            name="ck_document_sections_order",
        ),
        CheckConstraint(
            "context_json IS NULL OR json_valid(context_json)",
            name="ck_document_sections_context_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_section_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    section_type: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title_segment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_page_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentBlock(Base):
    __tablename__ = "document_blocks"
    __table_args__ = (
        _prefixed_uuid("blk_", "document_blocks"),
        CheckConstraint(
            f"block_type IN ({_sql_values(BlockType)})",
            name="ck_document_blocks_type",
        ),
        CheckConstraint(
            f"semantic_role IS NULL OR semantic_role IN ({_sql_values(SemanticRole)})",
            name="ck_document_blocks_semantic_role",
        ),
        CheckConstraint(
            "page_reading_order >= 0",
            name="ck_document_blocks_page_order",
        ),
        CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_blocks_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_blocks_target_geometry_json_valid",
        ),
        CheckConstraint(
            "style_json IS NULL OR json_valid(style_json)",
            name="ck_document_blocks_style_json_valid",
        ),
        CheckConstraint(
            "detail_json IS NULL OR json_valid(detail_json)",
            name="ck_document_blocks_detail_json_valid",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(DocumentStatus)})",
            name="ck_document_blocks_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_blocks_confidence",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_block_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_blocks.id", ondelete="SET NULL"),
        nullable=True,
    )
    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    global_reading_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_geometry_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentSegment(Base):
    __tablename__ = "document_segments"
    __table_args__ = (
        _prefixed_uuid("seg_", "document_segments"),
        CheckConstraint(
            "segment_order >= 0",
            name="ck_document_segments_order",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(SegmentStatus)})",
            name="ck_document_segments_status",
        ),
        CheckConstraint(
            f"review_status IN ({_sql_values(ReviewStatus)})",
            name="ck_document_segments_review_status",
        ),
        CheckConstraint(
            "is_locked IN (0, 1)",
            name="ck_document_segments_is_locked",
        ),
        CheckConstraint(
            "current_revision >= 0",
            name="ck_document_segments_revision",
        ),
        CheckConstraint(
            "confidence_overall IS NULL OR confidence_overall BETWEEN 0.0 AND 1.0",
            name="ck_document_segments_confidence",
        ),
        CheckConstraint(
            "confidence_json IS NULL OR json_valid(confidence_json)",
            name="ck_document_segments_confidence_json_valid",
        ),
        CheckConstraint(
            "trim(source_language) <> '' AND trim(target_language) <> ''",
            name="ck_document_segments_languages",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    block_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    global_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    native_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_source_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_source_text: Mapped[str] = mapped_column(Text, nullable=False)
    protected_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    machine_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_language: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False)
    is_locked: Mapped[int] = mapped_column(Integer, nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_overall: Mapped[float | None] = mapped_column(REAL, nullable=True)
    confidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_settings_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentAsset(Base):
    __tablename__ = "document_assets"
    __table_args__ = (
        _prefixed_uuid("ast_", "document_assets"),
        CheckConstraint(
            f"asset_type IN ({_sql_values(AssetType)})",
            name="ck_document_assets_type",
        ),
        CheckConstraint(
            "source_geometry_json IS NULL OR json_valid(source_geometry_json)",
            name="ck_document_assets_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_assets_target_geometry_json_valid",
        ),
        CheckConstraint(
            "width_pixels IS NULL OR width_pixels >= 0",
            name="ck_document_assets_width",
        ),
        CheckConstraint(
            "height_pixels IS NULL OR height_pixels >= 0",
            name="ck_document_assets_height",
        ),
        CheckConstraint(
            f"preservation_policy IN ({_sql_values(AssetPreservationPolicy)})",
            name="ck_document_assets_preservation_policy",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_assets_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=True,
    )
    file_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    width_pixels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_pixels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dpi: Mapped[float | None] = mapped_column(REAL, nullable=True)
    rotation_degrees: Mapped[float] = mapped_column(REAL, nullable=False)
    z_index: Mapped[int] = mapped_column(Integer, nullable=False)
    caption_block_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    preservation_policy: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentTable(Base):
    __tablename__ = "document_tables"
    __table_args__ = (
        _prefixed_uuid("tbl_", "document_tables"),
        CheckConstraint("row_count >= 0", name="ck_document_tables_rows"),
        CheckConstraint("column_count >= 0", name="ck_document_tables_columns"),
        CheckConstraint(
            f"complexity IN ({_sql_values(TableComplexity)})",
            name="ck_document_tables_complexity",
        ),
        CheckConstraint(
            "has_header_row IN (0, 1)",
            name="ck_document_tables_header_row",
        ),
        CheckConstraint(
            "has_header_column IN (0, 1)",
            name="ck_document_tables_header_column",
        ),
        CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_tables_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_tables_target_geometry_json_valid",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(DocumentStatus)})",
            name="ck_document_tables_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_tables_confidence",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_tables_metadata_json_valid",
        ),
        UniqueConstraint("block_id", name="uq_document_tables_block"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    block_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    complexity: Mapped[str] = mapped_column(Text, nullable=False)
    has_header_row: Mapped[int] = mapped_column(Integer, nullable=False)
    has_header_column: Mapped[int] = mapped_column(Integer, nullable=False)
    source_geometry_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuation_of_table_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentTableCell(Base):
    __tablename__ = "document_table_cells"
    __table_args__ = (
        _prefixed_uuid("cel_", "document_table_cells"),
        CheckConstraint("row_index >= 0", name="ck_document_table_cells_row"),
        CheckConstraint(
            "column_index >= 0",
            name="ck_document_table_cells_column",
        ),
        CheckConstraint("row_span >= 1", name="ck_document_table_cells_row_span"),
        CheckConstraint(
            "column_span >= 1",
            name="ck_document_table_cells_column_span",
        ),
        CheckConstraint(
            f"cell_role IN ({_sql_values(CellRole)})",
            name="ck_document_table_cells_role",
        ),
        CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_table_cells_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_table_cells_target_geometry_json_valid",
        ),
        CheckConstraint(
            "style_json IS NULL OR json_valid(style_json)",
            name="ck_document_table_cells_style_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    table_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_tables.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_span: Mapped[int] = mapped_column(Integer, nullable=False)
    column_span: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_role: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segment_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("document_segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_geometry_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentAnnotation(Base):
    __tablename__ = "document_annotations"
    __table_args__ = (
        _prefixed_uuid("ann_", "document_annotations"),
        CheckConstraint(
            f"annotation_type IN ({_sql_values(AnnotationType)})",
            name="ck_document_annotations_type",
        ),
        CheckConstraint(
            "json_valid(source_geometry_json)",
            name="ck_document_annotations_source_geometry_json_valid",
        ),
        CheckConstraint(
            "target_geometry_json IS NULL OR json_valid(target_geometry_json)",
            name="ck_document_annotations_target_geometry_json_valid",
        ),
        CheckConstraint(
            "trim(preservation_policy) <> ''",
            name="ck_document_annotations_preservation_policy",
        ),
        CheckConstraint(
            "trim(status) <> ''",
            name="ck_document_annotations_status",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_annotations_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    annotation_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_geometry_json: Mapped[str] = mapped_column(Text, nullable=False)
    target_geometry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    visible_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    preservation_policy: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentRelationship(Base):
    __tablename__ = "document_relationships"
    __table_args__ = (
        _prefixed_uuid("rel_", "document_relationships"),
        CheckConstraint(
            f"relationship_type IN ({_sql_values(RelationshipType)})",
            name="ck_document_relationships_type",
        ),
        CheckConstraint(
            "trim(source_entity_type) <> '' AND trim(source_entity_id) <> '' "
            "AND trim(target_entity_type) <> '' AND trim(target_entity_id) <> ''",
            name="ck_document_relationships_endpoints",
        ),
        CheckConstraint(
            "source_entity_type <> target_entity_type OR source_entity_id <> target_entity_id",
            name="ck_document_relationships_distinct_endpoints",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_document_relationships_confidence",
        ),
        CheckConstraint(
            "metadata_json IS NULL OR json_valid(metadata_json)",
            name="ck_document_relationships_metadata_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_document_sections_order",
    DocumentSection.document_id,
    DocumentSection.section_order,
    unique=True,
)
Index(
    "uq_document_blocks_page_order",
    DocumentBlock.page_id,
    DocumentBlock.page_reading_order,
    unique=True,
)
Index(
    "ix_document_blocks_page_type",
    DocumentBlock.page_id,
    DocumentBlock.block_type,
)
Index(
    "ix_document_blocks_section",
    DocumentBlock.section_id,
    DocumentBlock.global_reading_order,
)
Index(
    "uq_document_segments_block_order",
    DocumentSegment.block_id,
    DocumentSegment.segment_order,
    unique=True,
)
Index("ix_document_segments_status", DocumentSegment.status)
Index("ix_document_segments_review_status", DocumentSegment.review_status)
Index(
    "ix_document_segments_section_order",
    DocumentSegment.section_id,
    DocumentSegment.global_order,
)
Index("ix_document_segments_block", DocumentSegment.block_id)
Index("ix_document_assets_page", DocumentAsset.page_id)
Index("ix_document_assets_type", DocumentAsset.document_id, DocumentAsset.asset_type)
Index(
    "uq_document_table_cells_position",
    DocumentTableCell.table_id,
    DocumentTableCell.row_index,
    DocumentTableCell.column_index,
    unique=True,
)
