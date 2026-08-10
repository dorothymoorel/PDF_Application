import hashlib
import json
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.documents import (
    Document as DatabaseDocument,
)
from transloka_core.database.models.documents import (
    DocumentClass,
)
from transloka_core.database.models.documents import (
    DocumentStatus as DatabaseDocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.projects import (
    DocumentType as DatabaseDocumentType,
)
from transloka_core.database.models.projects import (
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_document_ir import Document, DocumentStatus, DocumentType
from transloka_document_ir.snapshots import (
    IRSnapshotIntegrityError,
    IRSnapshotVersionConflictError,
    canonical_document_json,
    create_ir_snapshot,
    load_ir_snapshot,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
DOCUMENT_ID = "doc_550e8400-e29b-41d4-a716-446655440000"
ORIGINAL_FILE_ID = "fil_550e8400-e29b-41d4-a716-446655440000"
CREATED_AT = datetime(2026, 7, 29, tzinfo=UTC)
CREATED_AT_TEXT = "2026-07-29T00:00:00.000Z"


@dataclass(frozen=True, slots=True)
class SnapshotContext:
    root: Path
    engine: Engine
    factory: sessionmaker[Session]
    storage: LocalFileStorage
    document: Document


@pytest.fixture
def snapshot_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[SnapshotContext]:
    root = tmp_path / "IR Snapshot Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="IR Snapshot Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DatabaseDocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT_TEXT,
        )
        StoredFilesRepository(session).create(
            file_id=ORIGINAL_FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL,
            storage_key=f"projects/{PROJECT_ID}/original/{ORIGINAL_FILE_ID}.pdf",
            original_filename="source.pdf",
            safe_filename="source.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata=None,
            created_at=CREATED_AT_TEXT,
        )
        session.add(
            DatabaseDocument(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Snapshot Document",
                author=None,
                document_type=DatabaseDocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=0,
                word_count_estimate=0,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DatabaseDocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT_TEXT,
                updated_at=CREATED_AT_TEXT,
            )
        )
    document = Document(
        ir_version="0.1",
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        source_file_id=ORIGINAL_FILE_ID,
        source_language="en",
        target_language="id",
        document_type=DocumentType.TECHNICAL_BOOK,
        page_count=0,
        status=DocumentStatus.STRUCTURED,
        revision=1,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        title="Snapshot Document",
        metadata={"source": "native", "unicode": "日本語"},
    )
    context = SnapshotContext(
        root=root,
        engine=engine,
        factory=factory,
        storage=LocalFileStorage(directories),
        document=document,
    )
    try:
        yield context
    finally:
        engine.dispose()
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_creates_immutable_snapshot_and_file_record(snapshot_context: SnapshotContext) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        record = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )

    stored_path = context.root / Path(record.storage_key)
    assert record.file_role is FileRole.IR_SNAPSHOT
    assert record.status is FileStatus.AVAILABLE
    assert record.document_id == DOCUMENT_ID
    assert record.is_immutable is True
    assert record.metadata == {
        "document_id": DOCUMENT_ID,
        "ir_version": "0.1",
        "revision": 1,
    }
    assert stored_path.is_file()
    assert not stored_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def test_snapshot_checksum_uses_canonical_json(snapshot_context: SnapshotContext) -> None:
    context = snapshot_context
    expected = canonical_document_json(context.document)
    with transaction_scope(context.factory) as session:
        record = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )

    assert record.checksum_sha256 == hashlib.sha256(expected).hexdigest()
    assert context.storage.checksum(record.storage_key) == record.checksum_sha256
    with context.storage.open_read(record.storage_key) as stored:
        content = stored.read()
    assert content == expected
    assert (
        json.dumps(
            json.loads(content),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        == content
    )


def test_repeated_version_preserves_old_revision_and_rejects_revision_conflict(
    snapshot_context: SnapshotContext,
) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        first = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )
    with transaction_scope(context.factory) as session:
        repeated = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )
    original_bytes = (context.root / Path(first.storage_key)).read_bytes()
    second_document = context.document.model_copy(
        update={"revision": 2, "title": "Second revision"}
    )
    with transaction_scope(context.factory) as session:
        second = create_ir_snapshot(
            second_document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )
    conflicting_second = second_document.model_copy(update={"title": "Different content"})
    with (
        pytest.raises(IRSnapshotVersionConflictError),
        transaction_scope(context.factory) as session,
    ):
        create_ir_snapshot(
            conflicting_second,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )
    with context.factory() as session:
        snapshot_count = session.scalar(
            select(func.count())
            .select_from(StoredFile)
            .where(StoredFile.file_role == FileRole.IR_SNAPSHOT.value)
        )

    assert repeated == first
    assert second.id != first.id
    assert second.storage_key != first.storage_key
    assert second.metadata is not None and second.metadata["ir_version"] == "0.1"
    assert second.metadata["revision"] == 2
    assert snapshot_count == 2
    assert (context.root / Path(first.storage_key)).read_bytes() == original_bytes


def test_snapshot_round_trip_restores_document(snapshot_context: SnapshotContext) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        record = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )

    restored = load_ir_snapshot(record, storage=context.storage)

    assert restored == context.document
    assert restored.revision == 1
    assert restored.ir_version == "0.1"


def test_tampered_snapshot_is_rejected(snapshot_context: SnapshotContext) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        record = create_ir_snapshot(
            context.document,
            storage=context.storage,
            repository=StoredFilesRepository(session),
            created_at=CREATED_AT,
        )
    stored_path = context.root / Path(record.storage_key)
    stored_path.chmod(stat.S_IREAD | stat.S_IWRITE)
    stored_path.write_bytes(b'{"tampered":true}')

    with pytest.raises(IRSnapshotIntegrityError, match="checksum"):
        load_ir_snapshot(record, storage=context.storage)
