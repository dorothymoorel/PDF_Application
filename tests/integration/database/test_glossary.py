import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.glossary import (
    Glossary,
    GlossaryConflict,
    GlossaryMatchMode,
    GlossaryRevision,
    GlossaryRevisionType,
    GlossaryRuleType,
    GlossaryScope,
    GlossarySnapshot,
    GlossaryTerm,
    ProtectedItem,
    ProtectedItemType,
    TermCandidate,
    TermOccurrence,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0008_document_ir_structure"
CREATED_AT = "2026-08-11T00:00:00.000Z"
SOURCE_GEOMETRY = (
    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,"y":120.0,"width":200.0,"height":40.0}'
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
ORIGINAL_FILE_ID = _id("fil_", 2)
DOCUMENT_ID = _id("doc_", 3)
PAGE_ID = _id("pag_", 4)
BLOCK_ID = _id("blk_", 5)
SEGMENT_ID = _id("seg_", 6)
SNAPSHOT_FILE_ID = _id("fil_", 7)
GLOSSARY_ID = _id("gls_", 10)
TERM_ID = _id("trm_", 11)
REVISION_ID = _id("grv_", 12)
SNAPSHOT_ID = _id("gsn_", 13)
CANDIDATE_ID = _id("tcd_", 14)
OCCURRENCE_ID = _id("occ_", 15)
CONFLICT_ID = _id("gcf_", 16)
PROTECTED_ITEM_ID = _id("pit_", 17)

GLOSSARY_TABLES = {
    "glossaries",
    "glossary_terms",
    "glossary_revisions",
    "glossary_snapshots",
    "term_candidates",
    "term_occurrences",
    "glossary_conflicts",
    "protected_items",
}


@pytest.fixture
def glossary_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Glossary Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    _seed_document_context(factory)
    yield root, engine, factory
    engine.dispose()


def _seed_document_context(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Glossary Project",
            description=None,
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
            storage_key=f"projects/{PROJECT_ID}/original/source.pdf",
            original_filename="source.pdf",
            safe_filename="source.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
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
                title="Glossary document",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=5,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        files.create(
            file_id=SNAPSHOT_FILE_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            file_role=FileRole.IR_SNAPSHOT,
            storage_key=f"projects/{PROJECT_ID}/glossary/{SNAPSHOT_FILE_ID}.json",
            original_filename=None,
            safe_filename=f"{SNAPSHOT_FILE_ID}.json",
            mime_type="application/json",
            size_bytes=50,
            checksum_sha256="b" * 64,
            is_immutable=True,
            status=FileStatus.AVAILABLE,
            metadata=None,
            created_at=CREATED_AT,
        )
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=600.0,
                height_points=800.0,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=0.99,
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
                page_reading_order=0,
                global_reading_order=0,
                source_text="The workflow begins.",
                normalized_source_text="The workflow begins.",
                source_geometry_json=SOURCE_GEOMETRY,
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.TERMS_DETECTED.value,
                confidence=0.98,
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
                segment_order=0,
                global_order=0,
                source_text="The workflow begins.",
                native_text="The workflow begins.",
                ocr_text=None,
                resolved_source_text="The workflow begins.",
                normalized_source_text="The workflow begins.",
                protected_source_text=None,
                machine_translation=None,
                reviewed_translation=None,
                final_text=None,
                source_language="en",
                target_language="id",
                status=SegmentStatus.TERMS_DETECTED.value,
                review_status=ReviewStatus.NOT_REVIEWED.value,
                is_locked=0,
                current_revision=0,
                confidence_overall=0.99,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )


def _glossary(**overrides: object) -> Glossary:
    values: dict[str, object] = {
        "id": GLOSSARY_ID,
        "project_id": PROJECT_ID,
        "name": "Project Glossary",
        "description": "Technical terminology.",
        "source_language": "en",
        "target_language": "id",
        "scope": GlossaryScope.PROJECT.value,
        "domain": "SOFTWARE_ENGINEERING",
        "status": "ACTIVE",
        "version": 1,
        "is_default": 1,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "deleted_at": None,
    }
    values.update(overrides)
    return Glossary(**values)


def _term(**overrides: object) -> GlossaryTerm:
    values: dict[str, object] = {
        "id": TERM_ID,
        "glossary_id": GLOSSARY_ID,
        "source_term": "workflow",
        "normalized_source_term": "workflow",
        "rule_type": GlossaryRuleType.KEEP_ORIGINAL.value,
        "target_term": None,
        "scope": GlossaryScope.PROJECT.value,
        "scope_reference_id": PROJECT_ID,
        "priority": 100,
        "case_sensitive": 0,
        "whole_word": 1,
        "match_mode": GlossaryMatchMode.PHRASE.value,
        "capitalization_policy": "MATCH_SENTENCE_POSITION",
        "inflection_policy": "USE_BASE_TERM",
        "first_use_policy": "NONE",
        "status": "ACTIVE",
        "term_source": "USER_CREATED",
        "confidence": 1.0,
        "notes": None,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return GlossaryTerm(**values)


def _revision(**overrides: object) -> GlossaryRevision:
    values: dict[str, object] = {
        "id": REVISION_ID,
        "term_id": TERM_ID,
        "revision_number": 1,
        "revision_type": GlossaryRevisionType.CREATE_TERM.value,
        "previous_value_json": None,
        "new_value_json": '{"rule_type":"KEEP_ORIGINAL"}',
        "reason": None,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return GlossaryRevision(**values)


def _snapshot(**overrides: object) -> GlossarySnapshot:
    values: dict[str, object] = {
        "id": SNAPSHOT_ID,
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "version": 1,
        "checksum_sha256": "c" * 64,
        "term_count": 1,
        "source_versions_json": f'{{"{GLOSSARY_ID}":1}}',
        "snapshot_file_id": SNAPSHOT_FILE_ID,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return GlossarySnapshot(**values)


def _candidate(**overrides: object) -> TermCandidate:
    values: dict[str, object] = {
        "id": CANDIDATE_ID,
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "source_term": "credential",
        "normalized_source_term": "credential",
        "candidate_type": "DOMAIN_TERM",
        "recommended_rule_type": GlossaryRuleType.TRANSLATE_AS.value,
        "recommended_target_term": "kredensial",
        "occurrence_count": 3,
        "confidence": 0.91,
        "status": "DETECTED",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return TermCandidate(**values)


def _occurrence(**overrides: object) -> TermOccurrence:
    values: dict[str, object] = {
        "id": OCCURRENCE_ID,
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "term_id": TERM_ID,
        "candidate_id": None,
        "segment_id": SEGMENT_ID,
        "page_id": PAGE_ID,
        "start_offset": 4,
        "end_offset": 12,
        "matched_text": "workflow",
        "match_method": "PHRASE",
        "confidence": 0.99,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return TermOccurrence(**values)


def _conflict(**overrides: object) -> GlossaryConflict:
    values: dict[str, object] = {
        "id": CONFLICT_ID,
        "project_id": PROJECT_ID,
        "source_term": "workflow",
        "conflict_type": "SAME_SOURCE_DIFFERENT_TARGET",
        "rules_json": f'["{TERM_ID}"]',
        "status": "OPEN",
        "resolution_type": None,
        "resolution_json": None,
        "created_at": CREATED_AT,
        "resolved_at": None,
    }
    values.update(overrides)
    return GlossaryConflict(**values)


def _protected_item(**overrides: object) -> ProtectedItem:
    values: dict[str, object] = {
        "id": PROTECTED_ITEM_ID,
        "segment_id": SEGMENT_ID,
        "glossary_term_id": TERM_ID,
        "item_type": ProtectedItemType.TERM.value,
        "placeholder": "__TLK_TERM_0001_A7__",
        "source_value": "workflow",
        "replacement_value": "workflow",
        "rule_type": GlossaryRuleType.KEEP_ORIGINAL.value,
        "start_offset": 4,
        "end_offset": 12,
        "capitalization_policy": "PRESERVE_SOURCE_CASE",
        "status": "PROTECTED",
        "created_at": CREATED_AT,
        "restored_at": None,
    }
    values.update(overrides)
    return ProtectedItem(**values)


def _seed_glossary_and_term(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        session.add(_glossary())
        session.flush()
        session.add(_term())


def test_glossary_schema_has_required_tables_constraints_and_no_user_dependency(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = glossary_database
    database = inspect(engine)
    assert GLOSSARY_TABLES <= set(database.get_table_names())
    assert "glossary_context_rules" not in database.get_table_names()

    with engine.connect() as connection:
        definitions = {
            table: connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
                {"name": table},
            ).scalar_one()
            for table in GLOSSARY_TABLES
        }
    assert all("STRICT" in definition for definition in definitions.values())
    assert "ck_glossary_terms_translate_as_target" in definitions["glossary_terms"]
    assert "ck_term_occurrences_reference" in definitions["term_occurrences"]
    assert "ck_protected_items_end_offset" in definitions["protected_items"]

    all_columns = {
        column["name"] for table in GLOSSARY_TABLES for column in database.get_columns(table)
    }
    all_foreign_keys = {
        foreign_key["referred_table"]
        for table in GLOSSARY_TABLES
        for foreign_key in database.get_foreign_keys(table)
    }
    assert not any("user_id" in column or "account" in column for column in all_columns)
    assert not any("user" in table or "account" in table for table in all_foreign_keys)


def test_all_glossary_models_persist_and_reference_document_ir(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    with transaction_scope(factory) as session:
        session.add(_glossary())
        session.flush()
        session.add_all((_term(), _candidate(), _snapshot(), _conflict()))
        session.flush()
        session.add_all((_revision(), _occurrence(), _protected_item()))

    with factory() as session:
        glossary = session.get(Glossary, GLOSSARY_ID)
        term = session.get(GlossaryTerm, TERM_ID)
        revision = session.get(GlossaryRevision, REVISION_ID)
        snapshot = session.get(GlossarySnapshot, SNAPSHOT_ID)
        candidate = session.get(TermCandidate, CANDIDATE_ID)
        occurrence = session.get(TermOccurrence, OCCURRENCE_ID)
        conflict = session.get(GlossaryConflict, CONFLICT_ID)
        protected_item = session.get(ProtectedItem, PROTECTED_ITEM_ID)

        assert glossary is not None and glossary.name == "Project Glossary"
        assert term is not None and term.source_term == "workflow"
        assert revision is not None and revision.revision_number == 1
        assert snapshot is not None and snapshot.term_count == 1
        assert candidate is not None and candidate.occurrence_count == 3
        assert occurrence is not None and occurrence.segment_id == SEGMENT_ID
        assert conflict is not None and conflict.status == "OPEN"
        assert protected_item is not None and protected_item.placeholder.startswith("__TLK_")


def test_translate_as_requires_a_non_empty_target(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    with transaction_scope(factory) as session:
        session.add(_glossary())

    for index, target in enumerate((None, ""), start=1):
        with factory() as session, pytest.raises(IntegrityError):
            session.add(
                _term(
                    id=_id("trm_", 100 + index),
                    source_term=f"term-{index}",
                    normalized_source_term=f"term-{index}",
                    rule_type=GlossaryRuleType.TRANSLATE_AS.value,
                    target_term=target,
                )
            )
            session.flush()

    with transaction_scope(factory) as session:
        session.add(_term(rule_type=GlossaryRuleType.KEEP_ORIGINAL.value, target_term=None))
    with factory() as session:
        assert session.get(GlossaryTerm, TERM_ID) is not None


def test_active_term_identity_is_unique_but_archived_history_is_allowed(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    _seed_glossary_and_term(factory)

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_term(id=_id("trm_", 101)))
        session.flush()

    with transaction_scope(factory) as session:
        session.add(_term(id=_id("trm_", 102), status="ARCHIVED"))


def test_revision_numbers_are_unique_and_revision_rows_are_append_only(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    _seed_glossary_and_term(factory)
    with transaction_scope(factory) as session:
        session.add(_revision())

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_revision(id=_id("grv_", 101)))
        session.flush()

    with factory() as session, pytest.raises(IntegrityError):
        revision = session.get(GlossaryRevision, REVISION_ID)
        assert revision is not None
        revision.reason = "mutated"
        session.flush()

    with factory() as session:
        revision = session.get(GlossaryRevision, REVISION_ID)
        assert revision is not None and revision.reason is None


def test_snapshot_versions_are_unique_and_snapshot_rows_are_immutable(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    with transaction_scope(factory) as session:
        session.add(_snapshot())

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_snapshot(id=_id("gsn_", 101)))
        session.flush()

    with factory() as session, pytest.raises(IntegrityError):
        snapshot = session.get(GlossarySnapshot, SNAPSHOT_ID)
        assert snapshot is not None
        snapshot.term_count = 2
        session.flush()

    with factory() as session:
        snapshot = session.get(GlossarySnapshot, SNAPSHOT_ID)
        assert snapshot is not None and snapshot.term_count == 1


def test_database_rejects_invalid_glossary_values(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    invalid_glossaries = (
        _glossary(id="gls_invalid"),
        _glossary(version=0),
        _glossary(is_default=2),
        _glossary(scope="CUSTOM"),
        _glossary(name=" "),
    )
    for invalid_glossary in invalid_glossaries:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(invalid_glossary)
            session.flush()

    with transaction_scope(factory) as session:
        session.add(_glossary())
    invalid_terms = (
        _term(id=_id("trm_", 101), priority=-1, normalized_source_term="priority"),
        _term(id=_id("trm_", 102), whole_word=2, normalized_source_term="whole"),
        _term(id=_id("trm_", 103), match_mode="FUZZY", normalized_source_term="fuzzy"),
        _term(id=_id("trm_", 104), confidence=1.1, normalized_source_term="confidence"),
    )
    for invalid_term in invalid_terms:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(invalid_term)
            session.flush()


def test_occurrence_candidate_conflict_and_protected_constraints(
    glossary_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = glossary_database
    _seed_glossary_and_term(factory)
    with transaction_scope(factory) as session:
        session.add(_candidate())

    invalid_rows = (
        _candidate(id=_id("tcd_", 101), normalized_source_term="negative", occurrence_count=-1),
        _occurrence(id=_id("occ_", 102), term_id=None, candidate_id=None),
        _occurrence(id=_id("occ_", 103), start_offset=4, end_offset=4),
        _conflict(id=_id("gcf_", 104), rules_json="{invalid"),
        _protected_item(id=_id("pit_", 105), item_type="CUSTOM"),
        _protected_item(id=_id("pit_", 106), start_offset=12, end_offset=4),
    )
    for row in invalid_rows:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(row)
            session.flush()

    with transaction_scope(factory) as session:
        session.add(_protected_item())
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_protected_item(id=_id("pit_", 107)))
        session.flush()


def test_glossary_migration_downgrades_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "glossary migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert not GLOSSARY_TABLES & tables
        assert {"projects", "documents", "document_segments"} <= tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert GLOSSARY_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_glossary_model_import_creates_no_database(tmp_path: Path) -> None:
    root = tmp_path / "glossary import data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", "import transloka_core.database.models.glossary"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()


def test_glossary_model_metadata_matches_migration() -> None:
    model_tables = {
        Glossary.__tablename__,
        GlossaryTerm.__tablename__,
        GlossaryRevision.__tablename__,
        GlossarySnapshot.__tablename__,
        TermCandidate.__tablename__,
        TermOccurrence.__tablename__,
        GlossaryConflict.__tablename__,
        ProtectedItem.__tablename__,
    }
    assert model_tables == GLOSSARY_TABLES
