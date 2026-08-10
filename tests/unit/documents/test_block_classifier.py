import pytest
from transloka_documents.extraction.models import TextBlockCandidate, TextGeometry
from transloka_documents.structure.classifier import (
    BlockClassificationContext,
    BlockType,
    ClassificationUncertainty,
    NativeBlockKind,
    classify_block,
)
from transloka_documents.structure.reading_order import ReadingOrderRegion


def _context(
    *,
    region: ReadingOrderRegion = ReadingOrderRegion.BODY,
    body_font_size: float | None = None,
    native_kind: NativeBlockKind | None = None,
    is_first_content_block: bool = False,
) -> BlockClassificationContext:
    return BlockClassificationContext(
        page_width=612,
        page_height=792,
        region=region,
        body_font_size=body_font_size,
        native_kind=native_kind,
        is_first_content_block=is_first_content_block,
    )


def _block(
    source_text: str,
    *,
    font_name: str | None = "Helvetica",
    font_size: float | None = 12,
) -> TextBlockCandidate:
    return TextBlockCandidate(
        source_text=source_text,
        normalized_text=source_text,
        geometry=TextGeometry(x=72, y=200, width=360, height=40),
        line_indexes=(),
        word_indexes=(),
        character_indexes=(),
        normalization_boundaries=(),
        font_name=font_name,
        font_size=font_size,
    )


@pytest.mark.parametrize(
    ("block", "context", "expected"),
    [
        (
            _block("TransLoka Architecture", font_size=24),
            _context(body_font_size=12, is_first_content_block=True),
            BlockType.DOCUMENT_TITLE,
        ),
        (
            _block("System Architecture", font_size=16),
            _context(body_font_size=12),
            BlockType.HEADING_1,
        ),
        (
            _block("This paragraph contains enough words to be recognized as prose."),
            _context(),
            BlockType.PARAGRAPH,
        ),
        (
            _block("- First item\n- Second item"),
            _context(),
            BlockType.LIST,
        ),
        (
            _block("Figure 2. Translation workflow"),
            _context(),
            BlockType.CAPTION,
        ),
        (
            _block(""),
            _context(native_kind=NativeBlockKind.IMAGE),
            BlockType.IMAGE,
        ),
        (
            _block(""),
            _context(native_kind=NativeBlockKind.TABLE),
            BlockType.TABLE,
        ),
        (
            _block("def translate(source):", font_name="Courier"),
            _context(),
            BlockType.CODE_BLOCK,
        ),
        (
            _block("TransLoka User Guide"),
            _context(region=ReadingOrderRegion.HEADER),
            BlockType.HEADER,
        ),
        (
            _block("Confidential draft"),
            _context(region=ReadingOrderRegion.FOOTER),
            BlockType.FOOTER,
        ),
        (
            _block("12"),
            _context(region=ReadingOrderRegion.FOOTER),
            BlockType.PAGE_NUMBER,
        ),
        (
            _block("Note"),
            _context(),
            BlockType.UNKNOWN,
        ),
    ],
)
def test_classifies_each_minimum_block_type(
    block: TextBlockCandidate,
    context: BlockClassificationContext,
    expected: BlockType,
) -> None:
    result = classify_block(block, context)

    assert result.block_type is expected
    if expected is BlockType.UNKNOWN:
        assert result.warnings
    else:
        assert result.is_certain is True
        assert result.confidence >= 0.75


def test_low_confidence_content_falls_back_to_unknown_with_warning() -> None:
    result = classify_block(_block("Note"), _context())

    assert result.block_type is BlockType.UNKNOWN
    assert result.confidence == 0.35
    assert result.evidence == ()
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "BLOCK_CLASSIFICATION_UNCERTAIN"
    assert result.warnings[0].reason is ClassificationUncertainty.INSUFFICIENT_EVIDENCE


def test_empty_content_is_not_forced_to_a_text_type() -> None:
    result = classify_block(_block(""), _context())

    assert result.block_type is BlockType.UNKNOWN
    assert result.confidence == 0.0
    assert result.warnings[0].reason is ClassificationUncertainty.EMPTY_CONTENT
