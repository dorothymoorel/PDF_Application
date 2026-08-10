from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class GlossaryScope(StrEnum):
    SYSTEM = "SYSTEM"
    DOMAIN = "DOMAIN"
    USER = "USER"
    PROJECT = "PROJECT"
    DOCUMENT = "DOCUMENT"
    SECTION = "SECTION"
    PAGE = "PAGE"
    SEGMENT = "SEGMENT"


class GlossaryRuleType(StrEnum):
    KEEP_ORIGINAL = "KEEP_ORIGINAL"
    TRANSLATE_AS = "TRANSLATE_AS"
    ORIGINAL_THEN_TRANSLATION = "ORIGINAL_THEN_TRANSLATION"
    TRANSLATION_THEN_ORIGINAL = "TRANSLATION_THEN_ORIGINAL"
    PRESERVE_ABBREVIATION = "PRESERVE_ABBREVIATION"
    IGNORE = "IGNORE"


class GlossaryMatchMode(StrEnum):
    EXACT = "EXACT"
    PHRASE = "PHRASE"


class GlossaryRevisionType(StrEnum):
    CREATE_TERM = "CREATE_TERM"
    EDIT_TERM = "EDIT_TERM"
    DEACTIVATE = "DEACTIVATE"
    REACTIVATE = "REACTIVATE"
    CHANGE_TARGET = "CHANGE_TARGET"
    CHANGE_SCOPE = "CHANGE_SCOPE"
    CHANGE_PRIORITY = "CHANGE_PRIORITY"
    CHANGE_MATCHING_MODE = "CHANGE_MATCHING_MODE"
    RESOLVE_CONFLICT = "RESOLVE_CONFLICT"


class ProtectedItemType(StrEnum):
    TERM = "TERM"
    URL = "URL"
    EMAIL = "EMAIL"
    CODE = "CODE"
    ENDPOINT = "ENDPOINT"
    FILE_PATH = "FILE_PATH"
    CITATION = "CITATION"
    ACRONYM = "ACRONYM"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


