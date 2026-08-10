from transloka_documents.extraction.models import (
    ExtractedPage,
    TextBlockCandidate,
    TextGeometry,
)
from transloka_documents.structure.reading_order import (
    ReadingOrderRegion,
    ReadingOrderUncertainty,
    resolve_reading_order,
)


def test_orders_single_column_header_body_and_footer() -> None:
    page = _page(
        _block("Body two", 72, 300, 360, 40),
        _block("Footer", 72, 740, 360, 20),
        _block("Header", 72, 40, 360, 20),
        _block("Body one", 72, 200, 360, 40),
    )

    result = resolve_reading_order(page)

    assert result.ordered_block_indexes == (2, 3, 0, 1)
    assert [assignment.page_reading_order for assignment in result.assignments] == [1, 2, 3, 4]
    assert [assignment.region for assignment in result.assignments] == [
        ReadingOrderRegion.HEADER,
        ReadingOrderRegion.BODY,
        ReadingOrderRegion.BODY,
        ReadingOrderRegion.FOOTER,
    ]
    assert result.column_count == 1
    assert result.is_certain is True


def test_orders_two_columns_column_first_without_zigzag() -> None:
    page = _page(
        _block("Right two", 330, 300, 190, 40),
        _block("Left one", 72, 200, 190, 40),
        _block("Right one", 330, 200, 190, 40),
        _block("Left two", 72, 300, 190, 40),
    )

    result = resolve_reading_order(page)

    assert result.ordered_block_indexes == (1, 3, 2, 0)
    assert [assignment.column_index for assignment in result.assignments] == [0, 0, 1, 1]
    assert result.column_count == 2
    assert result.warnings == ()


def test_places_right_sidebar_after_the_main_body_column() -> None:
    page = _page(
        _block("Sidebar", 440, 210, 100, 180),
        _block("Body two", 72, 300, 320, 60),
        _block("Body one", 72, 200, 320, 60),
    )

    result = resolve_reading_order(page)

    assert result.ordered_block_indexes == (2, 1, 0)
    assert [assignment.column_index for assignment in result.assignments] == [0, 0, 1]
    assert result.column_count == 2
    assert result.is_certain is True


def test_warns_and_uses_stable_geometry_order_for_ambiguous_overlap() -> None:
    page = _page(
        _block("Second", 100, 220, 300, 80),
        _block("First", 72, 200, 300, 80),
    )

    first_result = resolve_reading_order(page)
    second_result = resolve_reading_order(page)

    assert first_result == second_result
    assert first_result.ordered_block_indexes == (1, 0)
    assert first_result.column_count == 1
    assert first_result.is_certain is False
    assert len(first_result.warnings) == 1
    assert first_result.warnings[0].code == "READING_ORDER_UNCERTAIN"
    assert first_result.warnings[0].reason is ReadingOrderUncertainty.OVERLAPPING_BLOCKS
    assert first_result.warnings[0].block_indexes == (0, 1)


def _page(*blocks: TextBlockCandidate) -> ExtractedPage:
    return ExtractedPage(
        page_number=1,
        width_points=612,
        height_points=792,
        characters=(),
        words=(),
        lines=(),
        block_candidates=blocks,
    )


def _block(
    source_text: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> TextBlockCandidate:
    return TextBlockCandidate(
        source_text=source_text,
        normalized_text=source_text,
        geometry=TextGeometry(x=x, y=y, width=width, height=height),
        line_indexes=(),
        word_indexes=(),
        character_indexes=(),
        normalization_boundaries=(),
        font_name=None,
        font_size=None,
    )
