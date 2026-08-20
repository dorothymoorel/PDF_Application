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


class SegmentServiceError(ValueError):
    pass


class SegmentNotFoundError(SegmentServiceError):
    pass


class SegmentLockedError(SegmentServiceError):
    pass


class SegmentRevisionConflictError(SegmentServiceError):
    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__("The segment revision does not match.")
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class EmptySegmentTranslationError(SegmentServiceError):
    pass


@dataclass(frozen=True)
class EditSegmentTranslation:
    reviewed_translation: str
    expected_revision: int
    reason: str | None = None


CacheInvalidator = Callable[[str], None]


def invalidate_reconstruction_cache(_segment_id: str) -> None:
    """Invalidate the future reconstruction cache integration point."""


class SegmentService:
    def __init__(
        self,
        session: Session,
        *,
        invalidate_cache: CacheInvalidator | None = None,
    ) -> None:
        self._session = session
        self._invalidate_cache = invalidate_cache or invalidate_reconstruction_cache

    def edit_translation(
        self,
        segment_id: str,
        command: EditSegmentTranslation,
    ) -> DocumentSegment:
        reviewed_translation = command.reviewed_translation.strip()
        if not reviewed_translation:
            raise EmptySegmentTranslationError("The reviewed translation cannot be empty.")

        row = self._session.get(DocumentSegment, segment_id)
        if row is None:
            raise SegmentNotFoundError("The segment was not found.")
        if row.is_locked:
            raise SegmentLockedError("The segment is locked.")
        if row.current_revision != command.expected_revision:
            raise SegmentRevisionConflictError(
                command.expected_revision,
                row.current_revision,
            )

        now = _utc_now()
        revision_number = command.expected_revision + 1
        previous_text = row.final_text
        source_translation_id = self._latest_translation_id(segment_id)
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
                    reviewed_translation=reviewed_translation,
                    final_text=reviewed_translation,
                    status=SegmentStatus.USER_EDITED.value,
                    review_status=ReviewStatus.EDITED.value,
                    current_revision=revision_number,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            current = self._session.get(DocumentSegment, segment_id)
            if current is None:
                raise SegmentNotFoundError("The segment was not found.")
            if current.is_locked:
                raise SegmentLockedError("The segment is locked.")
            raise SegmentRevisionConflictError(
                command.expected_revision,
                current.current_revision,
            )

        self._session.add(
            SegmentRevision(
                id=f"rev_{uuid4()}",
                segment_id=segment_id,
                revision_number=revision_number,
                revision_type=SegmentRevisionType.USER_EDIT.value,
                previous_text=previous_text,
                new_text=reviewed_translation,
                source_translation_id=source_translation_id,
                reason=command.reason.strip() if command.reason else None,
                metadata_json=None,
                created_at=now,
            )
        )
        self._session.flush()
        self._invalidate_cache(segment_id)

        updated = self._session.get(DocumentSegment, segment_id)
        if updated is None:
            raise SegmentNotFoundError("The segment was not found after editing.")
        return updated

    def _latest_translation_id(self, segment_id: str) -> str | None:
        return self._session.scalar(
            select(SegmentTranslation.id)
            .where(SegmentTranslation.segment_id == segment_id)
            .order_by(SegmentTranslation.created_at.desc(), SegmentTranslation.id.desc())
            .limit(1)
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
