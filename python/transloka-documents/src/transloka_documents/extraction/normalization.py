import re
from collections.abc import Sequence

from transloka_documents.extraction.models import (
    NormalizationBoundary,
    NormalizationKind,
    NormalizedText,
)

_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
_LIST_ITEM_PREFIX = re.compile(r"^(?:[-*\u2022]\s+|\d+[.)]\s+|[A-Za-z][.)]\s+)")


def normalize_source_lines(lines: Sequence[str]) -> NormalizedText:
    source_text = "\n".join(lines)
    output: list[str] = []
    boundaries: list[NormalizationBoundary] = []
    source_offset = 0

    for line_index, line in enumerate(lines):
        if line_index:
            previous_line = lines[line_index - 1]
            _append_line_boundary(
                output,
                boundaries,
                previous_line=previous_line,
                next_line=line,
                source_offset=source_offset - 1,
            )

        _append_normalized_line(
            line,
            source_offset=source_offset,
            output=output,
            boundaries=boundaries,
        )
        source_offset += len(line) + 1

    return NormalizedText(
        source_text=source_text,
        text="".join(output),
        boundaries=tuple(boundaries),
    )


def _append_normalized_line(
    line: str,
    *,
    source_offset: int,
    output: list[str],
    boundaries: list[NormalizationBoundary],
) -> None:
    index = 0
    while index < len(line):
        character = line[index]
        normalized_start = _output_length(output)

        if character in _LIGATURES:
            replacement = _LIGATURES[character]
            output.append(replacement)
            boundaries.append(
                _boundary(
                    NormalizationKind.LIGATURE,
                    source_offset + index,
                    source_offset + index + 1,
                    normalized_start,
                    normalized_start + len(replacement),
                    character,
                    replacement,
                )
            )
            index += 1
            continue

        if character == "\u00ad":
            boundaries.append(
                _boundary(
                    NormalizationKind.SOFT_HYPHEN,
                    source_offset + index,
                    source_offset + index + 1,
                    normalized_start,
                    normalized_start,
                    character,
                    "",
                )
            )
            index += 1
            continue

        if character.isspace():
            whitespace_end = index + 1
            while whitespace_end < len(line) and line[whitespace_end].isspace():
                whitespace_end += 1
            replacement = " "
            output.append(replacement)
            source_fragment = line[index:whitespace_end]
            if source_fragment != replacement:
                boundaries.append(
                    _boundary(
                        NormalizationKind.WHITESPACE,
                        source_offset + index,
                        source_offset + whitespace_end,
                        normalized_start,
                        normalized_start + 1,
                        source_fragment,
                        replacement,
                    )
                )
            index = whitespace_end
            continue

        output.append(character)
        index += 1


def _append_line_boundary(
    output: list[str],
    boundaries: list[NormalizationBoundary],
    *,
    previous_line: str,
    next_line: str,
    source_offset: int,
) -> None:
    normalized_start = _output_length(output)
    hyphenated = _is_hyphenated_line_break(previous_line, next_line)
    if hyphenated and output and output[-1].endswith("-"):
        output[-1] = output[-1][:-1]
        normalized_start -= 1
        source_start = source_offset - 1
        source_text = "-\n"
        kind = NormalizationKind.HYPHENATED_LINE_BREAK
        replacement = ""
    elif _LIST_ITEM_PREFIX.match(next_line.lstrip()):
        output.append("\n")
        source_start = source_offset
        source_text = "\n"
        kind = NormalizationKind.PRESERVED_LINE_BREAK
        replacement = "\n"
    else:
        output.append(" ")
        source_start = source_offset
        source_text = "\n"
        kind = NormalizationKind.VISUAL_LINE_BREAK
        replacement = " "

    boundaries.append(
        _boundary(
            kind,
            source_start,
            source_offset + 1,
            normalized_start,
            normalized_start + len(replacement),
            source_text,
            replacement,
        )
    )


def _is_hyphenated_line_break(previous_line: str, next_line: str) -> bool:
    previous = previous_line.rstrip()
    following = next_line.lstrip()
    return (
        len(previous) >= 2
        and previous.endswith("-")
        and previous[-2].isalpha()
        and bool(following)
        and following[0].islower()
        and following[0].isalpha()
    )


def _output_length(output: Sequence[str]) -> int:
    return sum(map(len, output))


def _boundary(
    kind: NormalizationKind,
    source_start: int,
    source_end: int,
    normalized_start: int,
    normalized_end: int,
    source_text: str,
    normalized_text: str,
) -> NormalizationBoundary:
    return NormalizationBoundary(
        kind=kind,
        source_start=source_start,
        source_end=source_end,
        normalized_start=normalized_start,
        normalized_end=normalized_end,
        source_text=source_text,
        normalized_text=normalized_text,
    )
