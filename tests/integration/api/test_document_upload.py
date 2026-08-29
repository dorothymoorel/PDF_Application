import hashlib
import sqlite3
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
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
from transloka_core.database.models.documents import DocumentStatus
from transloka_core.database.models.jobs import JobStatus, JobType
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


def test_valid_upload_is_validated_and_committed_as_immutable_original(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    content = _pdf_bytes()

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers(),
        files={"file": ("system-design.pdf", content, "application/pdf")},
        data={"set_as_active": "true"},
    )

    assert response.status_code == 202
    payload = response.json()["data"]
    document = payload["document"]
    job = payload["job"]
    assert document == {
        "id": document["id"],
        "project_id": project_id,
        "original_file_id": document["original_file_id"],
        "status": DocumentStatus.CREATED.value,
        "original_filename": "system-design.pdf",
        "size_bytes": len(content),
        "checksum_sha256": hashlib.sha256(content).hexdigest(),
        "page_count": 1,
        "title": None,
    }
    assert job == {
        "id": job["id"],
        "job_type": JobType.ANALYZE_DOCUMENT.value,
        "status": JobStatus.QUEUED.value,
    }
    assert document["id"].startswith("doc_")
    assert job["id"].startswith("job_")
    original_file_id = document["original_file_id"]
    assert original_file_id.startswith("fil_")
    assert list((root / "temp").iterdir()) == []
    originals = list((root / "projects" / project_id / "original").glob("*.pdf"))
    assert len(originals) == 1
    assert originals[0].read_bytes() == content
    with sqlite3.connect(root / "database" / "transloka.db") as connection:
        stored = connection.execute(
            "SELECT id, file_role, checksum_sha256, is_immutable, status "
            "FROM stored_files WHERE id = ?",
            (original_file_id,),
        ).fetchone()
        persisted_document = connection.execute(
            "SELECT id, project_id, original_file_id, status, page_count "
            "FROM documents WHERE id = ?",
            (document["id"],),
        ).fetchone()
        persisted_job = connection.execute(
            "SELECT id, project_id, document_id, job_type, status "
            "FROM application_jobs WHERE id = ?",
            (job["id"],),
        ).fetchone()
        project = connection.execute(
            "SELECT active_document_id, status FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    assert stored == (
        original_file_id,
        "ORIGINAL",
        hashlib.sha256(content).hexdigest(),
        1,
        "VALIDATED",
    )
    assert persisted_document == (
        document["id"],
        project_id,
        original_file_id,
        DocumentStatus.CREATED.value,
        1,
    )
    assert persisted_job == (
        job["id"],
        project_id,
        document["id"],
        JobType.ANALYZE_DOCUMENT.value,
        JobStatus.QUEUED.value,
    )
    assert project == (document["id"], "ANALYZING")
    assert str(root) not in response.text


def test_document_detail_returns_persisted_safe_metadata(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    content = _pdf_bytes()
    imported = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("document-detail"),
        files={"file": ("system-design.pdf", content, "application/pdf")},
    ).json()["data"]["document"]

    response = client.get(f"/api/v1/documents/{imported['id']}")

    assert response.status_code == 200
    assert response.json()["data"] == imported
    assert "storage_key" not in response.text
    assert str(root) not in response.text


def test_document_detail_returns_normalized_not_found(
    document_api: tuple[TestClient, Path],
) -> None:
    client, _root = document_api

    response = client.get("/api/v1/documents/doc_00000000-0000-4000-8000-000000000099")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_document_detail_hides_orphaned_file_metadata(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    imported = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("document-detail-orphan"),
        files={"file": ("system-design.pdf", _pdf_bytes(), "application/pdf")},
    ).json()["data"]["document"]
    with sqlite3.connect(root / "database" / "transloka.db") as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "DELETE FROM stored_files WHERE id = ?",
            (imported["original_file_id"],),
        )

    response = client.get(f"/api/v1/documents/{imported['id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_document_detail_reduces_path_like_filename_to_safe_metadata(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    imported = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("document-detail-path"),
        files={"file": ("system-design.pdf", _pdf_bytes(), "application/pdf")},
    ).json()["data"]["document"]
    unsafe_filename = "C:\\private\\source.pdf"
    with sqlite3.connect(root / "database" / "transloka.db") as connection:
        connection.execute(
            "UPDATE stored_files SET original_filename = ? WHERE id = ?",
            (unsafe_filename, imported["original_file_id"]),
        )

    response = client.get(f"/api/v1/documents/{imported['id']}")

    assert response.status_code == 200
    returned_filename = response.json()["data"]["original_filename"]
    assert returned_filename.endswith(".pdf")
    assert "/" not in returned_filename
    assert "\\" not in returned_filename
    assert unsafe_filename not in response.text


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
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["document"]["original_filename"] == filename


def test_arbitrary_path_filename_is_reduced_to_safe_metadata(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    filename = "C:\\private\\secret.pdf"

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("path-filename"),
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["data"]["document"]["original_filename"] == "secret.pdf"
    assert filename not in response.text
    assert list((root / "temp").glob("*")) == []


def test_invalid_pdf_is_rejected_before_original_storage(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("invalid-pdf"),
        files={"file": ("invalid.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PDF_MAGIC"
    assert list((root / "temp").iterdir()) == []
    assert list((root / "projects" / project_id / "original").glob("*.pdf")) == []


def test_idempotent_retry_returns_same_original_without_duplicate(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    content = _pdf_bytes()

    first = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("same-import"),
        files={"file": ("same.pdf", content, "application/pdf")},
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("same-import"),
        files={"file": ("same.pdf", content, "application/pdf")},
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]
    assert list((root / "temp").iterdir()) == []
    assert len(list((root / "projects" / project_id / "original").glob("*.pdf"))) == 1


def test_idempotency_key_cannot_replace_an_existing_original(
    document_api: tuple[TestClient, Path],
) -> None:
    client, root = document_api
    project_id = _create_project(client)
    original = _pdf_bytes()

    first = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("conflicting-import"),
        files={"file": ("source.pdf", original, "application/pdf")},
    )
    conflict = client.post(
        f"/api/v1/projects/{project_id}/documents/import",
        headers=_upload_headers("conflicting-import"),
        files={"file": ("source.pdf", _pdf_bytes(page_count=2), "application/pdf")},
    )

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IMPORT_CONFLICT"
    assert list((root / "temp").iterdir()) == []
    originals = list((root / "projects" / project_id / "original").glob("*.pdf"))
    assert len(originals) == 1
    assert originals[0].read_bytes() == original


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
    for status_code in ("400", "403", "404", "409", "413", "415", "422", "500", "503"):
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


def _pdf_bytes(*, page_count: int = 1) -> bytes:
    destination = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(destination)
    return destination.getvalue()
