"""Create glossary and protected-content persistence tables.

Revision ID: 0009_glossary
Revises: 0008_document_ir_structure
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_glossary"
down_revision: str | Sequence[str] | None = "0008_document_ir_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPES = ("SYSTEM", "DOMAIN", "USER", "PROJECT", "DOCUMENT", "SECTION", "PAGE", "SEGMENT")
_RULE_TYPES = (
    "KEEP_ORIGINAL",
    "TRANSLATE_AS",
    "ORIGINAL_THEN_TRANSLATION",
    "TRANSLATION_THEN_ORIGINAL",
    "PRESERVE_ABBREVIATION",
    "IGNORE",
)
_MATCH_MODES = ("EXACT", "PHRASE")
_REVISION_TYPES = (
    "CREATE_TERM",
    "EDIT_TERM",
    "DEACTIVATE",
    "REACTIVATE",
    "CHANGE_TARGET",
    "CHANGE_SCOPE",
    "CHANGE_PRIORITY",
    "CHANGE_MATCHING_MODE",
    "RESOLVE_CONFLICT",
)
_PROTECTED_ITEM_TYPES = (
    "TERM",
    "URL",
    "EMAIL",
    "CODE",
    "ENDPOINT",
    "FILE_PATH",
    "CITATION",
    "ACRONYM",
)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _prefixed_uuid(prefix: str, table_name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


def upgrade() -> None:
    op.create_table(
        "glossaries",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_language", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        _prefixed_uuid("gls_", "glossaries"),
        sa.CheckConstraint(
            "trim(name) <> '' AND trim(source_language) <> '' AND trim(target_language) <> ''",
            name="ck_glossaries_required_text",
        ),
        sa.CheckConstraint(
            f"scope IN ({_values(_SCOPES)})",
            name="ck_glossaries_scope",
        ),
        sa.CheckConstraint("trim(status) <> ''", name="ck_glossaries_status"),
        sa.CheckConstraint("version >= 1", name="ck_glossaries_version"),
        sa.CheckConstraint("is_default IN (0, 1)", name="ck_glossaries_is_default"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_glossaries_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )

    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("glossary_id", sa.Text(), nullable=False),
        sa.Column("source_term", sa.Text(), nullable=False),
        sa.Column("normalized_source_term", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.Text(), nullable=False),
        sa.Column("target_term", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_reference_id", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("case_sensitive", sa.Integer(), nullable=False),
        sa.Column("whole_word", sa.Integer(), nullable=False),
        sa.Column("match_mode", sa.Text(), nullable=False),
        sa.Column("capitalization_policy", sa.Text(), nullable=False),
        sa.Column("inflection_policy", sa.Text(), nullable=False),
        sa.Column("first_use_policy", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("term_source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("trm_", "glossary_terms"),
        sa.CheckConstraint(
            "trim(source_term) <> '' AND trim(normalized_source_term) <> ''",
            name="ck_glossary_terms_source",
        ),
        sa.CheckConstraint(
            f"rule_type IN ({_values(_RULE_TYPES)})",
            name="ck_glossary_terms_rule_type",
        ),
        sa.CheckConstraint(
            "target_term IS NULL OR trim(target_term) <> ''",
            name="ck_glossary_terms_target_text",
        ),
        sa.CheckConstraint(
            "rule_type <> 'TRANSLATE_AS' OR target_term IS NOT NULL",
            name="ck_glossary_terms_translate_as_target",
        ),
        sa.CheckConstraint(
            f"scope IN ({_values(_SCOPES)})",
            name="ck_glossary_terms_scope",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_glossary_terms_priority"),
        sa.CheckConstraint(
            "case_sensitive IN (0, 1)",
            name="ck_glossary_terms_case_sensitive",
        ),
        sa.CheckConstraint("whole_word IN (0, 1)", name="ck_glossary_terms_whole_word"),
        sa.CheckConstraint(
            f"match_mode IN ({_values(_MATCH_MODES)})",
            name="ck_glossary_terms_match_mode",
        ),
        sa.CheckConstraint(
            "trim(capitalization_policy) <> '' AND trim(inflection_policy) <> '' "
            "AND trim(first_use_policy) <> '' AND trim(status) <> '' "
            "AND trim(term_source) <> ''",
            name="ck_glossary_terms_policies",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_glossary_terms_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["glossary_id"],
            ["glossaries.id"],
            name="fk_glossary_terms_glossary_id_glossaries",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "ix_glossary_terms_normalized",
        "glossary_terms",
        ["normalized_source_term"],
    )
    op.execute(
        "CREATE INDEX ix_glossary_terms_active "
        "ON glossary_terms(glossary_id, status, priority DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_glossary_terms_identity "
        "ON glossary_terms(glossary_id, normalized_source_term, scope, "
        "COALESCE(scope_reference_id, '')) "
        "WHERE status NOT IN ('ARCHIVED', 'REJECTED')"
    )

    op.create_table(
        "glossary_revisions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("term_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_type", sa.Text(), nullable=False),
        sa.Column("previous_value_json", sa.Text(), nullable=True),
        sa.Column("new_value_json", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        _prefixed_uuid("grv_", "glossary_revisions"),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_glossary_revisions_number",
        ),
        sa.CheckConstraint(
            f"revision_type IN ({_values(_REVISION_TYPES)})",
            name="ck_glossary_revisions_type",
        ),
        sa.CheckConstraint(
            "previous_value_json IS NULL OR json_valid(previous_value_json)",
            name="ck_glossary_revisions_previous_json_valid",
        ),
        sa.CheckConstraint(
            "json_valid(new_value_json)",
            name="ck_glossary_revisions_new_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["glossary_terms.id"],
            name="fk_glossary_revisions_term_id_glossary_terms",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_glossary_revisions_number",
        "glossary_revisions",
        ["term_id", "revision_number"],
        unique=True,
    )
    op.execute(
        "CREATE TRIGGER trg_glossary_revisions_no_update "
        "BEFORE UPDATE ON glossary_revisions "
        "BEGIN SELECT RAISE(ABORT, 'glossary revisions are append-only'); END"
    )

    op.create_table(
        "glossary_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("term_count", sa.Integer(), nullable=False),
        sa.Column("source_versions_json", sa.Text(), nullable=False),
        sa.Column("snapshot_file_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        _prefixed_uuid("gsn_", "glossary_snapshots"),
        sa.CheckConstraint("version >= 1", name="ck_glossary_snapshots_version"),
        sa.CheckConstraint(
            "length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_glossary_snapshots_checksum",
        ),
        sa.CheckConstraint("term_count >= 0", name="ck_glossary_snapshots_term_count"),
        sa.CheckConstraint(
            "json_valid(source_versions_json)",
            name="ck_glossary_snapshots_source_versions_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_glossary_snapshots_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_glossary_snapshots_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_file_id"],
            ["stored_files.id"],
            name="fk_glossary_snapshots_snapshot_file_id_stored_files",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_glossary_snapshots_version",
        "glossary_snapshots",
        ["project_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_glossary_snapshots_checksum",
        "glossary_snapshots",
        ["checksum_sha256"],
    )
    op.execute(
        "CREATE TRIGGER trg_glossary_snapshots_no_update "
        "BEFORE UPDATE ON glossary_snapshots "
        "BEGIN SELECT RAISE(ABORT, 'glossary snapshots are immutable'); END"
    )

    op.create_table(
        "term_candidates",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("source_term", sa.Text(), nullable=False),
        sa.Column("normalized_source_term", sa.Text(), nullable=False),
        sa.Column("candidate_type", sa.Text(), nullable=False),
        sa.Column("recommended_rule_type", sa.Text(), nullable=False),
        sa.Column("recommended_target_term", sa.Text(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        _prefixed_uuid("tcd_", "term_candidates"),
        sa.CheckConstraint(
            "trim(source_term) <> '' AND trim(normalized_source_term) <> ''",
            name="ck_term_candidates_source",
        ),
        sa.CheckConstraint(
            "trim(candidate_type) <> '' AND trim(recommended_rule_type) <> '' "
            "AND trim(status) <> ''",
            name="ck_term_candidates_classification",
        ),
        sa.CheckConstraint(
            f"recommended_rule_type IN ({_values(_RULE_TYPES)})",
            name="ck_term_candidates_rule_type",
        ),
        sa.CheckConstraint(
            "recommended_target_term IS NULL OR trim(recommended_target_term) <> ''",
            name="ck_term_candidates_target_text",
        ),
        sa.CheckConstraint(
            "occurrence_count >= 0",
            name="ck_term_candidates_occurrence_count",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0",
            name="ck_term_candidates_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_term_candidates_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_term_candidates_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_term_candidates_project_term",
        "term_candidates",
        ["project_id", "normalized_source_term"],
        unique=True,
    )

    op.create_table(
        "term_occurrences",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("term_id", sa.Text(), nullable=True),
        sa.Column("candidate_id", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("page_id", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("matched_text", sa.Text(), nullable=False),
        sa.Column("match_method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        _prefixed_uuid("occ_", "term_occurrences"),
        sa.CheckConstraint(
            "start_offset >= 0",
            name="ck_term_occurrences_start_offset",
        ),
        sa.CheckConstraint(
            "end_offset > start_offset",
            name="ck_term_occurrences_end_offset",
        ),
        sa.CheckConstraint(
            "term_id IS NOT NULL OR candidate_id IS NOT NULL",
            name="ck_term_occurrences_reference",
        ),
        sa.CheckConstraint(
            "trim(matched_text) <> ''",
            name="ck_term_occurrences_matched_text",
        ),
        sa.CheckConstraint(
            "trim(match_method) <> ''",
            name="ck_term_occurrences_match_method",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0",
            name="ck_term_occurrences_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_term_occurrences_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_term_occurrences_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["glossary_terms.id"],
            name="fk_term_occurrences_term_id_glossary_terms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["term_candidates.id"],
            name="fk_term_occurrences_candidate_id_term_candidates",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["document_segments.id"],
            name="fk_term_occurrences_segment_id_document_segments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_term_occurrences_page_id_document_pages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index("ix_term_occurrences_term", "term_occurrences", ["term_id"])
    op.create_index("ix_term_occurrences_candidate", "term_occurrences", ["candidate_id"])
    op.create_index("ix_term_occurrences_segment", "term_occurrences", ["segment_id"])

    op.create_table(
        "glossary_conflicts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("source_term", sa.Text(), nullable=False),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolution_type", sa.Text(), nullable=True),
        sa.Column("resolution_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        _prefixed_uuid("gcf_", "glossary_conflicts"),
        sa.CheckConstraint(
            "trim(source_term) <> '' AND trim(conflict_type) <> '' AND trim(status) <> ''",
            name="ck_glossary_conflicts_required_text",
        ),
        sa.CheckConstraint(
            "json_valid(rules_json)",
            name="ck_glossary_conflicts_rules_json_valid",
        ),
        sa.CheckConstraint(
            "resolution_json IS NULL OR json_valid(resolution_json)",
            name="ck_glossary_conflicts_resolution_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_glossary_conflicts_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "ix_glossary_conflicts_project_status",
        "glossary_conflicts",
        ["project_id", "status"],
    )

    op.create_table(
        "protected_items",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("glossary_term_id", sa.Text(), nullable=True),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("placeholder", sa.Text(), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("replacement_value", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("capitalization_policy", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("restored_at", sa.Text(), nullable=True),
        _prefixed_uuid("pit_", "protected_items"),
        sa.CheckConstraint(
            f"item_type IN ({_values(_PROTECTED_ITEM_TYPES)})",
            name="ck_protected_items_type",
        ),
        sa.CheckConstraint(
            "trim(placeholder) <> '' AND trim(source_value) <> '' "
            "AND trim(replacement_value) <> ''",
            name="ck_protected_items_values",
        ),
        sa.CheckConstraint(
            f"rule_type IN ({_values(_RULE_TYPES)})",
            name="ck_protected_items_rule_type",
        ),
        sa.CheckConstraint(
            "start_offset >= 0",
            name="ck_protected_items_start_offset",
        ),
        sa.CheckConstraint(
            "end_offset > start_offset",
            name="ck_protected_items_end_offset",
        ),
        sa.CheckConstraint(
            "trim(capitalization_policy) <> '' AND trim(status) <> ''",
            name="ck_protected_items_policy_status",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["document_segments.id"],
            name="fk_protected_items_segment_id_document_segments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["glossary_term_id"],
            ["glossary_terms.id"],
            name="fk_protected_items_glossary_term_id_glossary_terms",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_protected_items_placeholder",
        "protected_items",
        ["segment_id", "placeholder"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_protected_items_placeholder", table_name="protected_items")
    op.drop_table("protected_items")
    op.drop_index("ix_glossary_conflicts_project_status", table_name="glossary_conflicts")
    op.drop_table("glossary_conflicts")
    op.drop_index("ix_term_occurrences_segment", table_name="term_occurrences")
    op.drop_index("ix_term_occurrences_candidate", table_name="term_occurrences")
    op.drop_index("ix_term_occurrences_term", table_name="term_occurrences")
    op.drop_table("term_occurrences")
    op.drop_index("uq_term_candidates_project_term", table_name="term_candidates")
    op.drop_table("term_candidates")
    op.execute("DROP TRIGGER trg_glossary_snapshots_no_update")
    op.drop_index("ix_glossary_snapshots_checksum", table_name="glossary_snapshots")
    op.drop_index("uq_glossary_snapshots_version", table_name="glossary_snapshots")
    op.drop_table("glossary_snapshots")
    op.execute("DROP TRIGGER trg_glossary_revisions_no_update")
    op.drop_index("uq_glossary_revisions_number", table_name="glossary_revisions")
    op.drop_table("glossary_revisions")
    op.execute("DROP INDEX uq_glossary_terms_identity")
    op.execute("DROP INDEX ix_glossary_terms_active")
    op.drop_index("ix_glossary_terms_normalized", table_name="glossary_terms")
    op.drop_table("glossary_terms")
    op.drop_table("glossaries")
