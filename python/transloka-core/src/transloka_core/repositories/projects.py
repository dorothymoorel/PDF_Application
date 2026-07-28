import json
import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ProjectStatus,
    ReconstructionMode,
    TranslationStyle,
)


class ProjectRepositoryError(ValueError):
    pass


class InvalidProjectIdError(ProjectRepositoryError):
    pass


class InvalidProjectValueError(ProjectRepositoryError):
    pass


class ProjectAlreadyExistsError(ProjectRepositoryError):
    pass


class ProjectNotFoundError(ProjectRepositoryError):
    pass


class InvalidProjectStateError(ProjectRepositoryError):
    pass


class CorruptProjectError(ProjectRepositoryError):
    pass


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    name: str
    description: str | None
    status: ProjectStatus
    source_language: str
    target_language: str
    document_type: DocumentType
    translation_style: TranslationStyle
    reconstruction_mode: ReconstructionMode
    progress: float
    active_document_id: str | None
    settings: dict[str, object]
    created_at: str
    updated_at: str
    archived_at: str | None
    deleted_at: str | None


class ProjectsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        project_id: str,
        name: str,
        description: str | None,
        source_language: str,
        target_language: str,
        document_type: DocumentType,
        translation_style: TranslationStyle,
        reconstruction_mode: ReconstructionMode,
        created_at: str,
    ) -> ProjectRecord:
        validate_project_id(project_id)
        _validate_text(name, "Project name")
        _validate_optional_text(description, "Project description")
        _validate_text(source_language, "Source language")
        _validate_text(target_language, "Target language")
        _validate_enum(document_type, DocumentType)
        _validate_enum(translation_style, TranslationStyle)
        _validate_enum(reconstruction_mode, ReconstructionMode)
        if self._session.get(Project, project_id) is not None:
            raise ProjectAlreadyExistsError("The project already exists.")

        row = Project(
            id=project_id,
            name=name,
            description=description,
            status=ProjectStatus.CREATED.value,
            source_language=source_language,
            target_language=target_language,
            document_type=document_type.value,
            translation_style=translation_style.value,
            reconstruction_mode=reconstruction_mode.value,
            progress=0.0,
            active_document_id=None,
            settings_json="{}",
            created_at=created_at,
            updated_at=created_at,
            archived_at=None,
            deleted_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, project_id: str) -> ProjectRecord:
        row = self._active_row(project_id)
        return _record(row)

    def list(self, status: ProjectStatus | None = None) -> list[ProjectRecord]:
        if status is not None:
            _validate_enum(status, ProjectStatus)
        statement = (
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc(), Project.id)
        )
        if status is not None:
            statement = statement.where(Project.status == status.value)
        return [_record(row) for row in self._session.scalars(statement)]

    def update(
        self,
        project_id: str,
        *,
        name: str,
        description: str | None,
        status: ProjectStatus,
        translation_style: TranslationStyle,
        reconstruction_mode: ReconstructionMode,
        progress: float,
        updated_at: str,
    ) -> ProjectRecord:
        _validate_text(name, "Project name")
        _validate_optional_text(description, "Project description")
        _validate_enum(status, ProjectStatus)
        _validate_enum(translation_style, TranslationStyle)
        _validate_enum(reconstruction_mode, ReconstructionMode)
        validate_progress(progress)
        row = self._active_row(project_id)
        if row.status == ProjectStatus.ARCHIVED.value:
            raise InvalidProjectStateError("An archived project cannot be updated.")

        row.name = name
        row.description = description
        row.status = status.value
        row.translation_style = translation_style.value
        row.reconstruction_mode = reconstruction_mode.value
        row.progress = progress
        row.updated_at = updated_at
        self._session.flush()
        return _record(row)

    def archive(self, project_id: str, archived_at: str) -> ProjectRecord:
        row = self._active_row(project_id)
        if row.status in {
            ProjectStatus.ARCHIVED.value,
            ProjectStatus.DELETION_QUEUED.value,
        }:
            raise InvalidProjectStateError("The project cannot be archived in its current state.")

        row.status = ProjectStatus.ARCHIVED.value
        row.archived_at = archived_at
        row.updated_at = archived_at
        self._session.flush()
        return _record(row)

    def unarchive(self, project_id: str, updated_at: str) -> ProjectRecord:
        row = self._active_row(project_id)
        if row.status != ProjectStatus.ARCHIVED.value or row.archived_at is None:
            raise InvalidProjectStateError("The project is not archived.")

        row.status = ProjectStatus.CREATED.value
        row.archived_at = None
        row.updated_at = updated_at
        self._session.flush()
        return _record(row)

    def _active_row(self, project_id: str) -> Project:
        validate_project_id(project_id)
        row = self._session.get(Project, project_id)
        if row is None or row.deleted_at is not None:
            raise ProjectNotFoundError("The project was not found.")
        return row


def validate_project_id(value: str) -> None:
    if not isinstance(value, str) or not value.startswith("prj_"):
        raise InvalidProjectIdError("The project identifier is invalid.")
    try:
        parsed = UUID(value[4:])
    except (ValueError, AttributeError):
        raise InvalidProjectIdError("The project identifier is invalid.") from None
    if value != f"prj_{parsed}":
        raise InvalidProjectIdError("The project identifier is invalid.")


def validate_progress(value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise InvalidProjectValueError("Project progress must be between 0 and 1.")


def _validate_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise InvalidProjectValueError(f"{label} is invalid.")


def _validate_optional_text(value: str | None, label: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.isprintable()):
        raise InvalidProjectValueError(f"{label} is invalid.")


def _validate_enum(
    value: object,
    enum_type: type[ProjectStatus | DocumentType | TranslationStyle | ReconstructionMode],
) -> None:
    if not isinstance(value, enum_type):
        raise InvalidProjectValueError("The project enum value is invalid.")


def _record(row: Project) -> ProjectRecord:
    try:
        settings = json.loads(row.settings_json)
        if not isinstance(settings, dict) or not all(isinstance(key, str) for key in settings):
            raise ValueError
        return ProjectRecord(
            id=row.id,
            name=row.name,
            description=row.description,
            status=ProjectStatus(row.status),
            source_language=row.source_language,
            target_language=row.target_language,
            document_type=DocumentType(row.document_type),
            translation_style=TranslationStyle(row.translation_style),
            reconstruction_mode=ReconstructionMode(row.reconstruction_mode),
            progress=row.progress,
            active_document_id=row.active_document_id,
            settings=settings,
            created_at=row.created_at,
            updated_at=row.updated_at,
            archived_at=row.archived_at,
            deleted_at=row.deleted_at,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        raise CorruptProjectError("The stored project is invalid.") from None
