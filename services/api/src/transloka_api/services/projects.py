from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from transloka_core.database.models.projects import (
    DocumentType,
    ProjectStatus,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.projects import (
    InvalidProjectValueError,
    ProjectRecord,
    ProjectsRepository,
)


@dataclass(frozen=True)
class CreateProject:
    name: str
    description: str | None
    source_language: str
    target_language: str
    document_type: DocumentType
    translation_style: TranslationStyle
    reconstruction_mode: ReconstructionMode


@dataclass(frozen=True)
class UpdateProject:
    name: str | None = None
    status: ProjectStatus | None = None
    translation_style: TranslationStyle | None = None
    reconstruction_mode: ReconstructionMode | None = None
    progress: float | None = None


class ProjectService:
    def __init__(self, repository: ProjectsRepository) -> None:
        self._repository = repository

    def create(self, command: CreateProject) -> ProjectRecord:
        now = _utc_now()
        return self._repository.create(
            project_id=generate_project_id(),
            name=command.name,
            description=command.description,
            source_language=command.source_language,
            target_language=command.target_language,
            document_type=command.document_type,
            translation_style=command.translation_style,
            reconstruction_mode=command.reconstruction_mode,
            created_at=now,
        )

    def get(self, project_id: str) -> ProjectRecord:
        return self._repository.get(project_id)

    def list(self, status: ProjectStatus | None = None) -> list[ProjectRecord]:
        return self._repository.list(status)

    def update(self, project_id: str, command: UpdateProject) -> ProjectRecord:
        if all(
            value is None
            for value in (
                command.name,
                command.status,
                command.translation_style,
                command.reconstruction_mode,
                command.progress,
            )
        ):
            raise InvalidProjectValueError("At least one project field must be updated.")

        current = self._repository.get(project_id)
        return self._repository.update(
            project_id,
            name=command.name if command.name is not None else current.name,
            description=current.description,
            status=command.status if command.status is not None else current.status,
            translation_style=(
                command.translation_style
                if command.translation_style is not None
                else current.translation_style
            ),
            reconstruction_mode=(
                command.reconstruction_mode
                if command.reconstruction_mode is not None
                else current.reconstruction_mode
            ),
            progress=command.progress if command.progress is not None else current.progress,
            updated_at=_utc_now(),
        )

    def archive(self, project_id: str) -> ProjectRecord:
        return self._repository.archive(project_id, _utc_now())

    def unarchive(self, project_id: str) -> ProjectRecord:
        return self._repository.unarchive(project_id, _utc_now())


def generate_project_id() -> str:
    return f"prj_{uuid4()}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
