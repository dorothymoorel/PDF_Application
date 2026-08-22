from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.backup.archive import create_full_project_backup
from transloka_core.backup.restore import RestoreWorkflow
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.exports import Export, ExportProfile, ExportStatus, ExportType
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.glossary import (
    GlossaryMatchMode,
    GlossaryRevision,
    GlossaryRuleType,
    GlossaryScope,
    GlossaryTerm,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType
from transloka_core.database.models.translation import SegmentTranslation  # noqa: F401
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage, StoredFileArtifact
from transloka_glossary import GlossaryRepository
from transloka_glossary.snapshots import create_glossary_snapshot

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-23T00:00:00.000Z"
CREATED_AT_DATETIME = datetime(2026, 8, 23, tzinfo=UTC)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1301)
DOCUMENT_ID = _id("doc_", 1302)
ORIGINAL_FILE_ID = _id("fil_", 1303)
EXPORT_FILE_ID = _id("fil_", 1304)
EXPORT_ID = _id("exp_", 1305)
PAGE_ID = _id("pag_", 1306)
BLOCK_ID = _id("blk_", 1307)
SEGMENT_ID = _id("seg_", 1308)
REVISION_ID = _id("rev_", 1309)
GLOSSARY_ID = _id("gls_", 1310)
TERM_ID = _id("trm_", 1311)
TERM_REVISION_ID = _id("grv_", 1312)

ORIGINAL_BYTES = b"%PDF-1.7\noriginal project document\n"
EXPORT_BYTES = b"%PDF-1.7\ntranslated export document\n"


@dataclass(frozen=True, slots=True)
class BackupRestoreContext:
    directories: LocalDataDirectories
    engine: Engine
    factory: sessionmaker[Session]
    storage: LocalFileStorage
    backup_path: Path
    backup_checksum: str
    original_storage_key: str
    export_storage_key: str


