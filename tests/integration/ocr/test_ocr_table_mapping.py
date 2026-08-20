from transloka_documents.ocr.base import OCRGeometry, OCRResult, OCRTextBlock
from transloka_documents.ocr.tables import (
    OCRTableComplexity,
    OCRTableFallback,
    map_ocr_table,
)


def test_maps_simple_ocr_grid_with_cell_text_geometry_and_confidence() -> None:
    result = map_ocr_table(_ocr_result(_grid_blocks(borderless=False)))

    table = result.table
    assert table is not None
    assert table.complexity is OCRTableComplexity.SIMPLE
    assert table.fallback is None
    assert (table.row_count, table.column_count) == (3, 3)
    assert table.has_header_row_candidate is True
    assert [cell.source_text for cell in table.cells] == [
        "Name",
        "Qty",
        "Price",
        "Alpha",
        "2",
        "10",
        "Beta",
        "3",
        "12",
    ]
    assert table.cells[0].source_geometry == OCRGeometry(x=10, y=20, width=70, height=20)
    assert table.confidence > 0.9
    assert result.warnings == ()


def test_maps_aligned_text_without_borders_as_the_same_simple_grid() -> None:
    result = map_ocr_table(_ocr_result(_grid_blocks(borderless=True)))

    table = result.table
    assert table is not None
    assert table.complexity is OCRTableComplexity.SIMPLE
    assert table.fallback is None
    assert len(table.cells) == 9


def test_complex_grid_falls_back_without_forcing_cells() -> None:
    blocks = [
        OCRTextBlock(
            text=f"{row}-{column}",
            geometry=OCRGeometry(x=10 + column * 70, y=20 + row * 22, width=50, height=14),
            confidence=0.9,
        )
        for row in range(2)
        for column in range(9)
    ]

    result = map_ocr_table(_ocr_result(tuple(blocks)))

    table = result.table
    assert table is not None
    assert table.complexity is OCRTableComplexity.COMPLEX
    assert table.fallback is OCRTableFallback.PRESERVE_AS_IMAGE
    assert table.cells == ()
    assert result.warnings == ("COMPLEX_TABLE_FALLBACK",)


def _ocr_result(blocks: tuple[OCRTextBlock, ...]) -> OCRResult:
    return OCRResult(
        page_number=2,
        text="\n".join(block.text for block in blocks),
        blocks=blocks,
        confidence=0.94,
        provider="fake",
    )


def _grid_blocks(*, borderless: bool) -> tuple[OCRTextBlock, ...]:
    texts = (
        ("Name", "Qty", "Price"),
        ("Alpha", "2", "10"),
        ("Beta", "3", "12"),
    )
    return tuple(
        OCRTextBlock(
            text=text,
            geometry=OCRGeometry(
                x=10 + column * (110 if borderless else 100),
                y=20 + row * 30,
                width=70,
                height=20,
            ),
            confidence=0.92 - row * 0.01,
        )
        for row, values in enumerate(texts)
        for column, text in enumerate(values)
    )
