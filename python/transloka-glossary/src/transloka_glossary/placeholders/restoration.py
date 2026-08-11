import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from transloka_core.database.models.glossary import ProtectedItemType
from transloka_glossary.placeholders.generator import PlaceholderEntry
from transloka_glossary.protection import ProtectedInventoryItem

_ALLOWED_TYPES = "|".join(re.escape(item_type.value) for item_type in ProtectedItemType)
_PLACEHOLDER_PATTERN = re.compile(
    rf"__TLK_(?P<type>{_ALLOWED_TYPES})_"
    r"(?P<number>[0-9]{4,})_(?P<checksum>[0-9A-F]{2})__"
)
_PLACEHOLDER_LIKE_PATTERN = re.compile(r"__TLK[A-Za-z0-9_]*")
_LENIENT_IDENTITY_PATTERN = re.compile(r"__TLK_([A-Z_]+)_([0-9]+)_")


class PlaceholderIssueCode(StrEnum):
    MISSING = "MISSING"
    ALTERED = "ALTERED"
    DUPLICATED = "DUPLICATED"
    UNKNOWN = "UNKNOWN"
    MALFORMED = "MALFORMED"
    REORDERED = "REORDERED"


@dataclass(frozen=True, slots=True)
class PlaceholderIssue:
    code: PlaceholderIssueCode
    placeholder: str | None
    count: int | None = None


class InvalidPlaceholderInventoryError(ValueError):
    pass


class PlaceholderIntegrityError(ValueError):
    def __init__(self, issues: tuple[PlaceholderIssue, ...]) -> None:
        self.issues = issues
        codes = ", ".join(sorted({issue.code.value for issue in issues}))
        super().__init__(f"Critical placeholder integrity failure: {codes}.")

    @property
    def critical(self) -> bool:
        return True


class PlaceholderRestorer:
    def validate(
        self,
        text: str,
        inventory: Iterable[PlaceholderEntry | ProtectedInventoryItem],
        *,
        enforce_order: bool = True,
    ) -> tuple[PlaceholderIssue, ...]:
        if not isinstance(text, str):
            raise TypeError("Placeholder validation requires text input.")
        if not isinstance(enforce_order, bool):
            raise TypeError("Placeholder order enforcement must be a boolean.")

        records = _validate_inventory(inventory)
        expected = tuple(record.placeholder for record in records)
        expected_set = frozenset(expected)
        expected_by_number = {
            _placeholder_identity(placeholder)[1]: placeholder for placeholder in expected
        }
        matches = tuple(_PLACEHOLDER_PATTERN.finditer(text))
        observed = tuple(match.group(0) for match in matches)
        counts = Counter(observed)
        issues: list[PlaceholderIssue] = []

        for placeholder in expected:
            count = counts[placeholder]
            if count == 0:
                issues.append(
                    PlaceholderIssue(
                        code=PlaceholderIssueCode.MISSING,
                        placeholder=placeholder,
                        count=0,
                    )
                )
            elif count > 1:
                issues.append(
                    PlaceholderIssue(
                        code=PlaceholderIssueCode.DUPLICATED,
                        placeholder=placeholder,
                        count=count,
                    )
                )

        for placeholder in dict.fromkeys(observed):
            if placeholder in expected_set:
                continue
            _item_type, number, _checksum = _placeholder_identity(placeholder)
            code = (
                PlaceholderIssueCode.ALTERED
                if number in expected_by_number
                else PlaceholderIssueCode.UNKNOWN
            )
            issues.append(
                PlaceholderIssue(
                    code=code,
                    placeholder=placeholder,
                    count=counts[placeholder],
                )
            )

        strict_starts = {match.start() for match in matches}
        for match in _PLACEHOLDER_LIKE_PATTERN.finditer(text):
            if match.start() in strict_starts:
                continue
            fragment = match.group(0)
            issues.append(
                PlaceholderIssue(
                    code=PlaceholderIssueCode.MALFORMED,
                    placeholder=fragment,
                )
            )
            identity = _LENIENT_IDENTITY_PATTERN.match(fragment)
            if identity is not None and int(identity.group(2)) in expected_by_number:
                issues.append(
                    PlaceholderIssue(
                        code=PlaceholderIssueCode.ALTERED,
                        placeholder=fragment,
                    )
                )

        if enforce_order and all(counts[placeholder] == 1 for placeholder in expected):
            known_order = tuple(
                placeholder for placeholder in observed if placeholder in expected_set
            )
            if known_order != expected:
                issues.append(
                    PlaceholderIssue(
                        code=PlaceholderIssueCode.REORDERED,
                        placeholder=None,
                    )
                )

        return tuple(sorted(issues, key=_issue_order))

    def restore(
        self,
        text: str,
        inventory: Iterable[PlaceholderEntry | ProtectedInventoryItem],
        *,
        enforce_order: bool = True,
    ) -> str:
        records = _validate_inventory(inventory)
        issues = self.validate(text, records, enforce_order=enforce_order)
        if issues:
            raise PlaceholderIntegrityError(issues)

        restoration_map = {record.placeholder: record.source_value for record in records}
        return _PLACEHOLDER_PATTERN.sub(
            lambda match: restoration_map[match.group(0)],
            text,
        )


def _validate_inventory(
    inventory: Iterable[PlaceholderEntry | ProtectedInventoryItem],
) -> tuple[PlaceholderEntry | ProtectedInventoryItem, ...]:
    records = tuple(inventory)
    if not all(
        isinstance(record, (PlaceholderEntry, ProtectedInventoryItem)) for record in records
    ):
        raise InvalidPlaceholderInventoryError(
            "Every restoration record must be a placeholder inventory item."
        )
    placeholders = [record.placeholder for record in records]
    if len(placeholders) != len(set(placeholders)):
        raise InvalidPlaceholderInventoryError("Placeholder inventory must contain unique tokens.")
    if any(_PLACEHOLDER_PATTERN.fullmatch(placeholder) is None for placeholder in placeholders):
        raise InvalidPlaceholderInventoryError("Placeholder inventory contains an invalid token.")
    numbers = [_placeholder_identity(placeholder)[1] for placeholder in placeholders]
    if len(numbers) != len(set(numbers)):
        raise InvalidPlaceholderInventoryError("Placeholder inventory numbers must be unique.")
    return records


def _placeholder_identity(placeholder: str) -> tuple[str, int, str]:
    match = _PLACEHOLDER_PATTERN.fullmatch(placeholder)
    if match is None:
        raise InvalidPlaceholderInventoryError("Placeholder inventory contains an invalid token.")
    return match.group("type"), int(match.group("number")), match.group("checksum")


def _issue_order(issue: PlaceholderIssue) -> tuple[object, ...]:
    return (
        issue.code.value,
        issue.placeholder or "",
        issue.count if issue.count is not None else -1,
    )
