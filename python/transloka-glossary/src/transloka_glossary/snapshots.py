import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.glossary import (
    Glossary,
    GlossaryMatchMode,
    GlossaryRevision,
    GlossaryRuleType,
    GlossaryScope,
    GlossarySnapshot,
    GlossaryTerm,
)
from transloka_core.database.models.projects import Project
from transloka_core.repositories.files import (
    StoredFileAlreadyExistsError,
    StoredFileNotFoundError,
    StoredFileRecord,
    StoredFilesRepository,
    StoredFileStorageKeyExistsError,
)
from transloka_core.storage.local import (
    LocalFileStorage,
    LocalFileStorageError,
    StoredFileExistsError,
)

from transloka_glossary.resolution import scope_priority

_SCHEMA_VERSION = 1
_ARTIFACT_TYPE = "GLOSSARY_SNAPSHOT"
_ACTIVE = "ACTIVE"


class GlossarySnapshotError(RuntimeError):
    pass


class InvalidGlossarySnapshotRequestError(GlossarySnapshotError):
    pass


class GlossarySnapshotNotFoundError(GlossarySnapshotError):
    pass


class GlossarySnapshotIntegrityError(GlossarySnapshotError):
    pass


class GlossarySnapshotStorageError(GlossarySnapshotError):
    pass


class GlossarySnapshotVersionConflictError(GlossarySnapshotError):
    pass


@dataclass(frozen=True, order=True, slots=True)
class GlossarySourceVersion:
    glossary_id: str
    version: int


@dataclass(frozen=True, slots=True)
class CompiledGlossaryRule:
    term_id: str
    glossary_id: str
    revision: int
    source_term: str
    normalized_source_term: str
    rule_type: GlossaryRuleType
    target_term: str | None
    scope: GlossaryScope
    scope_reference_id: str | None
    priority: int
    case_sensitive: bool
    whole_word: bool
    match_mode: GlossaryMatchMode
    capitalization_policy: str
    inflection_policy: str
    first_use_policy: str


@dataclass(frozen=True, slots=True)
class CompiledGlossarySnapshot:
    project_id: str
    document_id: str | None
    source_versions: tuple[GlossarySourceVersion, ...]
    rules: tuple[CompiledGlossaryRule, ...]


@dataclass(frozen=True, slots=True)
class GlossarySnapshotRecord:
    id: str
    project_id: str
    document_id: str | None
    version: int
    checksum_sha256: str
    term_count: int
    source_versions: tuple[GlossarySourceVersion, ...]
    snapshot_file_id: str
    created_at: str
    compiled: CompiledGlossarySnapshot


