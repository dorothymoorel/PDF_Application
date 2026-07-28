from unittest.mock import create_autospec
from uuid import UUID

import pytest
from transloka_api.services.projects import (
    CreateProject,
    ProjectService,
    UpdateProject,
    generate_project_id,
)
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
    validate_progress,
    validate_project_id,
)


def _record(**overrides: object) -> ProjectRecord:
    values: dict[str, object] = {
        "id": "prj_550e8400-e29b-41d4-a716-446655440000",
        "name": "System Design Book",
        "description": None,
        "status": ProjectStatus.CREATED,
        "source_language": "en",
        "target_language": "id",
        "document_type": DocumentType.TECHNICAL_BOOK,
        "translation_style": TranslationStyle.PROFESSIONAL,
        "reconstruction_mode": ReconstructionMode.HYBRID,
        "progress": 0.0,
        "active_document_id": None,
        "settings": {},
        "created_at": "2026-07-28T00:00:00.000Z",
        "updated_at": "2026-07-28T00:00:00.000Z",
        "archived_at": None,
        "deleted_at": None,
    }
    values.update(overrides)
    return ProjectRecord(**values)  # type: ignore[arg-type]


def test_project_id_is_canonical_prefixed_uuid() -> None:
    first = generate_project_id()
    second = generate_project_id()

    validate_project_id(first)
    assert first.startswith("prj_")
    assert str(UUID(first[4:])) == first[4:]
    assert first != second


@pytest.mark.parametrize(
    "value",
    [
        "",
        "prj_123",
        "doc_550e8400-e29b-41d4-a716-446655440000",
        "PRJ_550e8400-e29b-41d4-a716-446655440000",
        "prj_550E8400-E29B-41D4-A716-446655440000",
    ],
)
def test_invalid_project_ids_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        validate_project_id(value)


@pytest.mark.parametrize("value", [-1, 1.01, float("nan"), float("inf"), True])
def test_invalid_progress_is_rejected(value: float) -> None:
    with pytest.raises(InvalidProjectValueError):
        validate_progress(value)


def test_canonical_enums_are_closed() -> None:
    assert {member.value for member in TranslationStyle} == {
        "LITERAL",
        "PROFESSIONAL",
        "ACADEMIC",
        "NATURAL",
    }
    assert {member.value for member in ReconstructionMode} == {
        "OVERLAY",
        "REFLOW",
        "HYBRID",
    }
    assert ProjectStatus("ARCHIVED") is ProjectStatus.ARCHIVED
    with pytest.raises(ValueError):
        ProjectStatus("CUSTOM")


def test_service_create_delegates_canonical_defaults() -> None:
    repository = create_autospec(ProjectsRepository, instance=True)
    expected = _record()
    repository.create.return_value = expected
    service = ProjectService(repository)

    result = service.create(
        CreateProject(
            name="System Design Book",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
        )
    )

    assert result is expected
    arguments = repository.create.call_args.kwargs
    validate_project_id(arguments["project_id"])
    assert arguments["name"] == "System Design Book"
    assert arguments["document_type"] is DocumentType.TECHNICAL_BOOK
    assert arguments["translation_style"] is TranslationStyle.PROFESSIONAL
    assert arguments["reconstruction_mode"] is ReconstructionMode.HYBRID
    assert arguments["created_at"].endswith("Z")


def test_service_partial_update_preserves_unspecified_fields() -> None:
    repository = create_autospec(ProjectsRepository, instance=True)
    current = _record()
    updated = _record(name="Updated", progress=0.5)
    repository.get.return_value = current
    repository.update.return_value = updated
    service = ProjectService(repository)

    result = service.update(
        current.id,
        UpdateProject(name="Updated", progress=0.5),
    )

    assert result is updated
    repository.update.assert_called_once()
    arguments = repository.update.call_args.kwargs
    assert arguments["name"] == "Updated"
    assert arguments["status"] is ProjectStatus.CREATED
    assert arguments["translation_style"] is TranslationStyle.PROFESSIONAL
    assert arguments["reconstruction_mode"] is ReconstructionMode.HYBRID
    assert arguments["progress"] == 0.5


def test_service_rejects_empty_update() -> None:
    repository = create_autospec(ProjectsRepository, instance=True)

    with pytest.raises(InvalidProjectValueError):
        ProjectService(repository).update(
            "prj_550e8400-e29b-41d4-a716-446655440000",
            UpdateProject(),
        )

    repository.get.assert_not_called()


def test_service_archive_delegates_without_hard_delete() -> None:
    repository = create_autospec(ProjectsRepository, instance=True)
    archived = _record(
        status=ProjectStatus.ARCHIVED,
        archived_at="2026-07-28T01:00:00.000Z",
    )
    repository.archive.return_value = archived
    service = ProjectService(repository)

    assert service.archive(archived.id) is archived
    assert not hasattr(service, "delete")
    arguments = repository.archive.call_args.args
    assert arguments[0] == archived.id
    assert arguments[1].endswith("Z")


def test_service_unarchive_delegates() -> None:
    repository = create_autospec(ProjectsRepository, instance=True)
    restored = _record(status=ProjectStatus.CREATED)
    repository.unarchive.return_value = restored
    service = ProjectService(repository)

    assert service.unarchive(restored.id) is restored
    arguments = repository.unarchive.call_args.args
    assert arguments[0] == restored.id
    assert arguments[1].endswith("Z")
