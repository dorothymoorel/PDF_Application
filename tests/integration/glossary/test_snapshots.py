import hashlib
import json
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.glossary import (
    Glossary,
    GlossaryMatchMode,
    GlossaryRevision,
    GlossaryRevisionType,
    GlossaryRuleType,
    GlossaryScope,
    GlossarySnapshot,
    GlossaryTerm,
)
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import ImmutableStoredFileError, LocalFileStorage
from transloka_glossary.snapshots import (
    GlossarySnapshotIntegrityError,
    canonical_glossary_snapshot_json,
    create_glossary_snapshot,
    load_glossary_snapshot,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = datetime(2026, 8, 11, tzinfo=UTC)
CREATED_AT_TEXT = "2026-08-11T00:00:00.000Z"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 201)
GLOSSARY_ID = _id("gls_", 202)
TERM_A_ID = _id("trm_", 203)
TERM_B_ID = _id("trm_", 204)
TERM_INACTIVE_ID = _id("trm_", 205)


@dataclass(frozen=True, slots=True)
class SnapshotContext:
    root: Path
    engine: Engine
    factory: sessionmaker[Session]
    storage: LocalFileStorage


@pytest.fixture
def snapshot_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[SnapshotContext]:
    root = tmp_path / "Glossary Snapshot Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Glossary Snapshot Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT_TEXT,
        )
        session.add(_glossary())
        session.flush()
        session.add_all(
            (
                _term(
                    TERM_A_ID,
                    "framework",
                    "kerangka kerja",
                    priority=10,
                ),
                _term(
                    TERM_B_ID,
                    "API",
                    None,
                    rule_type=GlossaryRuleType.KEEP_ORIGINAL,
                    scope=GlossaryScope.SYSTEM,
                    scope_reference_id=None,
                    priority=100,
                ),
                _term(
                    TERM_INACTIVE_ID,
                    "inactive",
                    "nonaktif",
                    status="INACTIVE",
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                _revision(TERM_A_ID, 301),
                _revision(TERM_B_ID, 302),
                _revision(TERM_INACTIVE_ID, 303),
            )
        )
    context = SnapshotContext(
        root=root,
        engine=engine,
        factory=factory,
        storage=LocalFileStorage(directories),
    )
    try:
        yield context
    finally:
        engine.dispose()
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def _glossary() -> Glossary:
    return Glossary(
        id=GLOSSARY_ID,
        project_id=PROJECT_ID,
        name="Project Glossary",
        description=None,
        source_language="en",
        target_language="id",
        scope=GlossaryScope.PROJECT.value,
        domain=None,
        status="ACTIVE",
        version=1,
        is_default=1,
        created_at=CREATED_AT_TEXT,
        updated_at=CREATED_AT_TEXT,
        deleted_at=None,
    )


def _term(
    term_id: str,
    source_term: str,
    target_term: str | None,
    *,
    rule_type: GlossaryRuleType = GlossaryRuleType.TRANSLATE_AS,
    scope: GlossaryScope = GlossaryScope.PROJECT,
    scope_reference_id: str | None = PROJECT_ID,
    priority: int = 0,
    status: str = "ACTIVE",
) -> GlossaryTerm:
    return GlossaryTerm(
        id=term_id,
        glossary_id=GLOSSARY_ID,
        source_term=source_term,
        normalized_source_term=source_term.casefold(),
        rule_type=rule_type.value,
        target_term=target_term,
        scope=scope.value,
        scope_reference_id=scope_reference_id,
        priority=priority,
        case_sensitive=0,
        whole_word=1,
        match_mode=GlossaryMatchMode.PHRASE.value,
        capitalization_policy="PRESERVE_SOURCE_CASE",
        inflection_policy="USE_BASE_TERM",
        first_use_policy="NONE",
        status=status,
        term_source="USER_CREATED",
        confidence=1.0,
        notes=None,
        created_at=CREATED_AT_TEXT,
        updated_at=CREATED_AT_TEXT,
    )


def _revision(term_id: str, value: int) -> GlossaryRevision:
    return GlossaryRevision(
        id=_id("grv_", value),
        term_id=term_id,
        revision_number=1,
        revision_type=GlossaryRevisionType.CREATE_TERM.value,
        previous_value_json=None,
        new_value_json="{}",
        reason=None,
        created_at=CREATED_AT_TEXT,
    )


def test_repeated_snapshot_reuses_identical_canonical_content(
    snapshot_context: SnapshotContext,
) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        first = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
    with transaction_scope(context.factory) as session:
        repeated = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
    with context.factory() as session:
        snapshot_count = session.scalar(select(func.count()).select_from(GlossarySnapshot))
        file_count = session.scalar(select(func.count()).select_from(StoredFile))

    assert repeated == first
    assert first.id.startswith("gsn_")
    assert first.version == 1
    assert first.term_count == 2
    assert [rule.term_id for rule in first.compiled.rules] == [TERM_A_ID, TERM_B_ID]
    assert TERM_INACTIVE_ID not in {rule.term_id for rule in first.compiled.rules}
    assert first.source_versions[0].glossary_id == GLOSSARY_ID
    assert first.source_versions[0].version == 1
    assert snapshot_count == 1
    assert file_count == 1
    payload = canonical_glossary_snapshot_json(first.compiled)
    assert first.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert json.loads(payload)["rules"][0]["scope"] == GlossaryScope.PROJECT.value


def test_changed_term_creates_new_version_without_mutating_old_snapshot(
    snapshot_context: SnapshotContext,
) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        first = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
    with transaction_scope(context.factory) as session:
        term = session.get(GlossaryTerm, TERM_A_ID)
        glossary = session.get(Glossary, GLOSSARY_ID)
        assert term is not None and glossary is not None
        term.target_term = "kerangka"
        glossary.version = 2
        session.add(
            GlossaryRevision(
                id=_id("grv_", 304),
                term_id=TERM_A_ID,
                revision_number=2,
                revision_type=GlossaryRevisionType.CHANGE_TARGET.value,
                previous_value_json='{"target_term":"kerangka kerja"}',
                new_value_json='{"target_term":"kerangka"}',
                reason=None,
                created_at=CREATED_AT_TEXT,
            )
        )
    with transaction_scope(context.factory) as session:
        second = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
    with context.factory() as session:
        restored_first = load_glossary_snapshot(
            first.id,
            session=session,
            storage=context.storage,
        )

    assert second.version == 2
    assert second.id != first.id
    assert second.snapshot_file_id != first.snapshot_file_id
    assert second.checksum_sha256 != first.checksum_sha256
    assert second.source_versions[0].version == 2
    assert second.compiled.rules[0].revision == 2
    assert second.compiled.rules[0].target_term == "kerangka"
    assert restored_first.compiled.rules[0].target_term == "kerangka kerja"
    assert restored_first.checksum_sha256 == first.checksum_sha256


def test_tampered_snapshot_is_rejected(snapshot_context: SnapshotContext) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        created = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
        file_row = session.get(StoredFile, created.snapshot_file_id)
        assert file_row is not None
        storage_key = file_row.storage_key
    stored_path = context.root / Path(storage_key)
    stored_path.chmod(stat.S_IREAD | stat.S_IWRITE)
    stored_path.write_bytes(b'{"tampered":true}')

    with (
        context.factory() as session,
        pytest.raises(
            GlossarySnapshotIntegrityError,
            match="checksum",
        ),
    ):
        load_glossary_snapshot(created.id, session=session, storage=context.storage)


def test_snapshot_file_and_database_row_are_immutable(
    snapshot_context: SnapshotContext,
) -> None:
    context = snapshot_context
    with transaction_scope(context.factory) as session:
        created = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            created_at=CREATED_AT,
        )
        file_row = session.get(StoredFile, created.snapshot_file_id)
        assert file_row is not None
        storage_key = file_row.storage_key
        assert file_row.is_immutable == 1
        assert file_row.metadata_json is not None
        assert json.loads(file_row.metadata_json)["artifact_type"] == "GLOSSARY_SNAPSHOT"

    stored_path = context.root / Path(storage_key)
    assert not stored_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    with pytest.raises(ImmutableStoredFileError):
        context.storage.delete(storage_key)
    with context.factory() as session, pytest.raises(IntegrityError):
        row = session.get(GlossarySnapshot, created.id)
        assert row is not None
        row.term_count = 99
        session.flush()