def create_glossary_snapshot(
    *,
    session: Session,
    storage: LocalFileStorage,
    project_id: str,
    document_id: str | None = None,
    created_at: datetime | None = None,
) -> GlossarySnapshotRecord:
    _validate_context(session, project_id, document_id)
    compiled = _compile_active_rules(session, project_id, document_id)
    payload = canonical_glossary_snapshot_json(compiled)
    checksum = hashlib.sha256(payload).hexdigest()

    existing = session.scalars(
        select(GlossarySnapshot)
        .where(
            GlossarySnapshot.project_id == project_id,
            GlossarySnapshot.checksum_sha256 == checksum,
        )
        .order_by(GlossarySnapshot.version)
    ).first()
    if existing is not None:
        record = _load_snapshot_row(existing, session=session, storage=storage)
        if record.compiled != compiled:
            raise GlossarySnapshotIntegrityError(
                "The stored glossary snapshot checksum identifies different content."
            )
        return record

    latest_version = session.scalar(
        select(func.max(GlossarySnapshot.version)).where(GlossarySnapshot.project_id == project_id)
    )
    version = (latest_version or 0) + 1
    snapshot_id = _snapshot_id(project_id, version, checksum)
    file_id = _snapshot_file_id(snapshot_id)
    safe_filename = _snapshot_filename(version, checksum)
    storage_key = f"projects/{project_id}/glossary/snapshots/{safe_filename}"
    created_at_text = _timestamp(created_at)
    source_versions_json = _source_versions_json(compiled.source_versions)
    metadata: dict[str, object] = {
        "artifact_type": _ARTIFACT_TYPE,
        "snapshot_id": snapshot_id,
        "snapshot_version": version,
    }

    try:
        temporary = storage.write_temporary(BytesIO(payload))
    except LocalFileStorageError as exc:
        raise GlossarySnapshotStorageError("The glossary snapshot could not be staged.") from exc
    if temporary.checksum_sha256 != checksum or temporary.size_bytes != len(payload):
        temporary.path.unlink(missing_ok=True)
        raise GlossarySnapshotStorageError(
            "The staged glossary snapshot does not match its canonical content."
        )
    try:
        artifact = storage.commit(temporary, storage_key, immutable=True)
    except StoredFileExistsError as exc:
        raise GlossarySnapshotVersionConflictError(
            "The glossary snapshot destination already exists."
        ) from exc
    except LocalFileStorageError as exc:
        raise GlossarySnapshotStorageError(
            "The glossary snapshot could not be stored safely."
        ) from exc

    files = StoredFilesRepository(session)
    try:
        files.create(
            file_id=file_id,
            project_id=project_id,
            document_id=document_id,
            file_role=FileRole.IR_SNAPSHOT,
            storage_key=artifact.storage_key,
            original_filename=None,
            safe_filename=safe_filename,
            mime_type="application/json",
            size_bytes=artifact.size_bytes,
            checksum_sha256=artifact.checksum_sha256,
            is_immutable=True,
            status=FileStatus.AVAILABLE,
            metadata=metadata,
            created_at=created_at_text,
        )
        row = GlossarySnapshot(
            id=snapshot_id,
            project_id=project_id,
            document_id=document_id,
            version=version,
            checksum_sha256=checksum,
            term_count=len(compiled.rules),
            source_versions_json=source_versions_json,
            snapshot_file_id=file_id,
            created_at=created_at_text,
        )
        session.add(row)
        session.flush()
    except (StoredFileAlreadyExistsError, StoredFileStorageKeyExistsError, IntegrityError) as exc:
        raise GlossarySnapshotVersionConflictError(
            "The glossary snapshot version could not be recorded uniquely."
        ) from exc

    return _record(row, compiled)


def load_glossary_snapshot(
    snapshot_id: str,
    *,
    session: Session,
    storage: LocalFileStorage,
) -> GlossarySnapshotRecord:
    _validate_prefixed_id(snapshot_id, "gsn_")
    row = session.get(GlossarySnapshot, snapshot_id)
    if row is None:
        raise GlossarySnapshotNotFoundError("The glossary snapshot was not found.")
    return _load_snapshot_row(row, session=session, storage=storage)


def canonical_glossary_snapshot_json(snapshot: CompiledGlossarySnapshot) -> bytes:
    if not isinstance(snapshot, CompiledGlossarySnapshot):
        raise TypeError("A compiled glossary snapshot is required.")
    payload = {
        "document_id": snapshot.document_id,
        "project_id": snapshot.project_id,
        "rules": [_rule_payload(rule) for rule in snapshot.rules],
        "schema_version": _SCHEMA_VERSION,
        "source_versions": [
            {"glossary_id": source.glossary_id, "version": source.version}
            for source in snapshot.source_versions
        ],
    }
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise GlossarySnapshotIntegrityError(
            "The glossary snapshot cannot be serialized canonically."
        ) from exc


