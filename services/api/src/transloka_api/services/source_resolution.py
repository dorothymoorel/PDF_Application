from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from transloka_core.database.models.document_ir import (
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType
from transloka_core.database.models.translation import SegmentTranslation


class SourceResolutionError(ValueError):
    """Base error for source resolution commands."""


class SourceSegmentNotFoundError(SourceResolutionError):
    pass


class SourceSegmentLockedError(SourceResolutionError):
    pass


class SourceRevisionConflictError(SourceResolutionError):
    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__("The segment revision does not match.")
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class EmptyResolvedSourceError(SourceResolutionError):
    pass


class InvalidResolutionSourceError(SourceResolutionError):
    pass


@dataclass(frozen=True, slots=True)
class ResolveSource:
    resolved_source_text: str
    expected_revision: int
    resolution_source: str = "MANUAL"
    reason: str | None = None


TranslationInvalidator = Callable[[str], None]


def invalidate_downstream_translation(_segment_id: str) -> None:
    """Integration point for future translation/reconstruction cache invalidation."""


class SourceResolutionService:
    """Resolve OCR source without replacing the raw OCR value."""

    _allowed_resolution_sources = frozenset({"AUTO", "AUTOMATIC", "MANUAL", "NATIVE", "OCR"})

    def __init__(
        self,
        session: Session,
        *,
        invalidate_translation: TranslationInvalidator | None = None,
        invalidate_cache: TranslationInvalidator | None = None,
    ) -> None:
        self._session = session
        self._invalidate_translation = (
            invalidate_translation or invalidate_cache or invalidate_downstream_translation
        )

    def resolve(self, segment_id: str, command: ResolveSource) -> DocumentSegment:
        resolved_source_text = command.resolved_source_text.strip()
        if not resolved_source_text:
            raise EmptyResolvedSourceError("The resolved source text cannot be empty.")
        if command.expected_revision < 0:
            raise SourceRevisionConflictError(command.expected_revision, 0)

        resolution_source = command.resolution_source.strip().upper()
        if resolution_source not in self._allowed_resolution_sources:
            raise InvalidResolutionSourceError("The resolution source is not supported.")

        segment = self._session.get(DocumentSegment, segment_id)
        if segment is None:
            raise SourceSegmentNotFoundError("The segment was not found.")
        if segment.is_locked:
            raise SourceSegmentLockedError("The segment is locked.")
        if segment.current_revision != command.expected_revision:
            raise SourceRevisionConflictError(
                command.expected_revision,
                segment.current_revision,
            )
        previous_source_text = segment.resolved_source_text
        if resolved_source_text == previous_source_text:
            return segment

        now = _utc_now()
        next_revision = command.expected_revision + 1
        source_translation_id = self._latest_translation_id(segment_id)
        normalized_source_text = _normalize_source_text(resolved_source_text)
        metadata_json = json.dumps(
            {
                "event": "SOURCE_CORRECTION",
                "raw_ocr_preserved": True,
                "resolution_source": resolution_source,
                "translation_invalidated": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(DocumentSegment)
                .where(
                    DocumentSegment.id == segment_id,
                    DocumentSegment.current_revision == command.expected_revision,
                    DocumentSegment.is_locked == 0,
                )
                .values(
                    resolved_source_text=resolved_source_text,
                    normalized_source_text=normalized_source_text,
                    protected_source_text=None,
                    machine_translation=None,
                    reviewed_translation=None,
                    final_text=None,
                    translation_settings_hash=None,
                    status=SegmentStatus.READY_FOR_TRANSLATION.value,
                    review_status=ReviewStatus.NOT_REVIEWED.value,
                    current_revision=next_revision,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            current = self._session.get(DocumentSegment, segment_id)
            if current is None:
                raise SourceSegmentNotFoundError("The segment was not found.")
            if current.is_locked:
                raise SourceSegmentLockedError("The segment is locked.")
            raise SourceRevisionConflictError(
                command.expected_revision,
                current.current_revision,
            )

        self._session.add(
            SegmentRevision(
                id=f"rev_{uuid4()}",
                segment_id=segment_id,
                revision_number=next_revision,
                revision_type=SegmentRevisionType.USER_EDIT.value,
                previous_text=previous_source_text,
                new_text=resolved_source_text,
                source_translation_id=source_translation_id,
                reason=(
                    command.reason.strip()
                    if command.reason and command.reason.strip()
                    else f"Source resolution ({resolution_source})."
                ),
                metadata_json=metadata_json,
                created_at=now,
            )
        )
        self._session.flush()
        self._invalidate_translation(segment_id)

        updated = self._session.get(DocumentSegment, segment_id)
        if updated is None:
            raise SourceSegmentNotFoundError("The segment was not found after source resolution.")
        return updated

    def resolve_source(self, segment_id: str, command: ResolveSource) -> DocumentSegment:
        """Compatibility name for callers that use an explicit source verb."""

        return self.resolve(segment_id, command)

    def _latest_translation_id(self, segment_id: str) -> str | None:
        return self._session.scalar(
            select(SegmentTranslation.id)
            .where(SegmentTranslation.segment_id == segment_id)
            .order_by(SegmentTranslation.created_at.desc(), SegmentTranslation.id.desc())
            .limit(1)
        )


def _normalize_source_text(value: str) -> str:
    lines = value.splitlines() or (value,)
    normalized_lines: list[str] = []
    for line in lines:
        cleaned = " ".join(line.split())
        if not cleaned:
            continue
        if normalized_lines and _is_hyphenated_break(normalized_lines[-1], cleaned):
            normalized_lines[-1] = normalized_lines[-1][:-1] + cleaned
        else:
            normalized_lines.append(cleaned)
    return " ".join(normalized_lines).strip()


def _is_hyphenated_break(previous: str, following: str) -> bool:
    return (
        len(previous) >= 2
        and previous.endswith("-")
        and previous[-2].isalpha()
        and following[0].isalpha()
        and following[0].islower()
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


SourceResolutionCommand = ResolveSource