@pytest.fixture
def backup_restore_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[BackupRestoreContext]:
    root = tmp_path / "backup restore e2e"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(directories)
    original_storage_key = f"projects/{PROJECT_ID}/original/{ORIGINAL_FILE_ID}.pdf"
    export_storage_key = f"projects/{PROJECT_ID}/exports/{EXPORT_FILE_ID}.pdf"

    original_artifact = _commit_file(storage, original_storage_key, ORIGINAL_BYTES)
    export_artifact = _commit_file(storage, export_storage_key, EXPORT_BYTES)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Backup restore project",
            description="Complete project state for backup recovery.",
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )
        files = StoredFilesRepository(session)
        files.create(
            file_id=ORIGINAL_FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL,
            storage_key=original_artifact.storage_key,
            original_filename="source.pdf",
            safe_filename="source.pdf",
            mime_type="application/pdf",
            size_bytes=original_artifact.size_bytes,
            checksum_sha256=original_artifact.checksum_sha256,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata=None,
            created_at=CREATED_AT,
        )
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Backup restore source",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=4,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.REVIEWED.value,
                metadata_json=None,
                analysis_json=json.dumps({"page_count": 1}),
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=612.0,
                height_points=792.0,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=1.0,
                ocr_confidence=None,
                structure_confidence=0.95,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentBlock(
                id=BLOCK_ID,
                page_id=PAGE_ID,
                section_id=None,
                parent_block_id=None,
                block_type=BlockType.PARAGRAPH.value,
                semantic_role=SemanticRole.BODY_TEXT.value,
                page_reading_order=1,
                global_reading_order=1,
                source_text="Source workflow term.",
                normalized_source_text="Source workflow term.",
                source_geometry_json=json.dumps(
                    {
                        "coordinate_system": "PDF_POINT_TOP_LEFT",
                        "x": 72.0,
                        "y": 72.0,
                        "width": 160.0,
                        "height": 14.0,
                    }
                ),
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.READY_FOR_TRANSLATION.value,
                confidence=0.99,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentSegment(
                id=SEGMENT_ID,
                block_id=BLOCK_ID,
                section_id=None,
                segment_order=1,
                global_order=1,
                source_text="Source workflow term.",
                native_text=None,
                ocr_text=None,
                resolved_source_text="Source workflow term.",
                normalized_source_text="Source workflow term.",
                protected_source_text=None,
                machine_translation="Terjemahan istilah alur kerja.",
                reviewed_translation="Terjemahan istilah alur kerja.",
                final_text="Terjemahan istilah alur kerja.",
                source_language="en",
                target_language="id",
                status=SegmentStatus.APPROVED.value,
                review_status=ReviewStatus.APPROVED.value,
                is_locked=0,
                current_revision=1,
                confidence_overall=0.98,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            SegmentRevision(
                id=REVISION_ID,
                segment_id=SEGMENT_ID,
                revision_number=1,
                revision_type=SegmentRevisionType.USER_EDIT.value,
                previous_text=None,
                new_text="Terjemahan istilah alur kerja.",
                source_translation_id=None,
                reason="Approved translated text.",
                metadata_json=None,
                created_at=CREATED_AT,
            )
        )
        repository = GlossaryRepository(session)
        repository.create_glossary(
            glossary_id=GLOSSARY_ID,
            project_id=PROJECT_ID,
            name="Backup restore glossary",
            description=None,
            source_language="en",
            target_language="id",
            scope=GlossaryScope.PROJECT,
            domain=None,
            is_default=True,
            created_at=CREATED_AT,
        )
        repository.create_term(
            term_id=TERM_ID,
            revision_id=TERM_REVISION_ID,
            glossary_id=GLOSSARY_ID,
            source_term="workflow",
            rule_type=GlossaryRuleType.TRANSLATE_AS,
            target_term="alur kerja",
            scope=GlossaryScope.PROJECT,
            scope_reference_id=PROJECT_ID,
            priority=100,
            case_sensitive=False,
            whole_word=True,
            match_mode=GlossaryMatchMode.PHRASE,
            capitalization_policy="PRESERVE_SOURCE_CASE",
            inflection_policy="USE_BASE_TERM",
            first_use_policy="NONE",
            confidence=1.0,
            notes=None,
            created_at=CREATED_AT,
        )
        create_glossary_snapshot(
            session=session,
            storage=storage,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_at=CREATED_AT_DATETIME,
        )
        files.create(
            file_id=EXPORT_FILE_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            file_role=FileRole.EXPORT,
            storage_key=export_artifact.storage_key,
            original_filename="translated.pdf",
            safe_filename="translated.pdf",
            mime_type="application/pdf",
            size_bytes=export_artifact.size_bytes,
            checksum_sha256=export_artifact.checksum_sha256,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata={"workflow": "backup-restore-e2e"},
            created_at=CREATED_AT,
        )
        session.add(
            Export(
                id=EXPORT_ID,
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                reconstruction_job_id=None,
                file_id=EXPORT_FILE_ID,
                export_type=ExportType.TRANSLATED_PDF.value,
                output_profile=ExportProfile.STANDARD.value,
                version_number=1,
                status=ExportStatus.COMPLETED.value,
                page_count=1,
                size_bytes=export_artifact.size_bytes,
                checksum_sha256=export_artifact.checksum_sha256,
                validation_report_id="val_backup_restore",
                settings_json="{}",
                created_at=CREATED_AT,
                completed_at=CREATED_AT,
                error_code=None,
            )
        )
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.active_document_id = DOCUMENT_ID

    backup = create_full_project_backup(directories)
    backup_path = directories.root / Path(backup.storage_key)
    yield BackupRestoreContext(
        directories=directories,
        engine=engine,
        factory=factory,
        storage=storage,
        backup_path=backup_path,
        backup_checksum=backup.checksum_sha256,
        original_storage_key=original_storage_key,
        export_storage_key=export_storage_key,
    )
    engine.dispose()


def test_complete_project_backup_restores_state_and_checksums(
    backup_restore_context: BackupRestoreContext,
) -> None:
    context = backup_restore_context
    with context.factory() as session:
        project = session.get(Project, PROJECT_ID)
        revision = session.get(SegmentRevision, REVISION_ID)
        term = session.get(GlossaryTerm, TERM_ID)
        export = session.get(Export, EXPORT_ID)
        assert project is not None
        assert revision is not None
        assert term is not None
        assert export is not None
        expected_state = (
            project.name,
            project.status,
            revision.new_text,
            term.source_term,
            term.target_term,
            export.checksum_sha256,
        )

    original_checksum = _sha256(context.directories.root / context.original_storage_key)
    export_checksum = _sha256(context.directories.root / context.export_storage_key)
    assert original_checksum == _sha256_bytes(ORIGINAL_BYTES)
    assert export_checksum == _sha256_bytes(EXPORT_BYTES)

    with transaction_scope(context.factory) as session:
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.name = "Mutated project"
        project.status = "FAILED"
        session.delete(session.get(SegmentRevision, REVISION_ID))
        session.delete(session.get(GlossaryTerm, TERM_ID))
        session.delete(session.get(Export, EXPORT_ID))
    _force_remove(context.directories.root / context.original_storage_key)
    _force_remove(context.directories.root / context.export_storage_key)

    with context.factory() as session:
        assert session.get(SegmentRevision, REVISION_ID) is None
        assert session.get(GlossaryTerm, TERM_ID) is None
        assert session.get(Export, EXPORT_ID) is None
        mutated_project = session.get(Project, PROJECT_ID)
        assert mutated_project is not None
        assert mutated_project.name == "Mutated project"

    context.engine.dispose()
    result = RestoreWorkflow(context.directories).restore(
        context.backup_path,
        confirmation="RESTORE",
    )
    assert result.backup_type.value == "FULL_PROJECTS"
    assert result.restored_content
    assert result.pre_restore_backup.storage_key.startswith("backups/")
    assert _sha256(context.backup_path) == context.backup_checksum

    restored_engine = create_sqlite_engine(context.directories)
    restored_factory = create_session_factory(restored_engine)
    try:
        with restored_factory() as session:
            project = session.get(Project, PROJECT_ID)
            revision = session.get(SegmentRevision, REVISION_ID)
            term = session.get(GlossaryTerm, TERM_ID)
            glossary_revision = session.get(GlossaryRevision, TERM_REVISION_ID)
            export = session.get(Export, EXPORT_ID)
            assert project is not None
            assert revision is not None
            assert term is not None
            assert glossary_revision is not None
            assert export is not None
            assert (
                project.name,
                project.status,
                revision.new_text,
                term.source_term,
                term.target_term,
                export.checksum_sha256,
            ) == expected_state
            assert export.status == ExportStatus.COMPLETED.value

        assert _sha256(context.directories.root / context.original_storage_key) == original_checksum
        assert _sha256(context.directories.root / context.export_storage_key) == export_checksum
        assert (
            context.directories.root / context.original_storage_key
        ).read_bytes() == ORIGINAL_BYTES
        assert (context.directories.root / context.export_storage_key).read_bytes() == EXPORT_BYTES
    finally:
        restored_engine.dispose()


def _commit_file(
    storage: LocalFileStorage,
    storage_key: str,
    content: bytes,
) -> StoredFileArtifact:
    temporary = storage.write_temporary(BytesIO(content))
    return storage.commit(temporary, storage_key, immutable=True)


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _force_remove(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IWRITE)
    path.unlink()