def _compile_active_rules(
    session: Session,
    project_id: str,
    document_id: str | None,
) -> CompiledGlossarySnapshot:
    glossaries = tuple(
        session.scalars(
            select(Glossary)
            .where(
                Glossary.deleted_at.is_(None),
                Glossary.status == _ACTIVE,
                or_(Glossary.project_id == project_id, Glossary.project_id.is_(None)),
            )
            .order_by(Glossary.id)
        )
    )
    source_versions = tuple(
        GlossarySourceVersion(glossary_id=row.id, version=row.version) for row in glossaries
    )
    glossary_ids = tuple(source.glossary_id for source in source_versions)
    if not glossary_ids:
        return CompiledGlossarySnapshot(
            project_id=project_id,
            document_id=document_id,
            source_versions=(),
            rules=(),
        )

    revision_numbers = (
        select(
            GlossaryRevision.term_id.label("term_id"),
            func.max(GlossaryRevision.revision_number).label("revision"),
        )
        .group_by(GlossaryRevision.term_id)
        .subquery()
    )
    rows = session.execute(
        select(GlossaryTerm, revision_numbers.c.revision)
        .outerjoin(revision_numbers, revision_numbers.c.term_id == GlossaryTerm.id)
        .where(
            GlossaryTerm.glossary_id.in_(glossary_ids),
            GlossaryTerm.status == _ACTIVE,
        )
    )
    rules = tuple(
        sorted((_compiled_rule(term, revision) for term, revision in rows), key=_rule_order)
    )
    return CompiledGlossarySnapshot(
        project_id=project_id,
        document_id=document_id,
        source_versions=source_versions,
        rules=rules,
    )


def _compiled_rule(term: GlossaryTerm, revision: object) -> CompiledGlossaryRule:
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise GlossarySnapshotIntegrityError(
            "An active glossary rule has no valid source revision."
        )
    try:
        return CompiledGlossaryRule(
            term_id=term.id,
            glossary_id=term.glossary_id,
            revision=revision,
            source_term=term.source_term,
            normalized_source_term=term.normalized_source_term,
            rule_type=GlossaryRuleType(term.rule_type),
            target_term=term.target_term,
            scope=GlossaryScope(term.scope),
            scope_reference_id=term.scope_reference_id,
            priority=term.priority,
            case_sensitive=_database_bool(term.case_sensitive),
            whole_word=_database_bool(term.whole_word),
            match_mode=GlossaryMatchMode(term.match_mode),
            capitalization_policy=term.capitalization_policy,
            inflection_policy=term.inflection_policy,
            first_use_policy=term.first_use_policy,
        )
    except (TypeError, ValueError):
        raise GlossarySnapshotIntegrityError(
            "An active glossary rule contains invalid persisted data."
        ) from None


def _load_snapshot_row(
    row: GlossarySnapshot,
    *,
    session: Session,
    storage: LocalFileStorage,
) -> GlossarySnapshotRecord:
    try:
        file_record = StoredFilesRepository(session).get(row.snapshot_file_id)
    except StoredFileNotFoundError as exc:
        raise GlossarySnapshotIntegrityError(
            "The glossary snapshot file record is missing."
        ) from exc
    _validate_file_record(row, file_record)
    try:
        stored_checksum = storage.checksum(file_record.storage_key)
        with storage.open_read(file_record.storage_key) as source:
            payload = source.read()
    except LocalFileStorageError as exc:
        raise GlossarySnapshotIntegrityError("The glossary snapshot file is unavailable.") from exc
    if (
        not isinstance(payload, bytes)
        or len(payload) != file_record.size_bytes
        or stored_checksum != row.checksum_sha256
        or file_record.checksum_sha256 != row.checksum_sha256
        or hashlib.sha256(payload).hexdigest() != row.checksum_sha256
    ):
        raise GlossarySnapshotIntegrityError(
            "The glossary snapshot checksum does not match its records."
        )
    compiled = _parse_compiled_snapshot(payload)
    if (
        compiled.project_id != row.project_id
        or compiled.document_id != row.document_id
        or len(compiled.rules) != row.term_count
        or _source_versions_json(compiled.source_versions) != row.source_versions_json
        or canonical_glossary_snapshot_json(compiled) != payload
    ):
        raise GlossarySnapshotIntegrityError(
            "The glossary snapshot content does not match its database record."
        )
    return _record(row, compiled)


