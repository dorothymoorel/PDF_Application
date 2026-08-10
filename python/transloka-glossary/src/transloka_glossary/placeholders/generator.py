import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

from transloka_core.database.models.glossary import ProtectedItemType

_MINIMUM_NUMBER_WIDTH = 4
_CHECKSUM_SPACE = 256
_PLACEHOLDER_PATTERN = re.compile(
    rf"__TLK_(?:{'|'.join(re.escape(value.value) for value in ProtectedItemType)})_"
    rf"[0-9]{{{_MINIMUM_NUMBER_WIDTH},}}_[0-9A-F]{{2}}__"
)


class InvalidPlaceholderError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlaceholderEntry:
    placeholder: str
    item_type: ProtectedItemType
    number: int
    checksum: str
    source_value: str


class PlaceholderGenerator:
    def __init__(self, source_text: str) -> None:
        if not isinstance(source_text, str):
            raise InvalidPlaceholderError("Placeholder generation requires source text.")
        self._occupied = {match.group(0) for match in _PLACEHOLDER_PATTERN.finditer(source_text)}
        self._entries: list[PlaceholderEntry] = []
        self._next_number = 1

    @property
    def inventory(self) -> tuple[PlaceholderEntry, ...]:
        return tuple(self._entries)

    @property
    def restoration_map(self) -> Mapping[str, str]:
        return MappingProxyType({entry.placeholder: entry.source_value for entry in self._entries})

    def generate(
        self,
        item_type: ProtectedItemType,
        source_value: str,
    ) -> PlaceholderEntry:
        if not isinstance(item_type, ProtectedItemType):
            raise InvalidPlaceholderError("The protected item type is not allowed.")
        if not isinstance(source_value, str) or not source_value:
            raise InvalidPlaceholderError("A protected item requires a source value.")

        number = self._next_number
        while True:
            checksum_seed = _checksum_seed(item_type, number, source_value)
            for collision_offset in range(_CHECKSUM_SPACE):
                checksum = f"{(checksum_seed + collision_offset) % _CHECKSUM_SPACE:02X}"
                placeholder = _format_placeholder(item_type, number, checksum)
                if placeholder in self._occupied:
                    continue

                entry = PlaceholderEntry(
                    placeholder=placeholder,
                    item_type=item_type,
                    number=number,
                    checksum=checksum,
                    source_value=source_value,
                )
                self._occupied.add(placeholder)
                self._entries.append(entry)
                self._next_number = number + 1
                return entry
            number += 1


def _checksum_seed(
    item_type: ProtectedItemType,
    number: int,
    source_value: str,
) -> int:
    digest = sha256(
        b"\0".join(
            (
                item_type.value.encode("ascii"),
                str(number).encode("ascii"),
                source_value.encode("utf-8"),
            )
        )
    ).digest()
    return digest[0]


def _format_placeholder(
    item_type: ProtectedItemType,
    number: int,
    checksum: str,
) -> str:
    return f"__TLK_{item_type.value}_{number:0{_MINIMUM_NUMBER_WIDTH}d}_{checksum}__"
