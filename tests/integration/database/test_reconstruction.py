import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.document_ir import BlockType, DocumentBlock
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.database.models.reconstruction import (
    ReconstructionBlock,
    ReconstructionBlockStatus,
    ReconstructionJob,
    ReconstructionPage,
    ReconstructionStatus,
    ReconstructionStrategy,
    TargetPageMapping,
    TargetPageMappingType,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0013_warnings"
CREATED_AT = "2026-08-20T00:00:00.000Z"
PROJECT_ID = f"prj_{UUID(int=1)}"
ORIGINAL_FILE_ID = f"fil_{UUID(int=2)}"
DOCUMENT_ID = f"doc_{UUID(int=3)}"
PAGE_ID = f"pag_{UUID(int=4)}"
BLOCK_ID = f"blk_{UUID(int=5)}"
ORIGINAL_HASH = "a" * 64
PAGE_HASH = "b" * 64
SOURCE_GEOMETRY = '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72,"y":120}'
TARGET_GEOMETRY = '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72,"y":120}'


@pytest.fixture
def reconstruction_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Reconstruction Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    try:
        with transaction_scope(factory) as session:
            ProjectsRepository(session).create(
                project_id=PROJECT_ID,
                name="Reconstruction Project",
                description=None,
                source_language="en",
                target_language="id",
                document_type=DocumentType.TECHNICAL_BOOK,
                translation_style=TranslationStyle.PROFESSIONAL,
                reconstruction_mode=ReconstructionMode.HYBRID,
                created_at=CREATED_AT,
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
                checksum_sha256=ORIGINAL_HASH,
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
                    title="Reconstruction Document",
                    author=None,
                    document_type=DocumentType.TECHNICAL_BOOK.value,
                    document_class=DocumentClass.DIGITAL_PDF.value,
                    source_language="en",
                    target_language="id",
                    page_count=1,
                    word_count_estimate=10,
                    has_text_layer=1,
                    scanned_page_count=0,
                    image_count=0,
                    table_count=0,
                    status=DocumentStatus.REVIEWED.value,
                    metadata_json=None,
                    analysis_json=None,
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
                    page_classification="REFLOW_FRIENDLY",
                    column_count=1,
                    reading_direction="LTR",
                    status="READY_FOR_RECONSTRUCTION",
                    render_file_id=None,
                    thumbnail_file_id=None,
                    native_extraction_confidence=1.0,
                    ocr_confidence=None,
                    structure_confidence=1.0,
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
                    semantic_role=None,
                    page_reading_order=0,
                    global_reading_order=0,
                    source_text="Source paragraph.",
                    normalized_source_text="Source paragraph.",
                    source_geometry_json=SOURCE_GEOMETRY,
                    target_geometry_json=None,
                    style_json=None,
                    detail_json=None,
                    status=DocumentStatus.REVIEWED.value,
                    confidence=1.0,
                    created_at=CREATED_AT,
                    updated_at=CREATED_AT,
                )
            )
        yield root, engine, factory
    finally:
        engine.dispose()


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


def _job(index: int = 10, **overrides: object) -> ReconstructionJob:
    values: dict[str, object] = {
        "id": _id("rcj_", index),
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "application_job_id": None,
        "mode": ReconstructionMode.HYBRID.value,
        "settings_version": "0.1",
        "settings_json": '{"mode":"HYBRID","preserve_images":true}',
        "status": ReconstructionStatus.COMPLETED.value,
        "progress": 1.0,
        "reconstruction_hash": f"hash-{index}",
        "created_at": CREATED_AT,
        "started_at": CREATED_AT,
        "completed_at": CREATED_AT,
        "error_code": None,
    }
    values.update(overrides)
    return ReconstructionJob(**values)