def _parse_compiled_snapshot(payload: bytes) -> CompiledGlossarySnapshot:
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or set(raw) != {
            "document_id",
            "project_id",
            "rules",
            "schema_version",
            "source_versions",
        }:
            raise ValueError
        if raw["schema_version"] != _SCHEMA_VERSION:
            raise ValueError
        project_id = raw["project_id"]
        document_id = raw["document_id"]
        _validate_prefixed_id(project_id, "prj_")
        if document_id is not None:
            _validate_prefixed_id(document_id, "doc_")
        source_versions = tuple(_parse_source_version(value) for value in raw["source_versions"])
        rules = tuple(_parse_rule(value) for value in raw["rules"])
        if source_versions != tuple(sorted(source_versions)):
            raise ValueError
        if rules != tuple(sorted(rules, key=_rule_order)):
            raise ValueError
        if len({source.glossary_id for source in source_versions}) != len(source_versions):
            raise ValueError
        if len({rule.term_id for rule in rules}) != len(rules):
            raise ValueError
        if not {rule.glossary_id for rule in rules} <= {
            source.glossary_id for source in source_versions
        }:
            raise ValueError
        return CompiledGlossarySnapshot(
            project_id=project_id,
            document_id=document_id,
            source_versions=source_versions,
            rules=rules,
        )
    except (
        InvalidGlossarySnapshotRequestError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        raise GlossarySnapshotIntegrityError("The glossary snapshot JSON is invalid.") from None


def _parse_source_version(value: object) -> GlossarySourceVersion:
    if not isinstance(value, dict) or set(value) != {"glossary_id", "version"}:
        raise ValueError
    glossary_id = value["glossary_id"]
    version = value["version"]
    _validate_prefixed_id(glossary_id, "gls_")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError
    return GlossarySourceVersion(glossary_id=glossary_id, version=version)


def _parse_rule(value: object) -> CompiledGlossaryRule:
    expected = {
        "capitalization_policy",
        "case_sensitive",
        "first_use_policy",
        "glossary_id",
        "inflection_policy",
        "match_mode",
        "normalized_source_term",
        "priority",
        "revision",
        "rule_type",
        "scope",
        "scope_reference_id",
        "source_term",
        "target_term",
        "term_id",
        "whole_word",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError
    _validate_prefixed_id(value["term_id"], "trm_")
    _validate_prefixed_id(value["glossary_id"], "gls_")
    for key in (
        "source_term",
        "normalized_source_term",
        "capitalization_policy",
        "inflection_policy",
        "first_use_policy",
    ):
        _validate_text(value[key])
    target_term = value["target_term"]
    if target_term is not None:
        _validate_text(target_term)
    scope_reference_id = value["scope_reference_id"]
    if scope_reference_id is not None:
        _validate_text(scope_reference_id)
    revision = value["revision"]
    priority = value["priority"]
    if any(
        isinstance(number, bool) or not isinstance(number, int) or number < minimum
        for number, minimum in ((revision, 1), (priority, 0))
    ):
        raise ValueError
    if not isinstance(value["case_sensitive"], bool) or not isinstance(value["whole_word"], bool):
        raise ValueError
    rule_type = GlossaryRuleType(value["rule_type"])
    if rule_type is GlossaryRuleType.TRANSLATE_AS and target_term is None:
        raise ValueError
    return CompiledGlossaryRule(
        term_id=value["term_id"],
        glossary_id=value["glossary_id"],
        revision=revision,
        source_term=value["source_term"],
        normalized_source_term=value["normalized_source_term"],
        rule_type=rule_type,
        target_term=target_term,
        scope=GlossaryScope(value["scope"]),
        scope_reference_id=scope_reference_id,
        priority=priority,
        case_sensitive=value["case_sensitive"],
        whole_word=value["whole_word"],
        match_mode=GlossaryMatchMode(value["match_mode"]),
        capitalization_policy=value["capitalization_policy"],
        inflection_policy=value["inflection_policy"],
        first_use_policy=value["first_use_policy"],
    )


def _validate_file_record(row: GlossarySnapshot, record: StoredFileRecord) -> None:
    safe_filename = _snapshot_filename(row.version, row.checksum_sha256)
    expected_storage_key = f"projects/{row.project_id}/glossary/snapshots/{safe_filename}"
    expected_metadata = {
        "artifact_type": _ARTIFACT_TYPE,
        "snapshot_id": row.id,
        "snapshot_version": row.version,
    }
    if (
        row.id != _snapshot_id(row.project_id, row.version, row.checksum_sha256)
        or record.id != _snapshot_file_id(row.id)
        or record.project_id != row.project_id
        or record.document_id != row.document_id
        or record.file_role is not FileRole.IR_SNAPSHOT
        or record.storage_key != expected_storage_key
        or record.original_filename is not None
        or record.safe_filename != safe_filename
        or record.mime_type != "application/json"
        or not record.is_immutable
        or record.status is not FileStatus.AVAILABLE
        or record.metadata != expected_metadata
    ):
        raise GlossarySnapshotIntegrityError("The glossary snapshot file record is invalid.")


def _record(
    row: GlossarySnapshot,
    compiled: CompiledGlossarySnapshot,
) -> GlossarySnapshotRecord:
    return GlossarySnapshotRecord(
        id=row.id,
        project_id=row.project_id,
        document_id=row.document_id,
        version=row.version,
        checksum_sha256=row.checksum_sha256,
        term_count=row.term_count,
        source_versions=compiled.source_versions,
        snapshot_file_id=row.snapshot_file_id,
        created_at=row.created_at,
        compiled=compiled,
    )


def _rule_payload(rule: CompiledGlossaryRule) -> dict[str, object]:
    return {
        "capitalization_policy": rule.capitalization_policy,
        "case_sensitive": rule.case_sensitive,
        "first_use_policy": rule.first_use_policy,
        "glossary_id": rule.glossary_id,
        "inflection_policy": rule.inflection_policy,
        "match_mode": rule.match_mode.value,
        "normalized_source_term": rule.normalized_source_term,
        "priority": rule.priority,
        "revision": rule.revision,
        "rule_type": rule.rule_type.value,
        "scope": rule.scope.value,
        "scope_reference_id": rule.scope_reference_id,
        "source_term": rule.source_term,
        "target_term": rule.target_term,
        "term_id": rule.term_id,
        "whole_word": rule.whole_word,
    }


def _rule_order(rule: CompiledGlossaryRule) -> tuple[object, ...]:
    return (
        -scope_priority(rule.scope),
        -rule.priority,
        rule.normalized_source_term,
        rule.source_term,
        rule.glossary_id,
        rule.term_id,
    )


def _source_versions_json(source_versions: tuple[GlossarySourceVersion, ...]) -> str:
    return json.dumps(
        {source.glossary_id: source.version for source in source_versions},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_context(session: Session, project_id: str, document_id: str | None) -> None:
    _validate_prefixed_id(project_id, "prj_")
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise InvalidGlossarySnapshotRequestError("The glossary snapshot project is unavailable.")
    if document_id is None:
        return
    _validate_prefixed_id(document_id, "doc_")
    document = session.get(Document, document_id)
    if document is None or document.project_id != project_id:
        raise InvalidGlossarySnapshotRequestError(
            "The glossary snapshot document is unavailable for this project."
        )


def _validate_prefixed_id(value: object, prefix: str) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise InvalidGlossarySnapshotRequestError("A glossary snapshot identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (AttributeError, ValueError):
        raise InvalidGlossarySnapshotRequestError(
            "A glossary snapshot identifier is invalid."
        ) from None
    if value != f"{prefix}{parsed}":
        raise InvalidGlossarySnapshotRequestError("A glossary snapshot identifier is invalid.")


def _validate_text(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or not value.isprintable()
    ):
        raise ValueError


def _database_bool(value: int) -> bool:
    if value not in (0, 1):
        raise ValueError
    return bool(value)


def _snapshot_id(project_id: str, version: int, checksum: str) -> str:
    return f"gsn_{uuid5(NAMESPACE_URL, f'transloka:glossary:{project_id}:{version}:{checksum}')}"


def _snapshot_file_id(snapshot_id: str) -> str:
    return f"fil_{uuid5(NAMESPACE_URL, f'transloka:glossary-file:{snapshot_id}')}"


def _snapshot_filename(version: int, checksum: str) -> str:
    return f"glossary-snapshot-v{version:06d}-{checksum[:12]}.json"


def _timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value
    if timestamp.tzinfo is None:
        raise InvalidGlossarySnapshotRequestError(
            "The glossary snapshot timestamp must include a timezone."
        )
    return timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
