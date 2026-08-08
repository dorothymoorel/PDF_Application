import math
from collections.abc import Hashable, Iterable
from datetime import UTC, datetime
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from transloka_document_ir.enums import (
    AnnotationType,
    AssetPreservationPolicy,
    AssetType,
    BlockType,
    CellRole,
    CoordinateSystem,
    DocumentStatus,
    DocumentType,
    PageType,
    ReadingDirection,
    RelationshipType,
    SectionType,
    SegmentStatus,
    SemanticRole,
    WarningSeverity,
    WarningStatus,
    WarningType,
)
from transloka_document_ir.identifiers import (
    AnnotationId,
    AssetId,
    BlockId,
    CellId,
    DocumentId,
    EntityId,
    FileId,
    PageId,
    ProjectId,
    RelationshipId,
    SectionId,
    SegmentId,
    TableId,
    WarningId,
)

CURRENT_IR_VERSION: Final[Literal["0.1"]] = "0.1"
LanguageCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=35,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Checksum = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
StorageKey = Annotated[str, StringConstraints(min_length=3, max_length=1024)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class IRModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        frozen=True,
        strict=True,
        validate_default=True,
    )


class Geometry(IRModel):
    coordinate_system: CoordinateSystem
    x: Annotated[float, Field(ge=0.0)]
    y: Annotated[float, Field(ge=0.0)]
    width: Annotated[float, Field(gt=0.0)]
    height: Annotated[float, Field(gt=0.0)]
    rotation: float = 0.0

    @model_validator(mode="after")
    def validate_geometry(self) -> Self:
        if not math.isfinite(self.rotation):
            raise ValueError("Geometry rotation must be finite.")
        if self.coordinate_system is CoordinateSystem.NORMALIZED_TOP_LEFT and (
            self.x > 1.0
            or self.y > 1.0
            or self.width > 1.0
            or self.height > 1.0
            or self.x + self.width > 1.0
            or self.y + self.height > 1.0
        ):
            raise ValueError("Normalized geometry must remain within the 0..1 bounds.")
        return self


