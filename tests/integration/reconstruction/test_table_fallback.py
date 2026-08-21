from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image
from transloka_reconstruction.tables.fallback import (
    ComplexTableFallbackRequest,
    ComplexTableKind,
    FallbackStrategy,
    FallbackWarningCode,
    FallbackWarningSeverity,
    preserve_complex_table_as_image,
)
from transloka_reconstruction.tables.models import TableRect


def _encoded_image(image_format: str, *, size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, (40, 80, 120))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_nested_table_is_preserved_as_image_with_translated_caption() -> None:
    source = _encoded_image("PNG", size=(400, 200))

    result = preserve_complex_table_as_image(
        ComplexTableFallbackRequest(
            table_id="table-nested",
            page_id="page-1",
            source=source,
            kind=ComplexTableKind.NESTED,
            target=TableRect(10, 20, 100, 100),
            caption_source="Nested table",
            caption_translation="Tabel bertingkat",
            caption_block_id="caption-1",
        )
    )

    assert result.strategy is FallbackStrategy.PRESERVE_AS_IMAGE
    assert result.preserved_as_image
    assert result.image_data == source
    assert result.mime_type == "image/png"
    assert result.kind is ComplexTableKind.NESTED
    assert result.caption_text == "Tabel bertingkat"
    assert result.caption_translated
    assert result.caption is not None
    assert result.caption.block_id == "caption-1"
    assert result.placement is not None
    assert result.placement.caption is not None
    assert result.placement.caption.text == "Tabel bertingkat"
    assert result.placement.aspect_ratio_preserved
    assert result.claims_reconstructed is False
    assert any(
        warning.code is FallbackWarningCode.COMPLEX_TABLE_PRESERVED_AS_IMAGE
        for warning in result.warnings
    )


def test_irregular_table_keeps_jpeg_bytes_and_does_not_reconstruct() -> None:
    source = _encoded_image("JPEG", size=(160, 80))

    result = preserve_complex_table_as_image(
        ComplexTableFallbackRequest(
            table_id="table-irregular",
            page_id="page-2",
            source=source,
            kind=ComplexTableKind.IRREGULAR,
            target=TableRect(0, 0, 320, 160),
        )
    )

    assert result.image_data == source
    assert result.mime_type == "image/jpeg"
    assert result.width_px == 160
    assert result.height_px == 80
    assert result.checksum_sha256 == hashlib.sha256(source).hexdigest()
    assert result.complete
    assert result.reconstructed is False
    assert result.claims_reconstructed is False


def test_image_fallback_preserves_transparent_png_source() -> None:
    image = Image.new("RGBA", (20, 30), (20, 40, 60, 128))
    output = BytesIO()
    image.save(output, format="PNG")
    source = output.getvalue()

    result = preserve_complex_table_as_image(
        ComplexTableFallbackRequest(
            table_id="table-image",
            page_id="page-3",
            source=source,
            kind=ComplexTableKind.DIAGRAM_LIKE,
        )
    )

    assert result.preserved_as_image
    assert result.image_data == source
    assert result.width_px == 20
    assert result.height_px == 30
    assert result.placement is not None
    assert result.placement.rendered is not None


def test_missing_image_emits_critical_warning_and_retains_source_caption() -> None:
    result = preserve_complex_table_as_image(
        ComplexTableFallbackRequest(
            table_id="table-missing",
            page_id="page-4",
            source=None,
            kind=ComplexTableKind.MERGED,
            caption_source="Original caption",
        )
    )

    assert result.image_data is None
    assert result.preserved_as_image is False
    assert result.claims_reconstructed is False
    assert result.caption_text == "Original caption"
    assert result.caption_translated is False
    assert any(
        warning.code is FallbackWarningCode.TABLE_IMAGE_MISSING
        and warning.severity is FallbackWarningSeverity.CRITICAL
        for warning in result.warnings
    )
    assert any(
        warning.code is FallbackWarningCode.CAPTION_NOT_TRANSLATED for warning in result.warnings
    )


def test_invalid_image_emits_critical_warning_without_synthetic_replacement() -> None:
    result = preserve_complex_table_as_image(
        ComplexTableFallbackRequest(
            table_id="table-invalid",
            page_id="page-5",
            source=b"not-an-image",
            kind=ComplexTableKind.UNKNOWN,
        )
    )

    assert result.image_data is None
    assert result.preserved_as_image is False
    warning = next(
        warning
        for warning in result.warnings
        if warning.code is FallbackWarningCode.TABLE_IMAGE_INVALID
    )
    assert warning.severity is FallbackWarningSeverity.CRITICAL
    assert result.claims_reconstructed is False
