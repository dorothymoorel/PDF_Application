import pytest
from transloka_translation.schemas import (
    TranslatedSegment,
    TranslationContext,
    TranslationPlaceholder,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationResponse,
    TranslationStyle,
)
from transloka_translation.validation import (
    TranslationIntegrityError,
    TranslationValidator,
    ValidationCode,
    ValidationIssue,
    ValidationSeverity,
    validate_citation_integrity,
    validate_code_integrity,
    validate_empty_translation,
    validate_negation,
    validate_number_integrity,
    validate_placeholder_integrity,
    validate_segment_mapping,
    validate_suspicious_length,
    validate_target_language,
    validate_translation,
    validate_untranslated_source_fragments,
    validate_url_integrity,
)

PLACEHOLDER = "__TLK_TERM_0001_AA__"


def test_segment_mapping_accepts_exact_ids_and_order() -> None:
    request = make_request(("segment_001", "segment_002"))
    response = make_response(("segment_001", "segment_002"))

    assert validate_segment_mapping(request, response) == ()


@pytest.mark.parametrize(
    "response_ids",
    [
        ("segment_002", "segment_001"),
        ("segment_001",),
        ("segment_001", "segment_999"),
    ],
)
def test_segment_mapping_rejects_reordered_missing_and_unknown_ids(
    response_ids: tuple[str, ...],
) -> None:
    issues = validate_segment_mapping(
        make_request(("segment_001", "segment_002")),
        make_response(response_ids),
    )

    assert issue_codes(issues) == {ValidationCode.SEGMENT_MAPPING_MISMATCH}
    assert issues[0].severity is ValidationSeverity.CRITICAL


def test_placeholder_validator_accepts_exact_inventory() -> None:
    source = make_source("Translate " + PLACEHOLDER)
    translated = make_translation("Terjemahkan " + PLACEHOLDER)

    assert validate_placeholder_integrity(source, translated, (make_placeholder(),)) == ()


def test_placeholder_validator_rejects_reordered_inventory() -> None:
    second_placeholder = "__TLK_URL_0002_BB__"
    issues = validate_placeholder_integrity(
        make_source(f"Keep {PLACEHOLDER} before {second_placeholder}."),
        make_translation(f"Pertahankan {second_placeholder} sebelum {PLACEHOLDER}."),
        (
            make_placeholder(),
            make_placeholder(placeholder=second_placeholder, item_type="URL"),
        ),
    )

    assert issue_codes(issues) == {ValidationCode.PLACEHOLDER_MISMATCH}


@pytest.mark.parametrize(
    "translated_text",
    [
        "Placeholder hilang.",
        f"Duplikat {PLACEHOLDER} {PLACEHOLDER}.",
        "Berubah __TLK_TERM_0001_AB__.",
        "Rusak __TLK_TERM_0001_A__.",
        "Asing __TLK_URL_9999_FF__.",
    ],
)
def test_placeholder_validator_rejects_every_inventory_mismatch(
    translated_text: str,
) -> None:
    issues = validate_placeholder_integrity(
        make_source("Translate " + PLACEHOLDER),
        make_translation(translated_text),
        (make_placeholder(),),
    )

    assert issue_codes(issues) == {ValidationCode.PLACEHOLDER_MISMATCH}
    assert issues[0].severity is ValidationSeverity.CRITICAL


def test_number_validator_accepts_locale_separator_change_without_value_change() -> None:
    source = make_source("Revenue was USD 1,500.50, growth 25%, version v1.2.3 on 2026-08-14.")
    translated = make_translation(
        "Pendapatan USD 1.500,50, pertumbuhan 25%, versi v1.2.3 pada 2026-08-14."
    )

    assert validate_number_integrity(source, translated) == ()


def test_number_validator_rejects_added_number() -> None:
    issues = validate_number_integrity(
        make_source("The value is 10."),
        make_translation("Nilainya 10 dan angka tambahan 99."),
    )

    assert issue_codes(issues) == {ValidationCode.NUMBER_MISMATCH}


@pytest.mark.parametrize("translated_text", ["Nilainya 11%.", "Nilainya 10.", "Nilainya EUR 10%."])
def test_number_validator_rejects_altered_or_removed_number_metadata(
    translated_text: str,
) -> None:
    source_text = "The value is USD 10%."

    issues = validate_number_integrity(
        make_source(source_text),
        make_translation(translated_text),
    )

    assert issue_codes(issues) == {ValidationCode.NUMBER_MISMATCH}


