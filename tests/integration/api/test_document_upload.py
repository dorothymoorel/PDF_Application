from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.config import Settings
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_api.services.imports import (
    ImportService,
    UploadInterruptedError,
    UploadTooLargeError,
)
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Upload Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


@pytest.fixture
def document_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Path]]:
    root = tmp_path / "document api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    with TestClient(create_app()) as client:
        yield client, root


def _create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", headers=CLIENT_HEADERS, json=PROJECT)
    assert response.status_code == 201
    return cast(str, response.json()["data"]["id"])


def _upload_headers(key: str = "import-document-1") -> dict[str, str]:
    return {**CLIENT_HEADERS, "Idempotency-Key": key}


def test_valid_upload_is_streamed_to_controlled_temporary_storage(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    content = b"%PDF-1.7\nstaging only"

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers(),
        files={"file": ("system-design.pdf", content, "application/pdf")},
        data={"set_as_active": "true"},
    )

    assert response.status_code == 202
    assert response.json()["data"] == {
        "upload_id": response.json()["data"]["upload_id"],
        "project_id": project_id,
        "status": "STAGED",
        "original_filename": "system-design.pdf",
        "size_bytes": len(content),
        "set_as_active": True,
    }
    assert response.json()["data"]["upload_id"].startswith("upl_")
    temporary_files = list((root / "temp").iterdir())
    assert len(temporary_files) == 1
    assert temporary_files[0].read_bytes() == content
    assert str(root) not in response.text


def test_empty_upload_is_rejected_and_cleaned(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers(),
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_UPLOAD"
    assert list((root / "temp").iterdir()) == []


def test_unicode_filename_is_preserved(document_api: tuple[TestClient, Path]) -> None:
    client, _root = document_api
    project_id = _create_project(client)
    filename = "設計資料_日本語.pdf"

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("unicode-filename"),
        files={"file": (filename, b"not validated until M3-T04", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["original_filename"] == filename


def test_arbitrary_path_filename_is_reduced_to_safe_metadata(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    filename = "C:\\private\\secret.pdf"

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("path-filename"),
        files={"file": (filename, b"content", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["original_filename"] == "secret.pdf"
    assert filename not in response.text
    temporary_files = list((root / "temp").glob("*"))
    assert len(temporary_files) == 1
    assert temporary_files[0].read_bytes() == b"content"


def test_unexpected_content_type_is_rejected(document_api: tuple[TestClient, Path]) -> None:
    client, _root = document_api
    project_id = _create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("wrong-content-type"),
        json={"file": "not-an-upload"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_oversized_stream_stops_at_limit_and_cleans_temporary_file(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "oversized")
    stream = BytesIO(b"123456")
    service = ImportService(LocalFileStorage(directories), max_upload_bytes=4)

    with pytest.raises(UploadTooLargeError):
        service.stage_upload(
            project_id="prj_test",
            original_filename="large.pdf",
            idempotency_key="oversized",
            set_as_active=True,
            stream=stream,
        )

    assert stream.tell() == 5
    assert list(directories.temporary.iterdir()) == []


def test_oversized_api_upload_returns_413_and_cleans_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "oversized api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    with TestClient(create_app(Settings(max_upload_bytes=4))) as client:
        project_id = _create_project(client)
        response = client.post(
            f"/api/v1/projects/{project_id}/documents/import",
            headers=_upload_headers("oversized-api"),
            files={"file": ("large.pdf", b"12345", "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert list((root / "temp").iterdir()) == []


def test_interrupted_stream_cleans_partial_temporary_file(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "interrupted")
    service = ImportService(LocalFileStorage(directories), max_upload_bytes=100)

    with pytest.raises(UploadInterruptedError):
        service.stage_upload(
            project_id="prj_test",
            original_filename="interrupted.pdf",
            idempotency_key="interrupted",
            set_as_active=True,
            stream=_InterruptedStream(b"partial"),
        )

    assert list(directories.temporary.iterdir()) == []


def test_upload_openapi_contract_is_registered() -> None:
    operation = create_app().openapi()["paths"]["/api/v1/projects/{project_id}/documents/import"][
        "post"
    ]

    assert operation["operationId"] == "import_document"
    assert "multipart/form-data" in operation["requestBody"]["content"]
    for status_code in ("400", "403", "404", "413", "415", "422", "500"):
        schema = operation["responses"][status_code]["content"]["application/json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/ErrorResponse"


class _InterruptedStream(BytesIO):
    def __init__(self, initial_bytes: bytes) -> None:
        super().__init__(initial_bytes)
        self._reads = 0

    def read(self, size: int | None = -1) -> bytes:
        self._reads += 1
        if self._reads > 1:
            raise OSError("simulated interruption")
        return super().read(min(size if size is not None else -1, 3))