def _page(job_id: str, index: int = 20, **overrides: object) -> ReconstructionPage:
    values: dict[str, object] = {
        "id": _id("rcp_", index),
        "reconstruction_job_id": job_id,
        "source_page_id": PAGE_ID,
        "target_page_start": 1,
        "target_page_end": 1,
        "strategy": ReconstructionStrategy.REFLOW.value,
        "status": ReconstructionStatus.COMPLETED.value,
        "output_file_id": None,
        "page_hash": PAGE_HASH,
        "warning_count": 0,
        "metadata_json": '{"page_number":1}',
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return ReconstructionPage(**values)


def _block(page_id: str, index: int = 30, **overrides: object) -> ReconstructionBlock:
    values: dict[str, object] = {
        "id": _id("rcb_", index),
        "reconstruction_page_id": page_id,
        "block_id": BLOCK_ID,
        "strategy": ReconstructionStrategy.REFLOW.value,
        "fit_strategy": "ADJUST_GEOMETRY",
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "status": ReconstructionBlockStatus.REFLOWED.value,
        "font_mapping_json": '{"source":"Arial","target":"Arial"}',
        "overflow_json": None,
        "collision_json": None,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return ReconstructionBlock(**values)


def _mapping(job_id: str, index: int = 40, **overrides: object) -> TargetPageMapping:
    values: dict[str, object] = {
        "id": _id("tpm_", index),
        "reconstruction_job_id": job_id,
        "source_page_id": PAGE_ID,
        "target_page_number": 1,
        "mapping_type": TargetPageMappingType.ONE_TO_ONE.value,
        "mapping_order": 0,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return TargetPageMapping(**values)


def test_reconstruction_migration_has_expected_tables_columns_indexes_and_strict_mode(
    reconstruction_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = reconstruction_database
    database = inspect(engine)
    expected_columns = {
        "reconstruction_jobs": [
            "id",
            "project_id",
            "document_id",
            "application_job_id",
            "mode",
            "settings_version",
            "settings_json",
            "status",
            "progress",
            "reconstruction_hash",
            "created_at",
            "started_at",
            "completed_at",
            "error_code",
        ],
        "reconstruction_pages": [
            "id",
            "reconstruction_job_id",
            "source_page_id",
            "target_page_start",
            "target_page_end",
            "strategy",
            "status",
            "output_file_id",
            "page_hash",
            "warning_count",
            "metadata_json",
            "created_at",
            "updated_at",
        ],
        "reconstruction_blocks": [
            "id",
            "reconstruction_page_id",
            "block_id",
            "strategy",
            "fit_strategy",
            "source_geometry_json",
            "target_geometry_json",
            "status",
            "font_mapping_json",
            "overflow_json",
            "collision_json",
            "created_at",
            "updated_at",
        ],
        "target_page_mappings": [
            "id",
            "reconstruction_job_id",
            "source_page_id",
            "target_page_number",
            "mapping_type",
            "mapping_order",
            "created_at",
        ],
    }
    for table_name, columns in expected_columns.items():
        assert [column["name"] for column in database.get_columns(table_name)] == columns
        assert database.get_pk_constraint(table_name)["constrained_columns"] == ["id"]
        with engine.connect() as connection:
            table_sql = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).scalar_one()
        assert table_sql.rstrip().endswith("STRICT")

    assert {
        index["name"]: index["unique"] for index in database.get_indexes("reconstruction_jobs")
    } == {"uq_reconstruction_jobs_hash": 1}
    assert {
        index["name"]: index["unique"] for index in database.get_indexes("reconstruction_blocks")
    } == {"uq_reconstruction_blocks_page_block": 1}


def test_reconstruction_job_page_block_and_mapping_persist(
    reconstruction_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = reconstruction_database
    job = _job()
    page = _page(job.id)
    block = _block(page.id)
    mapping = _mapping(job.id)

    with transaction_scope(factory) as session:
        session.add(job)
        session.flush()
        session.add(page)
        session.flush()
        session.add(block)
        session.add(mapping)

    with factory() as session:
        persisted_job = session.get(ReconstructionJob, job.id)
        persisted_page = session.get(ReconstructionPage, page.id)
        persisted_block = session.get(ReconstructionBlock, block.id)
        persisted_mapping = session.get(TargetPageMapping, mapping.id)

    assert persisted_job is not None
    assert persisted_job.status == ReconstructionStatus.COMPLETED.value
    assert persisted_page is not None
    assert persisted_page.target_page_start == 1
    assert persisted_block is not None
    assert persisted_block.status == ReconstructionBlockStatus.REFLOWED.value
    assert persisted_mapping is not None
    assert persisted_mapping.mapping_type == TargetPageMappingType.ONE_TO_ONE.value


def test_completed_reconstruction_hash_is_unique_per_project_but_versions_can_differ(
    reconstruction_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = reconstruction_database
    with transaction_scope(factory) as session:
        session.add(_job(50, reconstruction_hash="same-hash"))
        session.add(_job(51, reconstruction_hash="different-hash"))

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_job(52, reconstruction_hash="same-hash"))
        session.flush()

    with transaction_scope(factory) as session:
        session.add(
            _job(
                53,
                status=ReconstructionStatus.FAILED.value,
                progress=0.4,
                completed_at=None,
                reconstruction_hash="same-hash",
            )
        )

    with factory() as session:
        hashes = session.scalars(
            select(ReconstructionJob.reconstruction_hash).where(
                ReconstructionJob.project_id == PROJECT_ID
            )
        ).all()
    assert sorted(hashes) == ["different-hash", "same-hash", "same-hash"]


@pytest.mark.parametrize(
    "factory_name, overrides",
    (
        ("job", {"progress": 1.1}),
        ("job", {"settings_json": "{invalid"}),
        ("page", {"target_page_end": 0}),
        ("page", {"metadata_json": "{invalid"}),
        ("block", {"source_geometry_json": "{invalid"}),
        ("block", {"status": "UNKNOWN"}),
        ("mapping", {"mapping_type": "UNKNOWN"}),
        ("mapping", {"target_page_number": 0}),
    ),
)
def test_reconstruction_constraints_reject_invalid_records(
    reconstruction_database: tuple[Path, Engine, sessionmaker[Session]],
    factory_name: str,
    overrides: dict[str, object],
) -> None:
    _root, _engine, factory = reconstruction_database
    with factory() as session, pytest.raises(IntegrityError):
        job = _job(60)
        session.add(job)
        session.flush()
        if factory_name == "job":
            session.add(_job(61, **overrides))
        elif factory_name == "page":
            session.add(_page(job.id, 62, **overrides))
        elif factory_name == "block":
            page = _page(job.id, 63)
            session.add(page)
            session.flush()
            session.add(_block(page.id, 64, **overrides))
        else:
            session.add(_mapping(job.id, 65, **overrides))
        session.flush()


def test_reconstruction_migration_downgrades_and_reupgrades_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "reconstruction-migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert (
            not {
                "reconstruction_jobs",
                "reconstruction_pages",
                "reconstruction_blocks",
                "target_page_mappings",
            }
            & tables
        )
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "reconstruction_jobs",
            "reconstruction_pages",
            "reconstruction_blocks",
            "target_page_mappings",
        } <= tables
    finally:
        engine.dispose()
