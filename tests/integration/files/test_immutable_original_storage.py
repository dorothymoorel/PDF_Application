import hashlib
import io
import stat
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pypdf import PdfWriter
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.services.imports import (
    ImportService,
    OriginalImportConflictError,
    StagedUpload,
    ValidatedUploadMismatchError,
)
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import (
    ImmutableStoredFileError,
    LocalFileStorage,
    StoredFileExistsError,
)
from transloka_documents.validation import PdfValidationLimits, PdfValidationResult, validate_pdf

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
CREATED_AT = "2026-07-29T00:00:00.000Z"
IDEMPOTENCY_KEY = "import-original-1"
LIMITS = PdfValidationLimits(max_bytes=1024 * 1024, max_pages=10, max_objects=100)


@pytest.fixture
def original_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[
    tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ]
]:
    root = tmp_path / "immutable original"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Immutable Original Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )
    storage = LocalFileStorage(directories)
    try:
        yield root, engine, factory, storage, ImportService(storage, max_upload_bytes=1024 * 1024)
    finally:
        engine.dispose()
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_validated_pdf_is_stored_with_checksum_and_original_record(
    original_storage: tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ],
) -> None:
    root, _engine, factory, storage, service = original_storage
    content = _pdf_bytes()
    staged, validation = _stage_and_validate(service, content)

    with transaction_scope(factory) as session:
        record = service.store_original(staged, validation, StoredFilesRepository(session))

    stored_path = root / Path(record.storage_key)
    assert record.file_role is FileRole.ORIGINAL
    assert record.status is FileStatus.VALIDATED
    assert record.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert record.size_bytes == len(content)
    assert record.is_immutable is True
    assert record.storage_key == f"projects/{PROJECT_ID}/original/{record.id}.pdf"
    assert not stored_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    assert storage.checksum(record.storage_key) == record.checksum_sha256
    assert not staged.temporary.path.exists()


def test_only_the_validated_temporary_file_can_be_committed(
    original_storage: tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ],
) -> None:
    root, _engine, factory, _storage, service = original_storage
    staged, _validation = _stage_and_validate(service, _pdf_bytes())
    different_content = _pdf_bytes(page_count=2)
    different_validation = validate_pdf(
        BytesIO(different_content),
        filename="source.pdf",
        mime_type="application/pdf",
        limits=LIMITS,
    )

    with pytest.raises(ValidatedUploadMismatchError), transaction_scope(factory) as session:
        service.store_original(
            staged,
            different_validation,
            StoredFilesRepository(session),
        )

    assert not staged.temporary.path.exists()
    assert list((root / "projects" / PROJECT_ID / "original").glob("*.pdf")) == []


def test_retry_returns_same_original_without_duplicate(
    original_storage: tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ],
) -> None:
    root, _engine, factory, _storage, service = original_storage
    content = _pdf_bytes()
    first_staged, first_validation = _stage_and_validate(service, content)
    with transaction_scope(factory) as session:
        first = service.store_original(
            first_staged,
            first_validation,
            StoredFilesRepository(session),
        )

    retry_staged, retry_validation = _stage_and_validate(service, content)
    with transaction_scope(factory) as session:
        retry = service.store_original(
            retry_staged,
            retry_validation,
            StoredFilesRepository(session),
        )
        stored_count = session.scalar(select(func.count()).select_from(StoredFile))

    assert retry == first
    assert stored_count == 1
    assert list((root / "projects" / PROJECT_ID / "original").glob("*.pdf")) == [
        root / Path(first.storage_key)
    ]
    assert not retry_staged.temporary.path.exists()


def test_same_idempotency_key_cannot_overwrite_original(
    original_storage: tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ],
) -> None:
    _root, _engine, factory, storage, service = original_storage
    original_content = _pdf_bytes()
    staged, validation = _stage_and_validate(service, original_content)
    with transaction_scope(factory) as session:
        original = service.store_original(staged, validation, StoredFilesRepository(session))

    replacement, replacement_validation = _stage_and_validate(service, _pdf_bytes(page_count=2))
    with pytest.raises(OriginalImportConflictError), transaction_scope(factory) as session:
        service.store_original(
            replacement,
            replacement_validation,
            StoredFilesRepository(session),
        )

    assert storage.checksum(original.storage_key) == original.checksum_sha256
    assert not replacement.temporary.path.exists()


def test_original_cannot_be_mutated_or_used_as_output_target(
    original_storage: tuple[
        Path,
        Engine,
        sessionmaker[Session],
        LocalFileStorage,
        ImportService,
    ],
) -> None:
    _root, _engine, factory, storage, service = original_storage
    content = _pdf_bytes()
    staged, validation = _stage_and_validate(service, content)
    with transaction_scope(factory) as session:
        original = service.store_original(staged, validation, StoredFilesRepository(session))

    with storage.open_read(original.storage_key) as source, pytest.raises(io.UnsupportedOperation):
        source.write(b"mutation")
    with pytest.raises(ImmutableStoredFileError):
        storage.delete(original.storage_key)

    output = storage.write_temporary(BytesIO(_pdf_bytes(page_count=2)))
    with pytest.raises(StoredFileExistsError):
        storage.commit(output, original.storage_key)

    assert storage.checksum(original.storage_key) == original.checksum_sha256
    assert not output.path.exists()


def _stage_and_validate(
    service: ImportService,
    content: bytes,
) -> tuple[StagedUpload, PdfValidationResult]:
    staged = service.stage_upload(
        project_id=PROJECT_ID,
        original_filename="source.pdf",
        idempotency_key=IDEMPOTENCY_KEY,
        set_as_active=True,
        stream=BytesIO(content),
    )
    with staged.temporary.path.open("rb") as source:
        validation = validate_pdf(
            source,
            filename=staged.original_filename,
            mime_type="application/pdf",
            limits=LIMITS,
        )
    return staged, validation


def _pdf_bytes(*, page_count: int = 1) -> bytes:
    destination = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    writer.write(destination)
    return destination.getvalue()
