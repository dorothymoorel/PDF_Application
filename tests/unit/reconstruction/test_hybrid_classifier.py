from __future__ import annotations

from transloka_reconstruction.hybrid import (
    BlockStrategy,
    HybridStrategyClassifier,
    PageClassification,
    PageStrategy,
    TableComplexity,
    classify_page,
)


def _block(block_id: str, block_type: str, **values: object) -> dict[str, object]:
    return {"block_id": block_id, "block_type": block_type, **values}


def test_fixed_page_defaults_to_overlay() -> None:
    decision = classify_page(
        {
            "page_id": "page-fixed",
            "page_type": "COVER",
            "blocks": (
                _block("header", "HEADER", text="TransLoka"),
                _block("page-number", "PAGE_NUMBER", text="1"),
            ),
        }
    )

    assert decision.classification is PageClassification.COVER
    assert decision.strategy is PageStrategy.OVERLAY
    assert {item.strategy for item in decision.block_decisions} == {BlockStrategy.OVERLAY}


def test_body_page_expansion_defaults_to_reflow() -> None:
    decision = classify_page(
        {
            "page_id": "page-body",
            "page_type": "DIGITAL",
            "blocks": (
                _block(
                    "paragraph",
                    "PARAGRAPH",
                    text="A long body paragraph that expands after translation. " * 12,
                    expansion_ratio=1.35,
                ),
            ),
        }
    )

    assert decision.classification is PageClassification.REFLOW_FRIENDLY
    assert decision.strategy is PageStrategy.REFLOW
    assert decision.block_decisions[0].strategy is BlockStrategy.REFLOW


def test_mixed_page_keeps_image_and_fixed_caption_while_reflowing_body() -> None:
    decision = classify_page(
        {
            "page_id": "page-mixed",
            "page_type": "DIGITAL",
            "assets_count": 1,
            "blocks": (
                _block("body", "PARAGRAPH", text="Body text " * 80),
                _block("image", "IMAGE"),
                _block("caption", "CAPTION", text="Figure 1"),
            ),
        }
    )

    assert decision.classification is PageClassification.MIXED_LAYOUT
    assert decision.strategy is PageStrategy.HYBRID
    assert [item.strategy for item in decision.block_decisions] == [
        BlockStrategy.REFLOW,
        BlockStrategy.PRESERVE,
        BlockStrategy.OVERLAY,
    ]


def test_table_heavy_page_distinguishes_simple_and_complex_tables() -> None:
    classifier = HybridStrategyClassifier()
    decision = classifier.classify_page(
        {
            "page_id": "page-table",
            "page_type": "DIGITAL",
            "blocks": (
                _block("simple", "TABLE", table_complexity=TableComplexity.SIMPLE),
                _block("complex", "TABLE", table_complexity=TableComplexity.COMPLEX),
            ),
        }
    )

    assert decision.classification is PageClassification.TABLE_HEAVY
    assert decision.strategy is PageStrategy.HYBRID
    assert [item.strategy for item in decision.block_decisions] == [
        BlockStrategy.RECONSTRUCT,
        BlockStrategy.RENDER_AS_IMAGE,
    ]


def test_unsupported_page_requires_manual_review_and_is_deterministic() -> None:
    page = {
        "page_id": "page-unknown",
        "page_type": "UNKNOWN",
        "blocks": (_block("unknown", "UNKNOWN", supported=False),),
    }

    first = classify_page(page)
    second = classify_page(page)

    assert first.classification is PageClassification.UNKNOWN
    assert first.strategy is PageStrategy.MANUAL_REVIEW
    assert first.block_decisions[0].strategy is BlockStrategy.MANUAL_REVIEW
    assert first.decision_hash == second.decision_hash
    assert first.to_dict() == second.to_dict()
