from types import SimpleNamespace

import pytest
from transloka_reconstruction.reflow import (
    ReflowBlock,
    ReflowBlockKind,
    ReflowDocument,
    ReflowSecurityError,
    ReflowTable,
    SanitizedReflowBuilder,
)


@pytest.fixture
def builder() -> SanitizedReflowBuilder:
    return SanitizedReflowBuilder()


def test_source_script_is_escaped_and_never_emitted_as_markup(
    builder: SanitizedReflowBuilder,
) -> None:
    result = builder.build(
        ReflowDocument(
            blocks=(ReflowBlock("block-1", text='<script>alert("x")</script>'),),
        )
    )

    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in result.html
    assert "<script" not in result.html.lower()
    assert "</script" not in result.html.lower()


def test_heading_code_table_and_image_use_only_allowlisted_markup(
    builder: SanitizedReflowBuilder,
) -> None:
    result = builder.build(
        ReflowDocument(
            title="<Document>",
            blocks=(
                ReflowBlock("heading-1", ReflowBlockKind.HEADING, "A heading", level=2),
                ReflowBlock("code-1", ReflowBlockKind.CODE, "if x < 1:\n    print(x)"),
                ReflowBlock(
                    "table-1",
                    ReflowBlockKind.TABLE,
                    table=ReflowTable((("Name", "Value"), ("A", "1")), header_row=True),
                ),
                ReflowBlock(
                    "image-1",
                    ReflowBlockKind.IMAGE,
                    asset_id="ast_cover-01",
                    alt_text="Cover & figure",
                ),
            ),
        )
    )

    assert "<h2" in result.html
    assert "<pre" in result.html and "<code>if x &lt; 1:" in result.html
    assert "<table" in result.html and "<thead>" in result.html
    assert '<img src="assets/ast_cover-01"' in result.html
    assert "Cover &amp; figure" in result.html
    assert result.asset_ids == ("ast_cover-01",)
    for forbidden in ("<iframe", "<object", "<embed", "<form", "<input", "<video", "<audio"):
        assert forbidden not in result.html.lower()


def test_unsafe_url_cannot_become_an_image_source(builder: SanitizedReflowBuilder) -> None:
    with pytest.raises((ValueError, ReflowSecurityError)):
        builder.build(
            {
                "blocks": [
                    {
                        "block_id": "image-1",
                        "kind": "image",
                        "asset_id": "https://example.test/image.png",
                    }
                ]
            }
        )


def test_css_is_internal_and_build_is_deterministic(
    builder: SanitizedReflowBuilder,
) -> None:
    document = ReflowDocument(
        blocks=(
            ReflowBlock("p-1", text="Stable output"),
            ReflowBlock("p-2", text="Second block"),
        )
    )

    first = builder.build(document)
    second = builder.build(document)

    assert first.html == second.html
    assert first.css == second.css
    assert "@page" in first.css
    assert "<style>" in first.html
    assert "javascript:" not in first.html.lower()


def test_document_ir_shape_uses_final_text_table_and_local_image(
    builder: SanitizedReflowBuilder,
) -> None:
    segment = SimpleNamespace(
        segment_id="seg-1",
        segment_order=0,
        final_text="Translated <paragraph>",
        source_text="Source paragraph",
    )
    paragraph = SimpleNamespace(
        block_id="blk-1",
        block_type="PARAGRAPH",
        reading_order=0,
        source_text="Source paragraph",
        segments=(segment,),
    )
    table_block = SimpleNamespace(
        block_id="blk-table",
        block_type="TABLE",
        reading_order=1,
        source_text=None,
        segments=(),
    )
    image_block = SimpleNamespace(
        block_id="blk-image",
        block_type="IMAGE",
        reading_order=2,
        source_text=None,
        segments=(),
    )
    table = SimpleNamespace(
        table_id="tbl-1",
        block_id="blk-table",
        row_count=1,
        column_count=1,
        has_header_row=True,
        cells=(SimpleNamespace(row_index=0, column_index=0, source_text="Cell", segment_ids=()),),
    )
    asset = SimpleNamespace(
        asset_id="ast-1",
        asset_type="IMAGE",
        mime_type="image/png",
        alt_text="An image",
    )
    page = SimpleNamespace(
        page_id="page-1",
        blocks=(image_block, table_block, paragraph),
        tables=(table,),
        assets=(asset,),
    )
    document = SimpleNamespace(
        document_id="doc-1",
        title="IR document",
        target_language="id",
        pages=(page,),
    )

    result = builder.build(document)

    assert "Translated &lt;paragraph&gt;" in result.html
    assert "<th>Cell</th>" in result.html
    assert '<img src="assets/ast-1"' in result.html
