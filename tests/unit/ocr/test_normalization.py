import pytest
from transloka_documents.ocr.base import OCRGeometry, OCRResult, OCRSettings, OCRTextBlock
from transloka_documents.ocr.normalization import (
    OCRNormalizationSettings,
    normalize_ocr_result,
)


def _result(
    blocks: tuple[OCRTextBlock, ...],
    *,
    confidence: float = 0.92,
    text: str = "raw provider response",
    settings: OCRSettings | None = None,
) -> OCRResult:
    return OCRResult(
        page_number=3,
        text=text,
        blocks=blocks,
        confidence=confidence,
        settings=settings or OCRSettings(),
        provider="fake",
    )


def test_multiline_text_is_whitespace_normalized_and_geometry_is_unioned() -> None:
    raw = _result(
        (
            OCRTextBlock(
                text="Hello   ",
                geometry=OCRGeometry(x=10, y=20, width=40, height=10),
                confidence=0.90,
            ),
            OCRTextBlock(
                text="\tworld",
                geometry=OCRGeometry(x=55, y=20, width=45, height=10),
                confidence=0.80,
            ),
            OCRTextBlock(
                text="next line",
                geometry=OCRGeometry(x=10, y=55, width=90, height=10),
                confidence=0.85,
            ),
        ),
    )

    normalized = normalize_ocr_result(raw)

    assert normalized.raw_result is raw
    assert normalized.raw_text == raw.text
    assert [line.normalized_text for line in normalized.lines] == ["Hello world", "next line"]
    assert normalized.normalized_text == "Hello world\nnext line"
    assert normalized.blocks[0].geometry == OCRGeometry(x=10, y=20, width=90, height=10)
    assert normalized.blocks[0].line_indexes == (0,)
    assert normalized.segments[0].normalized_source_text == "Hello world"


def test_hyphenated_line_break_is_joined_without_losing_raw_ocr() -> None:
    raw = _result(
        (
            OCRTextBlock("inter-", OCRGeometry(x=10, y=20, width=45, height=10), 0.88),
            OCRTextBlock("national", OCRGeometry(x=10, y=50, width=70, height=10), 0.86),
        ),
        text="inter-\nnational",
    )

    normalized = normalize_ocr_result(raw)

    assert normalized.raw_result.text == "inter-\nnational"
    assert normalized.normalized_text == "international"
    assert normalized.blocks[0].source_text == "inter-\nnational"
    assert normalized.blocks[0].normalized_source_text == "international"
    assert normalized.segments[0].source_text == "inter-\nnational"
    assert normalized.segments[0].normalized_source_text == "international"


def test_two_columns_are_read_left_to_right_then_top_to_bottom() -> None:
    raw = _result(
        (
            OCRTextBlock("left one", OCRGeometry(x=10, y=100, width=180, height=16), 0.95),
            OCRTextBlock("right one", OCRGeometry(x=500, y=100, width=180, height=16), 0.94),
            OCRTextBlock("left two", OCRGeometry(x=10, y=135, width=180, height=16), 0.93),
            OCRTextBlock("right two", OCRGeometry(x=500, y=135, width=180, height=16), 0.92),
        ),
    )

    normalized = normalize_ocr_result(raw)

    assert normalized.column_count == 2
    assert [line.text for line in normalized.lines] == [
        "left one",
        "left two",
        "right one",
        "right two",
    ]
    assert [line.reading_order for line in normalized.lines] == [1, 2, 3, 4]
    assert [line.column_index for line in normalized.lines] == [0, 0, 1, 1]
    assert normalized.normalized_text == "left one left two\nright one right two"


def test_low_confidence_is_propagated_to_lines_blocks_segments_and_warning() -> None:
    raw = _result(
        (OCRTextBlock("uncertain text", OCRGeometry(x=0, y=0, width=100, height=20), 0.42),),
        confidence=0.42,
        settings=OCRSettings(low_confidence_threshold=0.75),
    )

    normalized = normalize_ocr_result(raw)

    assert normalized.confidence == pytest.approx(0.42)
    assert normalized.is_low_confidence is True
    assert normalized.lines[0].is_low_confidence is True
    assert normalized.blocks[0].is_low_confidence is True
    assert normalized.segments[0].is_low_confidence is True
    assert normalized.warnings == ("LOW_CONFIDENCE", "LOW_CONFIDENCE_LINE")


def test_normalization_settings_can_override_confidence_threshold() -> None:
    raw = _result(
        (OCRTextBlock("text", OCRGeometry(x=0, y=0, width=30, height=10), 0.60),),
        confidence=0.60,
    )

    normalized = normalize_ocr_result(
        raw,
        settings=OCRNormalizationSettings(low_confidence_threshold=0.50),
    )

    assert normalized.is_low_confidence is False
    assert normalized.blocks[0].is_low_confidence is False
