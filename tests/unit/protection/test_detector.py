from transloka_core.database.models.glossary import ProtectedItemType
from transloka_glossary.matching import MatchRule
from transloka_glossary.protection import ProtectedContentDetector


def test_detects_every_required_protected_type() -> None:
    text = (
        "Keep framework; visit https://example.test/docs, email dev@example.test, "
        "call parse_document(), use GET /api/v1/items/{item_id}, open "
        r"C:\Work\docs\file.pdf, cite [12], and preserve PDF."
    )

    detected = ProtectedContentDetector().detect(
        text,
        [MatchRule(term_id="term-framework", source_term="framework")],
    )

    assert {item.item_type for item in detected} == set(ProtectedItemType)
    assert [item.source_value for item in detected] == [
        "framework",
        "https://example.test/docs",
        "dev@example.test",
        "parse_document()",
        "GET /api/v1/items/{item_id}",
        r"C:\Work\docs\file.pdf",
        "[12]",
        "PDF",
    ]
    assert detected[0].term_id == "term-framework"


def test_overlap_prefers_complete_non_translatable_item() -> None:
    text = "Visit https://example.test/API and call GET /api/v1/{item_id}."

    detected = ProtectedContentDetector().detect(
        text,
        [
            MatchRule(term_id="term-api", source_term="API"),
            MatchRule(term_id="term-item", source_term="item_id"),
        ],
    )

    assert [(item.item_type, item.source_value) for item in detected] == [
        (ProtectedItemType.URL, "https://example.test/API"),
        (ProtectedItemType.ENDPOINT, "GET /api/v1/{item_id}"),
    ]


def test_url_trims_sentence_punctuation_but_keeps_balanced_parentheses() -> None:
    text = "See https://example.test/docs?q=1, and (https://example.test/wiki/Function_(math))."

    urls = [
        item.source_value
        for item in ProtectedContentDetector().detect(text)
        if item.item_type is ProtectedItemType.URL
    ]

    assert urls == [
        "https://example.test/docs?q=1",
        "https://example.test/wiki/Function_(math)",
    ]


def test_code_identifiers_and_delimited_code_are_protected() -> None:
    text = "Call parse_document(), then keep `client.fetch_data()` unchanged."

    code = [
        item.source_value
        for item in ProtectedContentDetector().detect(text)
        if item.item_type is ProtectedItemType.CODE
    ]

    assert code == ["parse_document()", "`client.fetch_data()`"]


def test_windows_posix_and_relative_path_separators_are_supported() -> None:
    text = r"Open C:\Work\docs\file.pdf. Then /home/user/file.txt and src/module/file.py."

    paths = [
        item.source_value
        for item in ProtectedContentDetector().detect(text)
        if item.item_type is ProtectedItemType.FILE_PATH
    ]

    assert paths == [
        r"C:\Work\docs\file.pdf",
        "/home/user/file.txt",
        "src/module/file.py",
    ]


def test_numeric_and_author_year_citations_are_protected() -> None:
    text = "Prior work [1, 3-5] confirms this (Smith et al., 2024)."

    citations = [
        item.source_value
        for item in ProtectedContentDetector().detect(text)
        if item.item_type is ProtectedItemType.CITATION
    ]

    assert citations == ["[1, 3-5]", "(Smith et al., 2024)"]


def test_protect_replaces_all_items_and_preserves_complete_inventory() -> None:
    text = "Keep framework, PDF, and dev@example.test."
    detector = ProtectedContentDetector()

    result = detector.protect(
        text,
        [MatchRule(term_id="term-framework", source_term="framework")],
    )

    assert len(result.inventory) == 3
    assert [item.item_type for item in result.inventory] == [
        ProtectedItemType.TERM,
        ProtectedItemType.ACRONYM,
        ProtectedItemType.EMAIL,
    ]
    assert all(item.placeholder in result.text for item in result.inventory)
    assert all(item.source_value not in result.text for item in result.inventory)
    assert result.restoration_map == {
        item.placeholder: item.source_value for item in result.inventory
    }


def test_detection_and_protection_are_deterministic() -> None:
    text = "Use API at https://example.test/api and src/client.py."
    detector = ProtectedContentDetector()

    first_detection = detector.detect(text)
    second_detection = detector.detect(text)
    first_protection = detector.protect(text)
    second_protection = detector.protect(text)

    assert first_detection == second_detection
    assert first_protection == second_protection


def test_empty_text_has_an_empty_inventory() -> None:
    detector = ProtectedContentDetector()

    assert detector.detect("") == ()
    assert detector.protect("").text == ""
    assert detector.protect("").inventory == ()