class Warning(IRModel):
    warning_id: WarningId
    scope_type: str
    scope_id: EntityId
    warning_type: WarningType
    severity: WarningSeverity
    message: NonEmptyText
    details: dict[str, JsonValue] = Field(default_factory=dict)
    status: WarningStatus
    created_by: Literal["SYSTEM", "USER"]
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    @field_validator("created_at", "resolved_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Document IR timestamps must include a timezone.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def resolution_is_consistent(self) -> Self:
        resolved = self.status is not WarningStatus.OPEN
        if resolved != (self.resolved_at is not None):
            raise ValueError("Resolved warning status and timestamp must agree.")
        return self


class Segment(IRModel):
    segment_id: SegmentId
    block_id: BlockId
    segment_order: Annotated[int, Field(ge=0)]
    source_text: str
    ocr_text: str | None = None
    normalized_source_text: str
    protected_source_text: str | None = None
    machine_translation: str | None = None
    reviewed_translation: str | None = None
    final_text: str | None = None
    status: SegmentStatus
    translation_style: str | None = None
    warnings: tuple[Warning, ...] = ()

    @model_validator(mode="after")
    def final_text_follows_resolution_rule(self) -> Self:
        expected: str | None = None
        if self.reviewed_translation is not None:
            expected = self.reviewed_translation
        elif self.machine_translation is not None:
            expected = self.machine_translation
        elif self.status is SegmentStatus.NOT_TRANSLATABLE:
            expected = self.source_text
        if self.final_text is not None and self.final_text != expected:
            raise ValueError("Segment final_text does not follow the resolution rule.")
        return self


class Block(IRModel):
    block_id: BlockId
    page_id: PageId
    block_type: BlockType
    semantic_role: SemanticRole | None = None
    source_geometry: Geometry
    target_geometry: Geometry | None = None
    reading_order: Annotated[int, Field(ge=0)]
    global_reading_order: Annotated[int, Field(ge=0)] | None = None
    section_id: SectionId | None = None
    parent_block_id: BlockId | None = None
    child_block_ids: tuple[BlockId, ...] = ()
    source_text: str | None = None
    normalized_source_text: str | None = None
    segments: tuple[Segment, ...] = ()
    status: DocumentStatus
    confidence: Confidence | None = None
    warnings: tuple[Warning, ...] = ()

    @model_validator(mode="after")
    def segments_are_ordered_and_owned(self) -> Self:
        if any(segment.block_id != self.block_id for segment in self.segments):
            raise ValueError("Every segment must reference its containing block.")
        _require_unique(
            (segment.segment_order for segment in self.segments),
            "Segment order must be unique within a block.",
        )
        return self


class Cell(IRModel):
    cell_id: CellId
    table_id: TableId
    row_index: Annotated[int, Field(ge=0)]
    column_index: Annotated[int, Field(ge=0)]
    row_span: Annotated[int, Field(ge=1)] = 1
    column_span: Annotated[int, Field(ge=1)] = 1
    source_geometry: Geometry
    target_geometry: Geometry | None = None
    cell_role: CellRole
    source_text: str | None = None
    segment_ids: tuple[SegmentId, ...] = ()


class Table(IRModel):
    table_id: TableId
    block_id: BlockId
    source_geometry: Geometry
    target_geometry: Geometry | None = None
    row_count: Annotated[int, Field(ge=0)]
    column_count: Annotated[int, Field(ge=0)]
    has_header_row: bool
    has_header_column: bool
    cells: tuple[Cell, ...] = ()
    status: DocumentStatus
    confidence: Confidence | None = None

    @model_validator(mode="after")
    def cells_fit_table(self) -> Self:
        positions: set[tuple[int, int]] = set()
        occupied: set[tuple[int, int]] = set()
        for cell in self.cells:
            if cell.table_id != self.table_id:
                raise ValueError("Every cell must reference its containing table.")
            if (
                cell.row_index + cell.row_span > self.row_count
                or cell.column_index + cell.column_span > self.column_count
            ):
                raise ValueError("Table cell must remain inside table bounds.")
            position = (cell.row_index, cell.column_index)
            if position in positions:
                raise ValueError("Table cell position must be unique.")
            positions.add(position)
            coverage = {
                (row, column)
                for row in range(cell.row_index, cell.row_index + cell.row_span)
                for column in range(
                    cell.column_index,
                    cell.column_index + cell.column_span,
                )
            }
            if occupied.intersection(coverage):
                raise ValueError("Merged table cells must not overlap.")
            occupied.update(coverage)
        return self


class Asset(IRModel):
    asset_id: AssetId
    page_id: PageId
    asset_type: AssetType
    source_geometry: Geometry
    target_geometry: Geometry | None = None
    storage_key: StorageKey
    mime_type: NonEmptyText
    checksum_sha256: Checksum
    width_px: Annotated[int, Field(ge=0)] | None = None
    height_px: Annotated[int, Field(ge=0)] | None = None
    dpi: Annotated[float, Field(gt=0.0)] | None = None
    rotation: float = 0.0
    opacity: Confidence = 1.0
    z_index: int = 0
    alt_text: str | None = None
    caption_block_id: BlockId | None = None
    preservation_policy: AssetPreservationPolicy = AssetPreservationPolicy.KEEP_UNCHANGED

    @field_validator("storage_key")
    @classmethod
    def storage_key_is_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            normalized != value
            or value.startswith("/")
            or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("Asset storage_key must be a safe relative path.")
        return value


class Annotation(IRModel):
    annotation_id: AnnotationId
    page_id: PageId
    annotation_type: AnnotationType
    source_geometry: Geometry
    target_geometry: Geometry | None = None
    target: str | None = None
    content: str | None = None
    preserve: bool


class Relationship(IRModel):
    relationship_id: RelationshipId
    relationship_type: RelationshipType
    source_entity_id: EntityId
    target_entity_id: EntityId
    confidence: Confidence | None = None

    @model_validator(mode="after")
    def endpoints_differ(self) -> Self:
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("Relationship endpoints must be different entities.")
        return self


class Section(IRModel):
    section_id: SectionId
    document_id: DocumentId
    section_type: SectionType
    title_segment_id: SegmentId | None = None
    level: Annotated[int, Field(ge=0)]
    order: Annotated[int, Field(ge=0)]
    parent_section_id: SectionId | None = None
    start_page_id: PageId | None = None
    end_page_id: PageId | None = None
    block_ids: tuple[BlockId, ...] = ()
    summary: str | None = None


class Page(IRModel):
    page_id: PageId
    document_id: DocumentId
    source_page_number: Annotated[int, Field(ge=1)]
    logical_page_number: str | None = None
    target_page_number: Annotated[int, Field(ge=1)] | None = None
    width: Annotated[float, Field(gt=0.0)]
    height: Annotated[float, Field(gt=0.0)]
    rotation: float
    page_type: PageType
    status: DocumentStatus
    reading_direction: ReadingDirection = ReadingDirection.LTR
    column_count: Annotated[int, Field(ge=0)] = 1
    blocks: tuple[Block, ...] = ()
    tables: tuple[Table, ...] = ()
    assets: tuple[Asset, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    warnings: tuple[Warning, ...] = ()

    @model_validator(mode="after")
    def children_are_valid(self) -> Self:
        if not math.isfinite(self.rotation):
            raise ValueError("Page rotation must be finite.")
        if any(block.page_id != self.page_id for block in self.blocks):
            raise ValueError("Every block must reference its containing page.")
        if any(asset.page_id != self.page_id for asset in self.assets):
            raise ValueError("Every asset must reference its containing page.")
        if any(annotation.page_id != self.page_id for annotation in self.annotations):
            raise ValueError("Every annotation must reference its containing page.")
        _require_unique(
            (block.reading_order for block in self.blocks),
            "Block reading order must be unique within a page.",
        )
        block_ids = {block.block_id for block in self.blocks}
        if any(table.block_id not in block_ids for table in self.tables):
            raise ValueError("Every table must reference a block on its page.")
        for geometry in _source_geometries(self):
            if geometry.coordinate_system is not CoordinateSystem.NORMALIZED_TOP_LEFT and (
                geometry.x + geometry.width > self.width
                or geometry.y + geometry.height > self.height
            ):
                raise ValueError("Source geometry must remain within page bounds.")
        return self


class Document(IRModel):
    ir_version: Literal["0.1"]
    document_id: DocumentId
    project_id: ProjectId
    source_file_id: FileId
    source_language: LanguageCode
    target_language: LanguageCode
    document_type: DocumentType
    page_count: Annotated[int, Field(ge=0)]
    status: DocumentStatus
    revision: Annotated[int, Field(ge=1)]
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    processing_config: dict[str, JsonValue] = Field(default_factory=dict)
    sections: tuple[Section, ...] = ()
    pages: tuple[Page, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    warnings: tuple[Warning, ...] = ()

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Document IR timestamps must include a timezone.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_document_graph(self) -> Self:
        if self.page_count != len(self.pages):
            raise ValueError("page_count must equal the number of page objects.")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at.")
        if self.source_language.casefold() == self.target_language.casefold():
            raise ValueError("Source and target languages must be different.")
        if any(page.document_id != self.document_id for page in self.pages):
            raise ValueError("Every page must reference its containing document.")
        if any(section.document_id != self.document_id for section in self.sections):
            raise ValueError("Every section must reference its containing document.")
        _require_unique(
            (page.source_page_number for page in self.pages),
            "Source page number must be unique within a document.",
        )
        _require_unique(
            (section.order for section in self.sections),
            "Section order must be unique within a document.",
        )
        self._validate_references()
        return self

    def _validate_references(self) -> None:
        all_blocks = [block for page in self.pages for block in page.blocks]
        all_segments = [segment for block in all_blocks for segment in block.segments]
        all_tables = [table for page in self.pages for table in page.tables]
        all_cells = [cell for table in all_tables for cell in table.cells]
        all_assets = [asset for page in self.pages for asset in page.assets]
        all_annotations = [annotation for page in self.pages for annotation in page.annotations]
        all_warnings = [
            *self.warnings,
            *(warning for page in self.pages for warning in page.warnings),
            *(warning for block in all_blocks for warning in block.warnings),
            *(warning for segment in all_segments for warning in segment.warnings),
        ]
        sections = {section.section_id: section for section in self.sections}
        pages = {page.page_id: page for page in self.pages}
        blocks = {block.block_id: block for block in all_blocks}
        segments = {segment.segment_id: segment for segment in all_segments}
        tables = {table.table_id: table for table in all_tables}
        cells = {cell.cell_id: cell for cell in all_cells}
        assets = {asset.asset_id: asset for asset in all_assets}
        annotations = {annotation.annotation_id: annotation for annotation in all_annotations}
        relationships = {
            relationship.relationship_id: relationship for relationship in self.relationships
        }
        warnings = {warning.warning_id: warning for warning in all_warnings}
        entities: dict[str, object] = {
            self.document_id: self,
            **sections,
            **pages,
            **blocks,
            **segments,
            **tables,
            **cells,
            **assets,
            **annotations,
            **relationships,
            **warnings,
        }
        expected_count = (
            1
            + len(self.sections)
            + len(self.pages)
            + len(all_blocks)
            + len(all_segments)
            + len(all_tables)
            + len(all_cells)
            + len(all_assets)
            + len(all_annotations)
            + len(self.relationships)
            + len(all_warnings)
        )
        if len(entities) != expected_count:
            raise ValueError("Entity IDs must be unique within a Document IR.")

        for section in sections.values():
            if section.parent_section_id is not None and section.parent_section_id not in sections:
                raise ValueError("Section parent must exist in the document.")
            if section.start_page_id is not None and section.start_page_id not in pages:
                raise ValueError("Section start page must exist in the document.")
            if section.end_page_id is not None and section.end_page_id not in pages:
                raise ValueError("Section end page must exist in the document.")
            if section.title_segment_id is not None and section.title_segment_id not in segments:
                raise ValueError("Section title segment must exist in the document.")
            if any(block_id not in blocks for block_id in section.block_ids):
                raise ValueError("Section blocks must exist in the document.")

        for block in blocks.values():
            if block.section_id is not None and block.section_id not in sections:
                raise ValueError("Block section must exist in the document.")
            if block.parent_block_id is not None and block.parent_block_id not in blocks:
                raise ValueError("Block parent must exist in the document.")
            if any(child_id not in blocks for child_id in block.child_block_ids):
                raise ValueError("Block children must exist in the document.")
        for table in tables.values():
            valid_segment_ids = {segment.segment_id for segment in blocks[table.block_id].segments}
            if any(
                segment_id not in valid_segment_ids
                for cell in table.cells
                for segment_id in cell.segment_ids
            ):
                raise ValueError("Table cell segments must belong to the table block.")
        for asset in assets.values():
            if asset.caption_block_id is not None and asset.caption_block_id not in blocks:
                raise ValueError("Asset caption block must exist in the document.")
        for relationship in self.relationships:
            if (
                relationship.source_entity_id not in entities
                or relationship.target_entity_id not in entities
            ):
                raise ValueError("Relationship endpoints must exist in the document.")
        for warning in warnings.values():
            if warning.scope_id not in entities:
                raise ValueError("Warning scope must exist in the document.")


def _source_geometries(page: Page) -> tuple[Geometry, ...]:
    return (
        *(block.source_geometry for block in page.blocks),
        *(table.source_geometry for table in page.tables),
        *(cell.source_geometry for table in page.tables for cell in table.cells),
        *(asset.source_geometry for asset in page.assets),
        *(annotation.source_geometry for annotation in page.annotations),
    )


def _require_unique[HashableT: Hashable](values: Iterable[HashableT], message: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(message)