def test_url_validator_accepts_identical_url() -> None:
    source = make_source("Open https://example.test/docs?q=1.")
    translated = make_translation("Buka https://example.test/docs?q=1.")

    assert validate_url_integrity(source, translated) == ()


def test_url_validator_rejects_altered_url() -> None:
    issues = validate_url_integrity(
        make_source("Open https://example.test/docs?q=1."),
        make_translation("Buka https://evil.test/docs?q=1."),
    )

    assert issue_codes(issues) == {ValidationCode.URL_MISMATCH}
    assert issues[0].severity is ValidationSeverity.CRITICAL


def test_code_validator_accepts_preserved_code_endpoint_and_path() -> None:
    source = make_source("Call `parse_value()` with POST /api/v1/jobs and config/app.toml.")
    translated = make_translation(
        "Panggil `parse_value()` dengan POST /api/v1/jobs dan config/app.toml."
    )

    assert validate_code_integrity(source, translated) == ()


def test_code_validator_rejects_altered_identifier() -> None:
    issues = validate_code_integrity(
        make_source("Call `parse_value()` now."),
        make_translation("Panggil `delete_value()` sekarang."),
    )

    assert issue_codes(issues) == {ValidationCode.CODE_MISMATCH}


def test_citation_validator_accepts_preserved_citations() -> None:
    source = make_source("Evidence [12] agrees with (Smith, 2024), Figure 3.2, and Table 4.")
    translated = make_translation(
        "Bukti [12] sesuai dengan (Smith, 2024), Figure 3.2, dan Table 4."
    )

    assert validate_citation_integrity(source, translated) == ()


def test_citation_validator_rejects_altered_citation() -> None:
    issues = validate_citation_integrity(
        make_source("See [12]."),
        make_translation("Lihat [13]."),
    )

    assert issue_codes(issues) == {ValidationCode.CITATION_MISMATCH}


def test_language_validator_accepts_requested_target_language() -> None:
    issues = validate_target_language(
        make_translation("Sistem ini telah siap untuk digunakan oleh pengguna."),
        target_language="id-ID",
    )

    assert issues == ()


def test_language_validator_warns_for_probable_source_language_output() -> None:
    issues = validate_target_language(
        make_translation("The system is ready for use and is available."),
        target_language="id",
    )

    assert issue_codes(issues) == {ValidationCode.TARGET_LANGUAGE_MISMATCH}
    assert issues[0].severity is ValidationSeverity.WARNING


def test_untranslated_source_fragment_warns_for_leftover_english_marker() -> None:
    issues = validate_untranslated_source_fragments(
        make_source("The protected term sends a request."),
        make_translation("The istilah terlindungi mengirim permintaan."),
        target_language="id",
    )

    assert issue_codes(issues) == {ValidationCode.UNTRANSLATED_SOURCE_FRAGMENT}
    assert issues[0].severity is ValidationSeverity.WARNING


def test_untranslated_source_fragment_accepts_complete_translation() -> None:
    issues = validate_untranslated_source_fragments(
        make_source("The protected term sends a request."),
        make_translation("Istilah terlindungi mengirim permintaan."),
        target_language="id-ID",
    )

    assert issues == ()


def test_untranslated_source_fragment_ignores_protected_values() -> None:
    issues = validate_untranslated_source_fragments(
        make_source(f"The {PLACEHOLDER} is retained."),
        make_translation(f"{PLACEHOLDER} tetap dipertahankan."),
        target_language="id",
    )

    assert issues == ()


def test_empty_validator_accepts_nonempty_text() -> None:
    assert validate_empty_translation(make_translation("Hasil.")) == ()


@pytest.mark.parametrize("translated_text", ["", " ", "\n\t"])
def test_empty_validator_rejects_blank_text(translated_text: str) -> None:
    issues = validate_empty_translation(make_translation(translated_text))

    assert issue_codes(issues) == {ValidationCode.EMPTY_TRANSLATION}
    assert issues[0].severity is ValidationSeverity.CRITICAL


def test_length_validator_accepts_plausible_ratio() -> None:
    issues = validate_suspicious_length(
        make_source("A moderately long source sentence."),
        make_translation("Kalimat sumber yang cukup panjang."),
    )

    assert issues == ()


@pytest.mark.parametrize("translated_text", ["Pendek.", "Sangat panjang. " * 20])
def test_length_validator_warns_for_suspicious_ratio(translated_text: str) -> None:
    issues = validate_suspicious_length(
        make_source("This source sentence has enough content for a stable ratio check."),
        make_translation(translated_text),
    )

    assert issue_codes(issues) == {ValidationCode.SUSPICIOUS_LENGTH}
    assert issues[0].severity is ValidationSeverity.WARNING


