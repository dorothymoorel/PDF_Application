from __future__ import annotations

import pytest
from transloka_reconstruction.links import (
    LinkSafetyError,
    LinkStatus,
    LinkWarningCode,
    is_safe_external_url,
    preserve_external_hyperlink,
    process_external_hyperlink,
    validate_external_url,
)


@pytest.mark.parametrize(
    ("target_url", "scheme"),
    (
        ("http://example.test/docs", "http"),
        ("https://example.test/docs", "https"),
        ("mailto:owner@example.test", "mailto"),
    ),
)
def test_allowed_external_schemes_are_preserved(
    target_url: str,
    scheme: str,
) -> None:
    result = validate_external_url(target_url)

    assert result.status is LinkStatus.PRESERVED
    assert result.allowed
    assert result.scheme == scheme
    assert result.target_url == target_url
    assert is_safe_external_url(target_url)


@pytest.mark.parametrize(
    "target_url",
    (
        "javascript:alert(1)",
        "file:///C:/secrets.txt",
        "shell:open_calculator",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.test/file",
    ),
)
def test_unsafe_schemes_are_disabled_by_default(target_url: str) -> None:
    result = validate_external_url(target_url)

    assert result.status is LinkStatus.DISABLED
    assert result.warning_code is LinkWarningCode.UNSAFE_SCHEME
    assert not result.allowed
    assert not is_safe_external_url(target_url)
    assert process_external_hyperlink("Open link", target_url).target_url is None


def test_translated_visible_label_does_not_change_safe_target() -> None:
    result = process_external_hyperlink(
        "OpenAI documentation",
        "https://example.test/docs",
        translated_text="Dokumentasi OpenAI",
    )

    assert result.preserved
    assert result.visible_text == "OpenAI documentation"
    assert result.display_text == "Dokumentasi OpenAI"
    assert result.target_url == "https://example.test/docs"
    assert result.fetched is False

    preserved = preserve_external_hyperlink(
        "OpenAI documentation",
        "https://example.test/docs",
        translated_text="Dokumentasi OpenAI",
    )
    assert preserved.display_text == "Dokumentasi OpenAI"
    assert preserved.target_url == "https://example.test/docs"
    assert preserved.fetched is False


@pytest.mark.parametrize(
    "target_url",
    (
        "https://",
        "http:example.test",
        "mailto:",
        "mailto://owner@example.test",
        "https://example.test/a b",
    ),
)
def test_broken_targets_are_reported_and_disabled(target_url: str) -> None:
    result = process_external_hyperlink("Broken link", target_url)

    assert result.validation.status is LinkStatus.BROKEN
    assert result.validation.warning_code is LinkWarningCode.INVALID_TARGET
    assert result.target_url is None
    assert not result.enabled

    with pytest.raises(LinkSafetyError):
        preserve_external_hyperlink("Broken link", target_url)


def test_validation_never_fetches_or_resolves_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is outside hyperlink reconstruction")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_called, raising=False)
    monkeypatch.setattr("socket.create_connection", fail_if_called, raising=False)

    result = process_external_hyperlink("Safe link", "https://example.test")

    assert result.preserved
    assert result.fetched is False
