from transloka_documents.extraction.models import TextBlockCandidate, TextGeometry
from transloka_documents.segmentation import segment_block
from transloka_documents.structure.classifier import BlockType

BLOCK_ID = "blk_550e8400-e29b-41d4-a716-446655440000"


def test_preserves_abbreviation_and_splits_real_sentence_boundary() -> None:
    segments = segment_block(
        BLOCK_ID, _block("Dr. Smith arrived. He started work."), BlockType.PARAGRAPH
    )
    assert [segment.source_text for segment in segments] == [
        "Dr. Smith arrived.",
        "He started work.",
    ]


def test_decimal_does_not_create_a_segment_boundary() -> None:
    segments = segment_block(
        BLOCK_ID, _block("Version 3.14 is stable. Upgrade now."), BlockType.PARAGRAPH
    )
    assert [segment.source_text for segment in segments] == [
        "Version 3.14 is stable.",
        "Upgrade now.",
    ]


def test_citation_stays_with_its_sentence() -> None:
    segments = segment_block(
        BLOCK_ID, _block("The result is confirmed [12]. Next step."), BlockType.PARAGRAPH
    )
    assert [segment.source_text for segment in segments] == [
        "The result is confirmed [12].",
        "Next step.",
    ]


def test_url_is_never_split() -> None:
    url = "https://docs.example.com/v1.2/guide"
    segments = segment_block(BLOCK_ID, _block(f"Read {url}. Continue here."), BlockType.PARAGRAPH)
    assert [segment.source_text for segment in segments] == [f"Read {url}.", "Continue here."]


def test_long_sentence_remains_whole() -> None:
    source = "A " + "very " * 400 + "long sentence ends here."
    segments = segment_block(BLOCK_ID, _block(source), BlockType.PARAGRAPH)
    assert len(segments) == 1
    assert segments[0].source_text == source


def test_mixed_language_segments_are_stable_and_ordered() -> None:
    block = _block("The system is ready. Sistem tetap lokal.")
    first = segment_block(BLOCK_ID, block, BlockType.PARAGRAPH)
    second = segment_block(BLOCK_ID, block, BlockType.PARAGRAPH)
    assert first == second
    assert [segment.segment_order for segment in first] == [1, 2]
    assert [segment.source_text for segment in first] == [
        "The system is ready.",
        "Sistem tetap lokal.",
    ]


def test_heading_caption_and_table_cell_remain_whole() -> None:
    for block_type in (BlockType.HEADING_1, BlockType.CAPTION, "TABLE_CELL"):
        segments = segment_block(BLOCK_ID, _block("One. Two."), block_type)
        assert len(segments) == 1
        assert segments[0].source_text == "One. Two."


def test_list_items_are_separate_segments() -> None:
    segments = segment_block(BLOCK_ID, _block("- First item\n- Second item"), BlockType.LIST)
    assert [segment.source_text for segment in segments] == ["- First item", "- Second item"]


def test_code_is_whole_and_not_translatable() -> None:
    source = "const endpoint = 'https://example.com/v1.2';\nrun(endpoint);"
    segments = segment_block(BLOCK_ID, _block(source), BlockType.CODE_BLOCK)
    assert len(segments) == 1
    assert segments[0].source_text == source
    assert segments[0].is_translatable is False


def _block(source_text: str) -> TextBlockCandidate:
    return TextBlockCandidate(
        source_text=source_text,
        normalized_text=source_text,
        geometry=TextGeometry(x=72, y=100, width=400, height=40),
        line_indexes=(),
        word_indexes=(),
        character_indexes=(),
        normalization_boundaries=(),
        font_name="Helvetica",
        font_size=12,
    )