def test_negation_fixture_is_reported_as_benchmark_warning() -> None:
    issues = validate_negation(
        make_source("The file is not deleted."),
        make_translation("File tersebut dihapus."),
    )

    assert issue_codes(issues) == {ValidationCode.NEGATION_MISMATCH}
    assert issues[0].severity is ValidationSeverity.WARNING


def test_negation_validator_accepts_preserved_negation() -> None:
    issues = validate_negation(
        make_source("The file is not deleted."),
        make_translation("File tersebut tidak dihapus."),
    )

    assert issues == ()


def test_aggregate_validator_accepts_valid_translation() -> None:
    request = make_request(
        ("segment_001",),
        source_text=f"The value is 25% at {PLACEHOLDER}.",
        placeholders=(make_placeholder(),),
    )
    response = make_response(
        ("segment_001",),
        translated_text=f"Nilainya adalah 25% pada {PLACEHOLDER}.",
    )

    report = validate_translation(request, response)

    assert report.passed is True
    assert report.accepted is True
    assert report.issues == ()


def test_critical_integrity_error_blocks_acceptance() -> None:
    request = make_request(("segment_001",), source_text="The value is 10.")
    response = make_response(("segment_001",), translated_text="Nilainya 99.")

    report = TranslationValidator().validate(request, response)

    assert report.accepted is False
    assert ValidationCode.NUMBER_MISMATCH in issue_codes(report.critical_issues)
    with pytest.raises(TranslationIntegrityError) as raised:
        report.raise_for_critical()
    assert raised.value.issues == report.critical_issues


def test_warning_does_not_masquerade_as_pass_but_remains_acceptable() -> None:
    request = make_request(
        ("segment_001",),
        source_text="The file is not deleted.",
    )
    response = make_response(
        ("segment_001",),
        translated_text="File tersebut dihapus.",
    )

    report = validate_translation(request, response)

    assert report.passed is False
    assert report.accepted is True
    assert issue_codes(report.warnings) == {ValidationCode.NEGATION_MISMATCH}
    report.raise_for_critical()


def test_aggregate_validator_warns_for_untranslated_source_fragment() -> None:
    request = make_request(
        ("segment_001",),
        source_text="The protected term sends a request.",
    )
    response = make_response(
        ("segment_001",),
        translated_text="The istilah terlindungi mengirim permintaan.",
    )

    report = validate_translation(request, response)

    assert report.accepted is True
    assert ValidationCode.UNTRANSLATED_SOURCE_FRAGMENT in issue_codes(report.warnings)


def test_validator_rejects_invalid_length_ratio_configuration() -> None:
    with pytest.raises(ValueError, match="positive and increasing"):
        TranslationValidator(minimum_length_ratio=2.0, maximum_length_ratio=1.0)


def make_request(
    segment_ids: tuple[str, ...],
    *,
    source_text: str = "Source text.",
    placeholders: tuple[TranslationPlaceholder, ...] = (),
) -> TranslationRequest:
    return TranslationRequest(
        segments=tuple(make_source(source_text, segment_id) for segment_id in segment_ids),
        context=TranslationContext(source_language="en", target_language="id"),
        glossary=(),
        placeholders=placeholders,
        style=TranslationStyle.PROFESSIONAL,
    )


def make_response(
    segment_ids: tuple[str, ...],
    *,
    translated_text: str = "Teks sumber.",
) -> TranslationResponse:
    return TranslationResponse(
        segments=tuple(make_translation(translated_text, segment_id) for segment_id in segment_ids)
    )


def make_source(
    source_text: str,
    segment_id: str = "segment_001",
) -> TranslationRequestSegment:
    return TranslationRequestSegment(segment_id=segment_id, source_text=source_text)


def make_translation(
    translated_text: str,
    segment_id: str = "segment_001",
) -> TranslatedSegment:
    return TranslatedSegment(segment_id=segment_id, translated_text=translated_text)


def make_placeholder(
    *,
    placeholder: str = PLACEHOLDER,
    item_type: str = "TERM",
) -> TranslationPlaceholder:
    return TranslationPlaceholder(
        segment_id="segment_001",
        placeholder=placeholder,
        item_type=item_type,
    )


def issue_codes(issues: tuple[ValidationIssue, ...]) -> set[ValidationCode]:
    return {issue.code for issue in issues}