def _prefixed_uuid(prefix: str, table_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


class Glossary(Base):
    __tablename__ = "glossaries"
    __table_args__ = (
        _prefixed_uuid("gls_", "glossaries"),
        CheckConstraint(
            "trim(name) <> '' AND trim(source_language) <> '' AND trim(target_language) <> ''",
            name="ck_glossaries_required_text",
        ),
        CheckConstraint(
            f"scope IN ({_sql_values(GlossaryScope)})",
            name="ck_glossaries_scope",
        ),
        CheckConstraint("trim(status) <> ''", name="ck_glossaries_status"),
        CheckConstraint("version >= 1", name="ck_glossaries_version"),
        CheckConstraint("is_default IN (0, 1)", name="ck_glossaries_is_default"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_language: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    __table_args__ = (
        _prefixed_uuid("trm_", "glossary_terms"),
        CheckConstraint(
            "trim(source_term) <> '' AND trim(normalized_source_term) <> ''",
            name="ck_glossary_terms_source",
        ),
        CheckConstraint(
            f"rule_type IN ({_sql_values(GlossaryRuleType)})",
            name="ck_glossary_terms_rule_type",
        ),
        CheckConstraint(
            "target_term IS NULL OR trim(target_term) <> ''",
            name="ck_glossary_terms_target_text",
        ),
        CheckConstraint(
            "rule_type <> 'TRANSLATE_AS' OR target_term IS NOT NULL",
            name="ck_glossary_terms_translate_as_target",
        ),
        CheckConstraint(
            f"scope IN ({_sql_values(GlossaryScope)})",
            name="ck_glossary_terms_scope",
        ),
        CheckConstraint("priority >= 0", name="ck_glossary_terms_priority"),
        CheckConstraint("case_sensitive IN (0, 1)", name="ck_glossary_terms_case_sensitive"),
        CheckConstraint("whole_word IN (0, 1)", name="ck_glossary_terms_whole_word"),
        CheckConstraint(
            f"match_mode IN ({_sql_values(GlossaryMatchMode)})",
            name="ck_glossary_terms_match_mode",
        ),
        CheckConstraint(
            "trim(capitalization_policy) <> '' AND trim(inflection_policy) <> '' "
            "AND trim(first_use_policy) <> '' AND trim(status) <> '' "
            "AND trim(term_source) <> ''",
            name="ck_glossary_terms_policies",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_glossary_terms_confidence",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    glossary_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("glossaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_source_term: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_reference_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    case_sensitive: Mapped[int] = mapped_column(Integer, nullable=False)
    whole_word: Mapped[int] = mapped_column(Integer, nullable=False)
    match_mode: Mapped[str] = mapped_column(Text, nullable=False)
    capitalization_policy: Mapped[str] = mapped_column(Text, nullable=False)
    inflection_policy: Mapped[str] = mapped_column(Text, nullable=False)
    first_use_policy: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    term_source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_glossary_terms_normalized", GlossaryTerm.normalized_source_term)
Index(
    "ix_glossary_terms_active",
    GlossaryTerm.glossary_id,
    GlossaryTerm.status,
    GlossaryTerm.priority.desc(),
)
Index(
    "uq_glossary_terms_identity",
    GlossaryTerm.glossary_id,
    GlossaryTerm.normalized_source_term,
    GlossaryTerm.scope,
    func.coalesce(GlossaryTerm.scope_reference_id, ""),
    unique=True,
    sqlite_where=GlossaryTerm.status.not_in(("ARCHIVED", "REJECTED")),
)


class GlossaryRevision(Base):
    __tablename__ = "glossary_revisions"
    __table_args__ = (
        _prefixed_uuid("grv_", "glossary_revisions"),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_glossary_revisions_number",
        ),
        CheckConstraint(
            f"revision_type IN ({_sql_values(GlossaryRevisionType)})",
            name="ck_glossary_revisions_type",
        ),
        CheckConstraint(
            "previous_value_json IS NULL OR json_valid(previous_value_json)",
            name="ck_glossary_revisions_previous_json_valid",
        ),
        CheckConstraint(
            "json_valid(new_value_json)",
            name="ck_glossary_revisions_new_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    term_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("glossary_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_type: Mapped[str] = mapped_column(Text, nullable=False)
    previous_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_glossary_revisions_number",
    GlossaryRevision.term_id,
    GlossaryRevision.revision_number,
    unique=True,
)


class GlossarySnapshot(Base):
    __tablename__ = "glossary_snapshots"
    __table_args__ = (
        _prefixed_uuid("gsn_", "glossary_snapshots"),
        CheckConstraint("version >= 1", name="ck_glossary_snapshots_version"),
        CheckConstraint(
            "length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_glossary_snapshots_checksum",
        ),
        CheckConstraint("term_count >= 0", name="ck_glossary_snapshots_term_count"),
        CheckConstraint(
            "json_valid(source_versions_json)",
            name="ck_glossary_snapshots_source_versions_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    term_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_versions_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_file_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("stored_files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_glossary_snapshots_version",
    GlossarySnapshot.project_id,
    GlossarySnapshot.version,
    unique=True,
)
Index("ix_glossary_snapshots_checksum", GlossarySnapshot.checksum_sha256)


class TermCandidate(Base):
    __tablename__ = "term_candidates"
    __table_args__ = (
        _prefixed_uuid("tcd_", "term_candidates"),
        CheckConstraint(
            "trim(source_term) <> '' AND trim(normalized_source_term) <> ''",
            name="ck_term_candidates_source",
        ),
        CheckConstraint(
            "trim(candidate_type) <> '' AND trim(recommended_rule_type) <> '' "
            "AND trim(status) <> ''",
            name="ck_term_candidates_classification",
        ),
        CheckConstraint(
            f"recommended_rule_type IN ({_sql_values(GlossaryRuleType)})",
            name="ck_term_candidates_rule_type",
        ),
        CheckConstraint(
            "recommended_target_term IS NULL OR trim(recommended_target_term) <> ''",
            name="ck_term_candidates_target_text",
        ),
        CheckConstraint(
            "occurrence_count >= 0",
            name="ck_term_candidates_occurrence_count",
        ),
        CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name="ck_term_candidates_confidence",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_source_term: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_type: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_target_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(REAL, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_term_candidates_project_term",
    TermCandidate.project_id,
    TermCandidate.normalized_source_term,
    unique=True,
)


class TermOccurrence(Base):
    __tablename__ = "term_occurrences"
    __table_args__ = (
        _prefixed_uuid("occ_", "term_occurrences"),
        CheckConstraint("start_offset >= 0", name="ck_term_occurrences_start_offset"),
        CheckConstraint(
            "end_offset > start_offset",
            name="ck_term_occurrences_end_offset",
        ),
        CheckConstraint(
            "term_id IS NOT NULL OR candidate_id IS NOT NULL",
            name="ck_term_occurrences_reference",
        ),
        CheckConstraint("trim(matched_text) <> ''", name="ck_term_occurrences_matched_text"),
        CheckConstraint("trim(match_method) <> ''", name="ck_term_occurrences_match_method"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_term_occurrences_confidence",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    term_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("glossary_terms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    candidate_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("term_candidates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    segment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_text: Mapped[str] = mapped_column(Text, nullable=False)
    match_method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index("ix_term_occurrences_term", TermOccurrence.term_id)
Index("ix_term_occurrences_candidate", TermOccurrence.candidate_id)
Index("ix_term_occurrences_segment", TermOccurrence.segment_id)


class GlossaryConflict(Base):
    __tablename__ = "glossary_conflicts"
    __table_args__ = (
        _prefixed_uuid("gcf_", "glossary_conflicts"),
        CheckConstraint(
            "trim(source_term) <> '' AND trim(conflict_type) <> '' AND trim(status) <> ''",
            name="ck_glossary_conflicts_required_text",
        ),
        CheckConstraint("json_valid(rules_json)", name="ck_glossary_conflicts_rules_json_valid"),
        CheckConstraint(
            "resolution_json IS NULL OR json_valid(resolution_json)",
            name="ck_glossary_conflicts_resolution_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_term: Mapped[str] = mapped_column(Text, nullable=False)
    conflict_type: Mapped[str] = mapped_column(Text, nullable=False)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_glossary_conflicts_project_status", GlossaryConflict.project_id, GlossaryConflict.status)


class ProtectedItem(Base):
    __tablename__ = "protected_items"
    __table_args__ = (
        _prefixed_uuid("pit_", "protected_items"),
        CheckConstraint(
            f"item_type IN ({_sql_values(ProtectedItemType)})",
            name="ck_protected_items_type",
        ),
        CheckConstraint(
            "trim(placeholder) <> '' AND trim(source_value) <> '' "
            "AND trim(replacement_value) <> ''",
            name="ck_protected_items_values",
        ),
        CheckConstraint(
            f"rule_type IN ({_sql_values(GlossaryRuleType)})",
            name="ck_protected_items_rule_type",
        ),
        CheckConstraint("start_offset >= 0", name="ck_protected_items_start_offset"),
        CheckConstraint("end_offset > start_offset", name="ck_protected_items_end_offset"),
        CheckConstraint(
            "trim(capitalization_policy) <> '' AND trim(status) <> ''",
            name="ck_protected_items_policy_status",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("document_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    glossary_term_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("glossary_terms.id", ondelete="RESTRICT"),
        nullable=True,
    )
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    placeholder: Mapped[str] = mapped_column(Text, nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_value: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    capitalization_policy: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    restored_at: Mapped[str | None] = mapped_column(Text, nullable=True)


Index(
    "uq_protected_items_placeholder",
    ProtectedItem.segment_id,
    ProtectedItem.placeholder,
    unique=True,
)
