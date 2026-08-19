import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType
from transloka_core.database.models.translation import (
    SegmentTranslation,
    TranslationAttempt,
    TranslationBatch,
    TranslationBatchSegment,
    TranslationValidation,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-17T00:00:00.000Z"
PROJECT_ID = f"prj_{UUID(int=1)}"
ORIGINAL_FILE_ID = f"fil_{UUID(int=2)}"
SNAPSHOT_FILE_ID = f"fil_{UUID(int=3)}"
DOCUMENT_ID = f"doc_{UUID(int=4)}"
PAGE_ID = f"pag_{UUID(int=5)}"
SECTION_ID = f"sec_{UUID(int=6)}"
BLOCK_ID = f"blk_{UUID(int=7)}"
SEGMENT_ID = f"seg_{UUID(int=8)}"
SNAPSHOT_ID = f"gsn_{UUID(int=9)}"
BATCH_ID = f"tbt_{UUID(int=10)}"
SECOND_BATCH_ID = f"tbt_{UUID(int=11)}"
ATTEMPT_ID = f"tat_{UUID(int=12)}"
SECOND_ATTEMPT_ID = f"tat_{UUID(int=13)}"


@pytest.fixture
def translation_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Translation Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        session.execute(
            text(
                "INSERT INTO projects "
                "(id, name, description, status, source_language, target_language, "
                "document_type, translation_style, reconstruction_mode, progress, "
                "active_document_id, settings_json, created_at, updated_at, archived_at, deleted_at) "
                "VALUES (:id, 'Translation project', NULL, 'CREATED', 'en', 'id', "
                "'TECHNICAL_BOOK', 'PROFESSIONAL', 'HYBRID', 0.0, NULL, '{}', :created, :created, NULL, NULL)"
            ),
            {"id": PROJECT_ID, "created": CREATED_AT},
        )
        for file_id, role, filename in (
            (ORIGINAL_FILE_ID, "ORIGINAL", "source.pdf"),
            (SNAPSHOT_FILE_ID, "IR_SNAPSHOT", "glossary.json"),
        ):
            session.execute(
                text(
                    "INSERT INTO stored_files "
                    "(id, project_id, document_id, file_role, storage_key, original_filename, "
                    "safe_filename, mime_type, size_bytes, checksum_sha256, is_immutable, status, "
                    "metadata_json, created_at, deleted_at) "
                    "VALUES (:id, :project_id, NULL, :role, :storage_key, :filename, :filename, "
                    "'application/octet-stream', 1, :checksum, 1, 'VALIDATED', NULL, :created, NULL)"
                ),
                {
                    "id": file_id,
                    "project_id": PROJECT_ID,
                    "role": role,
                    "storage_key": f"projects/{PROJECT_ID}/{filename}",
                    "filename": filename,
                    "checksum": "a" * 64 if role == "ORIGINAL" else "b" * 64,
                    "created": CREATED_AT,
                },
            )
        session.execute(
            text(
                "INSERT INTO documents "
                "(id, project_id, original_file_id, ir_version, title, author, document_type, "
                "document_class, source_language, target_language, page_count, word_count_estimate, "
                "has_text_layer, scanned_page_count, image_count, table_count, status, metadata_json, "
                "analysis_json, created_at, updated_at) VALUES "
                "(:id, :project_id, :file_id, '0.1', 'Source', NULL, 'TECHNICAL_BOOK', 'DIGITAL_PDF', "
                "'en', 'id', 1, 2, 1, 0, 0, 0, 'READY_FOR_TRANSLATION', NULL, NULL, :created, :created)"
            ),
            {
                "id": DOCUMENT_ID,
                "project_id": PROJECT_ID,
                "file_id": ORIGINAL_FILE_ID,
                "created": CREATED_AT,
            },
        )
        session.execute(
            text(
                "INSERT INTO document_pages "
                "(id, document_id, source_page_number, logical_page_number, width_points, height_points, "
                "rotation_degrees, page_type, page_classification, column_count, reading_direction, "
                "status, render_file_id, thumbnail_file_id, native_extraction_confidence, "
                "ocr_confidence, structure_confidence, metadata_json, created_at, updated_at) VALUES "
                "(:id, :document_id, 1, NULL, 612.0, 792.0, 0.0, 'DIGITAL', NULL, 1, 'LTR', "
                "'EXTRACTED', NULL, NULL, 1.0, NULL, NULL, NULL, :created, :created)"
            ),
            {"id": PAGE_ID, "document_id": DOCUMENT_ID, "created": CREATED_AT},
        )
        session.execute(
            text(
                "INSERT INTO document_sections "
                "(id, document_id, parent_section_id, section_type, level, section_order, "
                "title_segment_id, start_page_id, end_page_id, source_summary, context_json, created_at, updated_at) "
                "VALUES (:id, :document_id, NULL, 'CHAPTER', 0, 0, NULL, :page_id, :page_id, NULL, NULL, :created, :created)"
            ),
            {
                "id": SECTION_ID,
                "document_id": DOCUMENT_ID,
                "page_id": PAGE_ID,
                "created": CREATED_AT,
            },
        )
        session.execute(
            text(
                "INSERT INTO document_blocks "
                "(id, page_id, section_id, parent_block_id, block_type, semantic_role, page_reading_order, "
                "global_reading_order, source_text, normalized_source_text, source_geometry_json, "
                "target_geometry_json, style_json, detail_json, status, confidence, created_at, updated_at) "
                "VALUES (:id, :page_id, :section_id, NULL, 'PARAGRAPH', 'BODY_TEXT', 0, 0, 'Hello', 'Hello', '{}', NULL, NULL, NULL, 'STRUCTURED', 1.0, :created, :created)"
            ),
            {
                "id": BLOCK_ID,
                "page_id": PAGE_ID,
                "section_id": SECTION_ID,
                "created": CREATED_AT,
            },
        )
        session.execute(
            text(
                "INSERT INTO document_segments "
                "(id, block_id, section_id, segment_order, global_order, source_text, native_text, ocr_text, "
                "resolved_source_text, normalized_source_text, protected_source_text, machine_translation, "
                "reviewed_translation, final_text, source_language, target_language, status, review_status, "
                "is_locked, current_revision, confidence_overall, confidence_json, translation_settings_hash, "
                "created_at, updated_at) VALUES (:id, :block_id, :section_id, 0, 0, 'Hello', 'Hello', NULL, "
                "'Hello', 'Hello', NULL, NULL, NULL, NULL, 'en', 'id', 'READY_FOR_TRANSLATION', 'NOT_REVIEWED', "
                "0, 0, NULL, NULL, NULL, :created, :created)"
            ),
            {
                "id": SEGMENT_ID,
                "block_id": BLOCK_ID,
                "section_id": SECTION_ID,
                "created": CREATED_AT,
            },
        )
        session.execute(
            text(
                "INSERT INTO glossary_snapshots "
                "(id, project_id, document_id, version, checksum_sha256, term_count, source_versions_json, "
                "snapshot_file_id, created_at) VALUES (:id, :project_id, :document_id, 1, :checksum, 0, '{}', :file_id, :created)"
            ),
            {
                "id": SNAPSHOT_ID,
                "project_id": PROJECT_ID,
                "document_id": DOCUMENT_ID,
                "checksum": "c" * 64,
                "file_id": SNAPSHOT_FILE_ID,
                "created": CREATED_AT,
            },
        )
    yield root, engine, factory
    engine.dispose()


def _batch(batch_id: str = BATCH_ID, **overrides: object) -> TranslationBatch:
    values: dict[str, object] = {
        "id": batch_id,
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "section_id": SECTION_ID,
        "glossary_snapshot_id": SNAPSHOT_ID,
        "provider_type": "LOCAL",
        "model_id": "qwen3:1.7b",
        "prompt_version": "translation_prompt_0.1",
        "pipeline_version": "pipeline_0.1",
        "status": "QUEUED",
        "segment_count": 1,
        "source_character_count": 5,
        "estimated_input_tokens": 2,
        "actual_input_tokens": None,
        "actual_output_tokens": None,
        "batch_order": 0,
        "idempotency_key": f"translation:{batch_id}",
        "settings_json": json.dumps({"style": "PROFESSIONAL"}),
        "created_at": CREATED_AT,
        "started_at": None,
        "completed_at": None,
        "error_code": None,
    }
    values.update(overrides)
    return TranslationBatch(**values)


def _attempt(attempt_id: str = ATTEMPT_ID, **overrides: object) -> TranslationAttempt:
    values: dict[str, object] = {
        "id": attempt_id,
        "batch_id": BATCH_ID,
        "attempt_number": 1,
        "provider_type": "LOCAL",
        "model_id": "qwen3:1.7b",
        "status": "COMPLETED",
        "request_hash": "request-hash-1",
        "response_hash": "response-hash-1",
        "latency_ms": 100,
        "input_tokens": 2,
        "output_tokens": 2,
        "retry_reason": None,
        "error_code": None,
        "error_message": None,
        "provider_metadata_json": "{}",
        "created_at": CREATED_AT,
        "completed_at": CREATED_AT,
    }
    values.update(overrides)
    return TranslationAttempt(**values)


def test_translation_schema_has_documented_columns_indexes_and_foreign_keys(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = translation_database
    database = inspect(engine)
    expected_columns = {
        "translation_batches": [
            "id",
            "project_id",
            "document_id",
            "section_id",
            "glossary_snapshot_id",
            "provider_type",
            "model_id",
            "prompt_version",
            "pipeline_version",
            "status",
            "segment_count",
            "source_character_count",
            "estimated_input_tokens",
            "actual_input_tokens",
            "actual_output_tokens",
            "batch_order",
            "idempotency_key",
            "settings_json",
            "created_at",
            "started_at",
            "completed_at",
            "error_code",
        ],
        "translation_batch_segments": ["batch_id", "segment_id", "segment_order"],
        "translation_attempts": [
            "id",
            "batch_id",
            "attempt_number",
            "provider_type",
            "model_id",
            "status",
            "request_hash",
            "response_hash",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "retry_reason",
            "error_code",
            "error_message",
            "provider_metadata_json",
            "created_at",
            "completed_at",
        ],
        "segment_translations": [
            "id",
            "segment_id",
            "batch_id",
            "attempt_id",
            "translated_text_raw",
            "translated_text_restored",
            "status",
            "confidence_overall",
            "confidence_json",
            "validation_status",
            "created_at",
        ],
        "translation_validations": [
            "id",
            "segment_translation_id",
            "validator_type",
            "status",
            "score",
            "details_json",
            "created_at",
        ],
    }
    for table_name, columns in expected_columns.items():
        assert [column["name"] for column in database.get_columns(table_name)] == columns

    assert {index["name"] for index in database.get_indexes("translation_batches")} == {
        "uq_translation_batches_idempotency_key",
        "ix_translation_batches_project_status",
        "ix_translation_batches_document_order",
    }
    assert {index["name"] for index in database.get_indexes("translation_batch_segments")} == {
        "uq_translation_batch_segments_order"
    }
    assert {index["name"] for index in database.get_indexes("translation_attempts")} == {
        "uq_translation_attempts_number"
    }
    assert {index["name"] for index in database.get_indexes("segment_translations")} == {
        "ix_segment_translations_segment"
    }
    assert {index["name"] for index in database.get_indexes("translation_validations")} == {
        "uq_translation_validations_type"
    }
    assert {
        foreign_key["referred_table"]
        for foreign_key in database.get_foreign_keys("translation_batches")
    } == {"projects", "documents", "document_sections", "glossary_snapshots"}


def test_batch_segment_join_and_attempt_number_are_unique(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_batch())
        session.flush()
        session.add(
            TranslationBatchSegment(batch_id=BATCH_ID, segment_id=SEGMENT_ID, segment_order=0)
        )
        session.flush()
        session.add(_attempt())

    with pytest.raises(IntegrityError):
        with transaction_scope(factory) as session:
            session.add(
                TranslationBatchSegment(batch_id=BATCH_ID, segment_id=SEGMENT_ID, segment_order=1)
            )

    with pytest.raises(IntegrityError):
        with transaction_scope(factory) as session:
            session.add(_attempt(attempt_id=SECOND_ATTEMPT_ID))


def test_translation_result_is_append_only_across_attempts(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_batch())
        session.flush()
        session.add(
            TranslationBatchSegment(batch_id=BATCH_ID, segment_id=SEGMENT_ID, segment_order=0)
        )
        session.flush()
        session.add(_attempt())
        session.add(_attempt(SECOND_ATTEMPT_ID, attempt_number=2, request_hash="request-hash-2"))
        session.flush()
        session.add(
            SegmentTranslation(
                id="translation-result-1",
                segment_id=SEGMENT_ID,
                batch_id=BATCH_ID,
                attempt_id=ATTEMPT_ID,
                translated_text_raw="First result",
                translated_text_restored="First result",
                status="MACHINE_TRANSLATED",
                confidence_overall=0.6,
                confidence_json='{"overall":0.6}',
                validation_status="RETRY_REQUIRED",
                created_at=CREATED_AT,
            )
        )
        session.add(
            SegmentTranslation(
                id="translation-result-2",
                segment_id=SEGMENT_ID,
                batch_id=BATCH_ID,
                attempt_id=SECOND_ATTEMPT_ID,
                translated_text_raw="Second result",
                translated_text_restored="Second result",
                status="MACHINE_TRANSLATED",
                confidence_overall=0.9,
                confidence_json='{"overall":0.9}',
                validation_status="PASSED",
                created_at="2026-08-17T00:00:01.000Z",
            )
        )
        session.add(
            TranslationValidation(
                id="validation-1",
                segment_translation_id="translation-result-2",
                validator_type="PLACEHOLDER_INTEGRITY",
                status="PASSED",
                score=1.0,
                details_json='{"missing":[]}',
                created_at=CREATED_AT,
            )
        )
        session.flush()
        results = (
            session.execute(
                text(
                    "SELECT attempt_id, translated_text_raw FROM segment_translations "
                    "WHERE segment_id = :segment_id ORDER BY created_at"
                ),
                {"segment_id": SEGMENT_ID},
            )
            .tuples()
            .all()
        )

    assert list(results) == [(ATTEMPT_ID, "First result"), (SECOND_ATTEMPT_ID, "Second result")]

    with pytest.raises(IntegrityError):
        with transaction_scope(factory) as session:
            session.add(
                TranslationValidation(
                    id="validation-2",
                    segment_translation_id="translation-result-2",
                    validator_type="PLACEHOLDER_INTEGRITY",
                    status="PASSED",
                    score=1.0,
                    details_json="{}",
                    created_at=CREATED_AT,
                )
            )


@pytest.mark.parametrize(
    ("table_name", "values"),
    [
        ("translation_batches", {"segment_count": -1}),
        ("translation_attempts", {"attempt_number": 0}),
        ("segment_translations", {"confidence_overall": 1.1}),
        ("translation_validations", {"validator_type": "UNKNOWN"}),
    ],
)
def test_translation_constraints_reject_invalid_values(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
    table_name: str,
    values: dict[str, object],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_batch())
        session.flush()
        session.add(
            TranslationBatchSegment(batch_id=BATCH_ID, segment_id=SEGMENT_ID, segment_order=0)
        )
        session.flush()
        session.add(_attempt())
        session.flush()
        session.add(
            SegmentTranslation(
                id="translation-result-1",
                segment_id=SEGMENT_ID,
                batch_id=BATCH_ID,
                attempt_id=ATTEMPT_ID,
                translated_text_raw="Result",
                translated_text_restored=None,
                status="MACHINE_TRANSLATED",
                confidence_overall=0.5,
                confidence_json=None,
                validation_status="PASSED",
                created_at=CREATED_AT,
            )
        )
        session.flush()

    with pytest.raises(IntegrityError):
        with transaction_scope(factory) as session:
            if table_name == "translation_batches":
                session.add(_batch(SECOND_BATCH_ID, **values))
            elif table_name == "translation_attempts":
                session.add(_attempt(SECOND_ATTEMPT_ID, **values))
            elif table_name == "segment_translations":
                session.add(
                    SegmentTranslation(
                        id="translation-result-invalid",
                        segment_id=SEGMENT_ID,
                        batch_id=BATCH_ID,
                        attempt_id=ATTEMPT_ID,
                        translated_text_raw="Result",
                        translated_text_restored=None,
                        status="MACHINE_TRANSLATED",
                        confidence_overall=values["confidence_overall"],
                        confidence_json=None,
                        validation_status="PASSED",
                        created_at=CREATED_AT,
                    )
                )
            else:
                session.add(
                    TranslationValidation(
                        id="validation-invalid",
                        segment_translation_id="translation-result-1",
                        validator_type=values["validator_type"],
                        status="FAILED",
                        score=None,
                        details_json=None,
                        created_at=CREATED_AT,
                    )
                )
            session.flush()


def test_translation_migration_downgrade_and_upgrade_are_reversible(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, engine, _factory = translation_database
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.downgrade(configuration, "0010_local_models")
    try:
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert (
            not {
                "translation_batches",
                "translation_batch_segments",
                "translation_attempts",
                "segment_translations",
                "translation_validations",
            }
            & tables
        )
    finally:
        command.upgrade(configuration, "head")

    assert (root / "database" / "transloka.db").is_file()


def _segment_revision(
    revision_id: str = "revision-1", revision_number: int = 1, **overrides: object
) -> SegmentRevision:
    values: dict[str, object] = {
        "id": revision_id,
        "segment_id": SEGMENT_ID,
        "revision_number": revision_number,
        "revision_type": SegmentRevisionType.MACHINE_TRANSLATION,
        "previous_text": None,
        "new_text": "Hello dunia",
        "source_translation_id": None,
        "reason": None,
        "metadata_json": None,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return SegmentRevision(**values)


def test_segment_revisions_are_sequential_and_preserve_source_reference(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_batch())
        session.flush()
        session.add(
            TranslationBatchSegment(batch_id=BATCH_ID, segment_id=SEGMENT_ID, segment_order=0)
        )
        session.flush()
        session.add(_attempt())
        session.flush()
        session.add(
            SegmentTranslation(
                id="translation-result-1",
                segment_id=SEGMENT_ID,
                batch_id=BATCH_ID,
                attempt_id=ATTEMPT_ID,
                translated_text_raw="Hello dunia",
                translated_text_restored="Hello dunia",
                status="MACHINE_TRANSLATED",
                confidence_overall=0.9,
                confidence_json=None,
                validation_status="PASSED",
                created_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(_segment_revision(source_translation_id="translation-result-1"))
        session.add(
            _segment_revision(
                revision_id="revision-2",
                revision_number=2,
                revision_type=SegmentRevisionType.USER_EDIT,
                previous_text="Hello dunia",
                new_text="Halo dunia",
                reason="Terminology correction",
            )
        )

    with transaction_scope(factory) as session:
        revisions = (
            session.execute(
                text(
                    "SELECT revision_number, revision_type, previous_text, new_text, "
                    "source_translation_id FROM segment_revisions "
                    "WHERE segment_id = :segment_id ORDER BY revision_number"
                ),
                {"segment_id": SEGMENT_ID},
            )
            .tuples()
            .all()
        )

    assert list(revisions) == [
        (1, SegmentRevisionType.MACHINE_TRANSLATION, None, "Hello dunia", "translation-result-1"),
        (2, SegmentRevisionType.USER_EDIT, "Hello dunia", "Halo dunia", None),
    ]


def test_segment_revision_number_is_unique_per_segment(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_segment_revision())

    with pytest.raises(IntegrityError):
        with transaction_scope(factory) as session:
            session.add(_segment_revision(revision_id="revision-duplicate"))
            session.flush()


def test_restore_creates_new_append_only_revision(
    translation_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = translation_database
    with transaction_scope(factory) as session:
        session.add(_segment_revision())
        session.add(
            _segment_revision(
                revision_id="revision-2",
                revision_number=2,
                revision_type=SegmentRevisionType.USER_EDIT,
                previous_text="Hello dunia",
                new_text="Halo dunia",
            )
        )
        session.flush()
        session.add(
            _segment_revision(
                revision_id="revision-3",
                revision_number=3,
                revision_type=SegmentRevisionType.RESTORE_VERSION,
                previous_text="Halo dunia",
                new_text="Hello dunia",
                reason="Restore revision 1",
            )
        )

    with transaction_scope(factory) as session:
        restored = session.get(SegmentRevision, "revision-3")
        assert restored is not None
        assert restored.revision_type == SegmentRevisionType.RESTORE_VERSION
        assert restored.new_text == "Hello dunia"
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE segment_revisions SET new_text = 'Tampered' WHERE id = 'revision-1'")
            )
