from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO
from urllib.parse import urlsplit

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

_ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto"})
_MAX_VISITED_CONTAINERS = 100_000


class ActiveContentWarningCode(StrEnum):
    EMBEDDED_JAVASCRIPT = "PDF_EMBEDDED_JAVASCRIPT_DETECTED"
    EMBEDDED_ATTACHMENT = "PDF_EMBEDDED_ATTACHMENT_DETECTED"
    LAUNCH_ACTION = "PDF_LAUNCH_ACTION_DETECTED"
    UNSAFE_URL_SCHEME = "PDF_UNSAFE_URL_SCHEME_DETECTED"


@dataclass(frozen=True, slots=True)
class ActiveContentWarning:
    code: ActiveContentWarningCode
    message: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActiveContentReport:
    warnings: tuple[ActiveContentWarning, ...]

    @property
    def has_active_content(self) -> bool:
        return bool(self.warnings)

    @property
    def warning_codes(self) -> tuple[ActiveContentWarningCode, ...]:
        return tuple(warning.code for warning in self.warnings)


class ActiveContentInspectionError(RuntimeError):
    pass


def detect_active_content(stream: BinaryIO) -> ActiveContentReport:
    original_position: int | None = None
    try:
        original_position = stream.tell()
        stream.seek(0)
        reader = PdfReader(stream, strict=False)
        javascript = False
        attachment = False
        launch = False
        unsafe_schemes: set[str] = set()

        for dictionary in _walk_dictionaries(reader.root_object):
            action = str(dictionary.get("/S", ""))
            javascript = (
                javascript
                or action == "/JavaScript"
                or any(key in dictionary for key in ("/JavaScript", "/JS"))
            )
            attachment = (
                attachment
                or any(key in dictionary for key in ("/EmbeddedFiles", "/EF", "/AF"))
                or str(dictionary.get("/Subtype", "")) == "/FileAttachment"
            )
            launch = launch or action == "/Launch"
            if action == "/URI" and "/URI" in dictionary:
                scheme = _url_scheme(dictionary["/URI"])
                if scheme not in _ALLOWED_URL_SCHEMES:
                    unsafe_schemes.add(scheme or "missing")

        return ActiveContentReport(
            warnings=_warnings(javascript, attachment, launch, unsafe_schemes)
        )
    except ActiveContentInspectionError:
        raise
    except Exception as exc:
        raise ActiveContentInspectionError(
            "The PDF active content could not be inspected safely."
        ) from exc
    finally:
        if original_position is not None:
            try:
                stream.seek(original_position)
            except (OSError, ValueError):
                pass


def _walk_dictionaries(root: object) -> Iterator[DictionaryObject]:
    stack = [root]
    seen_indirect: set[tuple[int, int]] = set()
    seen_containers: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, IndirectObject):
            reference = (current.idnum, current.generation)
            if reference in seen_indirect:
                continue
            seen_indirect.add(reference)
            current = current.get_object()

        if not isinstance(current, (DictionaryObject, ArrayObject)):
            continue
        identity = id(current)
        if identity in seen_containers:
            continue
        seen_containers.add(identity)
        if len(seen_containers) > _MAX_VISITED_CONTAINERS:
            raise ActiveContentInspectionError(
                "The PDF object graph exceeds the active-content inspection limit."
            )

        if isinstance(current, DictionaryObject):
            yield current
            stack.extend(current.values())
        else:
            stack.extend(current)


def _url_scheme(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return urlsplit(text.strip()).scheme.casefold()


def _warnings(
    javascript: bool,
    attachment: bool,
    launch: bool,
    unsafe_schemes: set[str],
) -> tuple[ActiveContentWarning, ...]:
    warnings: list[ActiveContentWarning] = []
    if javascript:
        warnings.append(
            ActiveContentWarning(
                ActiveContentWarningCode.EMBEDDED_JAVASCRIPT,
                "The PDF contains embedded JavaScript that will not be executed.",
            )
        )
    if attachment:
        warnings.append(
            ActiveContentWarning(
                ActiveContentWarningCode.EMBEDDED_ATTACHMENT,
                "The PDF contains an attachment that will not be opened or extracted.",
            )
        )
    if launch:
        warnings.append(
            ActiveContentWarning(
                ActiveContentWarningCode.LAUNCH_ACTION,
                "The PDF contains a launch action that will not be executed.",
            )
        )
    if unsafe_schemes:
        warnings.append(
            ActiveContentWarning(
                ActiveContentWarningCode.UNSAFE_URL_SCHEME,
                "The PDF contains a link with a URL scheme that is not allowed.",
                tuple(sorted(unsafe_schemes)),
            )
        )
    return tuple(warnings)
