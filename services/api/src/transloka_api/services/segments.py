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


class SegmentLockStateError(SegmentServiceError):
    pass


class EmptyUnlockReasonError(SegmentServiceError):
    pass


@dataclass(frozen=True)
class EditSegmentTranslation:
    reviewed_translation: str
    expected_revision: int
    reason: str | None = None


@dataclass(frozen=True)
class LockSegment:
    expected_revision: int


@dataclass(frozen=True)
class UnlockSegment:
    expected_revision: int
    reason: str


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

    def lock(self, segment_id: str, command: LockSegment) -> DocumentSegment:
        row = self._session.get(DocumentSegment, segment_id)
        if row is None:
            raise SegmentNotFoundError("The segment was not found.")
        if row.is_locked:
            raise SegmentLockStateError("The segment is already locked.")
        if row.review_status != ReviewStatus.APPROVED.value:
            raise SegmentLockStateError("Only approved segments can be locked.")
        if row.current_revision != command.expected_revision:
            raise SegmentRevisionConflictError(
                command.expected_revision,
                row.current_revision,
            )

        current_text = self._current_text(row)
        now = _utc_now()
        revision_number = command.expected_revision + 1
        source_translation_id = self._latest_translation_id(segment_id)
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(DocumentSegment)
                .where(
                    DocumentSegment.id == segment_id,
                    DocumentSegment.current_revision == command.expected_revision,
                    DocumentSegment.is_locked == 0,
                    DocumentSegment.review_status == ReviewStatus.APPROVED.value,
                )
                .values(
                    status=SegmentStatus.LOCKED.value,
                    is_locked=1,
                    current_revision=revision_number,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            self._raise_lock_race_error(segment_id, command.expected_revision)

        self._session.add(
            SegmentRevision(
                id=f"rev_{uuid4()}",
                segment_id=segment_id,
                revision_number=revision_number,
                revision_type=SegmentRevisionType.LOCK.value,
                previous_text=current_text,
                new_text=current_text,
                source_translation_id=source_translation_id,
                reason=None,
                metadata_json=None,
                created_at=now,
            )
        )
        self._session.flush()
        self._invalidate_cache(segment_id)

        updated = self._session.get(DocumentSegment, segment_id)
        if updated is None:
            raise SegmentNotFoundError("The segment was not found after locking.")
        return updated

    def unlock(self, segment_id: str, command: UnlockSegment) -> DocumentSegment:
        reason = command.reason.strip()
        if not reason:
            raise EmptyUnlockReasonError("A reason is required to unlock a segment.")

        row = self._session.get(DocumentSegment, segment_id)
        if row is None:
            raise SegmentNotFoundError("The segment was not found.")
        if not row.is_locked:
            raise SegmentLockStateError("The segment is not locked.")
        if row.current_revision != command.expected_revision:
            raise SegmentRevisionConflictError(
                command.expected_revision,
                row.current_revision,
            )

        current_text = self._current_text(row)
        now = _utc_now()
        revision_number = command.expected_revision + 1
        source_translation_id = self._latest_translation_id(segment_id)
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(DocumentSegment)
                .where(
                    DocumentSegment.id == segment_id,
                    DocumentSegment.current_revision == command.expected_revision,
                    DocumentSegment.is_locked == 1,
                )
                .values(
                    status=SegmentStatus.APPROVED.value,
                    is_locked=0,
                    current_revision=revision_number,
                    updated_at=now,
                )
            ),
        )
        if result.rowcount != 1:
            self._raise_lock_race_error(segment_id, command.expected_revision)

        self._session.add(
            SegmentRevision(
                id=f"rev_{uuid4()}",
                segment_id=segment_id,
                revision_number=revision_number,
                revision_type=SegmentRevisionType.UNLOCK.value,
                previous_text=current_text,
                new_text=current_text,
                source_translation_id=source_translation_id,
                reason=reason,
                metadata_json=None,
                created_at=now,
            )
        )
        self._session.flush()
        self._invalidate_cache(segment_id)

        updated = self._session.get(DocumentSegment, segment_id)
        if updated is None:
            raise SegmentNotFoundError("The segment was not found after unlocking.")
        return updated

    def _current_text(self, row: DocumentSegment) -> str:
        for value in (row.final_text, row.reviewed_translation, row.machine_translation):
            if value and value.strip():
                return value
        raise SegmentLockStateError("A translated value is required before locking.")

    def _raise_lock_race_error(self, segment_id: str, expected_revision: int) -> None:
        current = self._session.get(DocumentSegment, segment_id)
        if current is None:
            raise SegmentNotFoundError("The segment was not found.")
        if current.current_revision != expected_revision:
            raise SegmentRevisionConflictError(expected_revision, current.current_revision)
        if current.is_locked:
            raise SegmentLockStateError("The segment is already locked.")
        raise SegmentLockStateError("The segment lock state changed before the update.")

    def _latest_translation_id(self, segment_id: str) -> str | None:
        return self._session.scalar(
            select(SegmentTranslation.id)
            .where(SegmentTranslation.segment_id == segment_id)
            .order_by(SegmentTranslation.created_at.desc(), SegmentTranslation.id.desc())
            .limit(1)
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
