"""Safe external hyperlink values used during reconstruction.

This module only parses and validates link strings.  It deliberately has no
HTTP client, URL opener, DNS resolver, or preview operation: reconstruction
preserves a safe target as metadata and leaves navigation to the final PDF
consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import SplitResult, urlsplit


class LinkSafetyError(ValueError):
    """Raised when a hyperlink cannot safely be preserved."""


class LinkStatus(StrEnum):
    """Outcome of validating an external hyperlink target."""

    PRESERVED = "PRESERVED"
    DISABLED = "DISABLED"
    BROKEN = "BROKEN"


class LinkWarningCode(StrEnum):
    """Stable warning codes for unsafe or malformed hyperlink targets."""

    UNSAFE_SCHEME = "UNSAFE_HYPERLINK_SCHEME"
    INVALID_TARGET = "INVALID_HYPERLINK_TARGET"


class AllowedLinkScheme(StrEnum):
    """Schemes permitted for preserved external hyperlinks."""

    HTTP = "http"
    HTTPS = "https"
    MAILTO = "mailto"


ALLOWED_LINK_SCHEMES: Final[frozenset[str]] = frozenset(
    scheme.value for scheme in AllowedLinkScheme
)


def _non_empty_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise LinkSafetyError(f"{field_name} must be a non-empty string.")
    return value


def _has_control_or_whitespace(value: str) -> bool:
    return any(character.isspace() or ord(character) < 0x20 for character in value)


def _scheme(parsed: SplitResult) -> str | None:
    return parsed.scheme.casefold() or None


def _parse_target(value: object) -> tuple[str, SplitResult]:
    target = _non_empty_text(value, "target_url").strip()
    if _has_control_or_whitespace(target):
        raise LinkSafetyError("target_url must not contain whitespace or control characters.")
    try:
        parsed = urlsplit(target)
    except ValueError as exc:
        raise LinkSafetyError("target_url is not a valid URL.") from exc
    return target, parsed


def _valid_http_target(parsed: SplitResult) -> bool:
    if not parsed.netloc:
        return False
    try:
        port = parsed.port
        return parsed.hostname is not None and (port is None or port >= 0)
    except ValueError:
        return False


def _valid_mailto_target(parsed: SplitResult) -> bool:
    # ``mailto:recipient@example.test`` is the URI form.  A netloc form such
    # as ``mailto://recipient`` is not accepted because it is ambiguous.
    return bool(parsed.path and not parsed.netloc and "@" in parsed.path)


@dataclass(frozen=True, slots=True)
class ExternalLinkPolicy:
    """Policy controlling which URI schemes can be preserved."""

    allowed_schemes: frozenset[str] = ALLOWED_LINK_SCHEMES

    def __post_init__(self) -> None:
        normalized = frozenset(
            _non_empty_text(scheme, "allowed_schemes").casefold() for scheme in self.allowed_schemes
        )
        if not normalized <= ALLOWED_LINK_SCHEMES:
            raise LinkSafetyError("allowed_schemes may only contain http, https, or mailto.")
        object.__setattr__(self, "allowed_schemes", normalized)


@dataclass(frozen=True, slots=True)
class LinkValidation:
    """Auditable validation result; it never performs a network operation."""

    target_url: str
    scheme: str | None
    status: LinkStatus
    warning_code: LinkWarningCode | None = None
    reason: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status is LinkStatus.PRESERVED

    @property
    def safe(self) -> bool:
        return self.allowed

    @property
    def broken(self) -> bool:
        return self.status is LinkStatus.BROKEN

    @property
    def disabled(self) -> bool:
        return self.status is LinkStatus.DISABLED

    def raise_for_unsafe(self) -> None:
        if self.allowed:
            return
        detail = self.reason or self.status.value.casefold()
        raise LinkSafetyError(f"External hyperlink was not preserved: {detail}.")


@dataclass(frozen=True, slots=True)
class PreservedHyperlink:
    """A safe link with an optionally translated visible label."""

    visible_text: str
    target_url: str
    display_text: str
    validation: LinkValidation

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_text", _non_empty_text(self.visible_text, "visible_text"))
        object.__setattr__(self, "display_text", _non_empty_text(self.display_text, "display_text"))
        if not self.validation.allowed:
            raise LinkSafetyError("PreservedHyperlink requires an allowed target URL.")
        if self.target_url != self.validation.target_url:
            raise LinkSafetyError("target_url must match the validated URL.")

    @property
    def scheme(self) -> str:
        return self.validation.scheme or ""

    @property
    def fetched(self) -> bool:
        """Always false: reconstruction never fetches external links."""

        return False


SafeHyperlink = PreservedHyperlink
Hyperlink = PreservedHyperlink
ExternalHyperlink = PreservedHyperlink
HyperlinkStatus = LinkStatus
HyperlinkWarningCode = LinkWarningCode
LinkScheme = AllowedLinkScheme


@dataclass(frozen=True, slots=True)
class HyperlinkDecision:
    """Non-raising result for callers that need to disable broken links."""

    visible_text: str
    display_text: str
    original_target_url: str
    target_url: str | None
    validation: LinkValidation

    @property
    def preserved(self) -> bool:
        return self.validation.allowed

    @property
    def enabled(self) -> bool:
        return self.preserved and self.target_url is not None

    @property
    def fetched(self) -> bool:
        return False


def validate_external_url(
    target_url: object,
    *,
    policy: ExternalLinkPolicy | None = None,
) -> LinkValidation:
    """Validate an external target without opening or resolving it."""

    effective_policy = policy or ExternalLinkPolicy()
    try:
        target, parsed = _parse_target(target_url)
    except LinkSafetyError as exc:
        raw = target_url if isinstance(target_url, str) else str(target_url)
        return LinkValidation(
            target_url=raw,
            scheme=None,
            status=LinkStatus.BROKEN,
            warning_code=LinkWarningCode.INVALID_TARGET,
            reason=str(exc),
        )

    scheme = _scheme(parsed)
    if scheme is None or scheme not in effective_policy.allowed_schemes:
        return LinkValidation(
            target_url=target,
            scheme=scheme,
            status=LinkStatus.DISABLED,
            warning_code=LinkWarningCode.UNSAFE_SCHEME,
            reason=f"scheme {scheme or 'missing'} is not allowed",
        )

    if scheme in {AllowedLinkScheme.HTTP.value, AllowedLinkScheme.HTTPS.value}:
        valid_target = _valid_http_target(parsed)
    else:
        valid_target = _valid_mailto_target(parsed)
    if not valid_target:
        return LinkValidation(
            target_url=target,
            scheme=scheme,
            status=LinkStatus.BROKEN,
            warning_code=LinkWarningCode.INVALID_TARGET,
            reason="the allowed URL scheme has no valid target",
        )
    return LinkValidation(target, scheme, LinkStatus.PRESERVED)


def is_safe_external_url(target_url: object) -> bool:
    """Return whether a target is safe to preserve as an external link."""

    return validate_external_url(target_url).allowed


def sanitize_external_url(target_url: object) -> str | None:
    """Return a safe target unchanged, or ``None`` when it must be disabled."""

    validation = validate_external_url(target_url)
    return validation.target_url if validation.allowed else None


def process_external_hyperlink(
    visible_text: object,
    target_url: object,
    *,
    translated_text: object | None = None,
    policy: ExternalLinkPolicy | None = None,
) -> HyperlinkDecision:
    """Preserve a safe link and label, or disable only its unsafe target."""

    label = _non_empty_text(visible_text, "visible_text")
    display_text = (
        label if translated_text is None else _non_empty_text(translated_text, "translated_text")
    )
    original = target_url if isinstance(target_url, str) else str(target_url)
    validation = validate_external_url(target_url, policy=policy)
    return HyperlinkDecision(
        visible_text=label,
        display_text=display_text,
        original_target_url=original,
        target_url=validation.target_url if validation.allowed else None,
        validation=validation,
    )


def preserve_external_hyperlink(
    visible_text: object,
    target_url: object,
    *,
    translated_text: object | None = None,
    policy: ExternalLinkPolicy | None = None,
) -> PreservedHyperlink:
    """Return a preserved hyperlink or raise for an unsafe/broken target."""

    decision = process_external_hyperlink(
        visible_text,
        target_url,
        translated_text=translated_text,
        policy=policy,
    )
    decision.validation.raise_for_unsafe()
    return PreservedHyperlink(
        visible_text=decision.visible_text,
        target_url=decision.target_url or "",
        display_text=decision.display_text,
        validation=decision.validation,
    )


reconstruct_hyperlink = process_external_hyperlink
validate_link = validate_external_url


__all__ = [
    "ALLOWED_LINK_SCHEMES",
    "AllowedLinkScheme",
    "ExternalLinkPolicy",
    "ExternalHyperlink",
    "Hyperlink",
    "HyperlinkDecision",
    "HyperlinkStatus",
    "HyperlinkWarningCode",
    "LinkScheme",
    "LinkSafetyError",
    "LinkStatus",
    "LinkValidation",
    "LinkWarningCode",
    "PreservedHyperlink",
    "SafeHyperlink",
    "is_safe_external_url",
    "preserve_external_hyperlink",
    "process_external_hyperlink",
    "reconstruct_hyperlink",
    "sanitize_external_url",
    "validate_external_url",
    "validate_link",
]
