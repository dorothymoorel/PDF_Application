import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document
from transloka_core.database.models.glossary import (
    Glossary,
    GlossaryRuleType,
    GlossaryScope,
    GlossaryTerm,
    TermOccurrence,
)
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project

from transloka_glossary.conflicts import (
    ConflictDetector,
    ConflictRule,
    DetectedConflict,
    InvalidConflictRuleError,
)

_ACTIVE = "ACTIVE"
_TARGET_REQUIRED_RULES = frozenset(
    {
        GlossaryRuleType.TRANSLATE_AS,
        GlossaryRuleType.ORIGINAL_THEN_TRANSLATION,
        GlossaryRuleType.TRANSLATION_THEN_ORIGINAL,
    }
)
_TARGET_FORBIDDEN_RULES = frozenset(
    {
        GlossaryRuleType.KEEP_ORIGINAL,
        GlossaryRuleType.IGNORE,
    }
)
_PLACEHOLDER_PATTERN = re.compile(r"__TLK_[A-Z_]+_[0-9]{4,}_[0-9A-F]{2}__")


class GlossaryImpactError(RuntimeError):
    pass


class InvalidGlossaryImpactRequestError(GlossaryImpactError):
    pass


class GlossaryImpactProjectNotFoundError(GlossaryImpactError):
    pass


class GlossaryImpactTermNotFoundError(GlossaryImpactError):
    def __init__(self, term_ids: tuple[str, ...]) -> None:
        super().__init__("One or more glossary terms were not found in the project context.")
        self.term_ids = term_ids


class GlossaryImpactIntegrityError(GlossaryImpactError):
    pass


@dataclass(frozen=True, slots=True)
class GlossaryImpactChange:
    term_id: str
    proposed_rule_type: GlossaryRuleType
    proposed_target_term: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.term_id, str) or not self.term_id.strip():
            raise InvalidGlossaryImpactRequestError("A glossary term identifier is required.")
        if not isinstance(self.proposed_rule_type, GlossaryRuleType):
            raise InvalidGlossaryImpactRequestError("The proposed glossary rule type is invalid.")
        if self.proposed_target_term is not None and (
            not isinstance(self.proposed_target_term, str)
            or not self.proposed_target_term.strip()
            or self.proposed_target_term != self.proposed_target_term.strip()
            or not self.proposed_target_term.isprintable()
        ):
            raise InvalidGlossaryImpactRequestError(
                "The proposed target term must be valid printable text."
            )
        if self.proposed_rule_type in _TARGET_REQUIRED_RULES and self.proposed_target_term is None:
            raise InvalidGlossaryImpactRequestError(
                f"{self.proposed_rule_type.value} requires a proposed target term."
            )
        if (
            self.proposed_rule_type in _TARGET_FORBIDDEN_RULES
            and self.proposed_target_term is not None
        ):
            raise InvalidGlossaryImpactRequestError(
                f"{self.proposed_rule_type.value} does not accept a proposed target term."
            )


@dataclass(frozen=True, slots=True)
class GlossaryImpactResult:
    affected_segments: int
    unreviewed_segments: int
    approved_segments: int
    locked_segments: int
    safe_replacement_segments: int
    retranslation_recommended_segments: int
    conflicts: tuple[DetectedConflict, ...]


def analyze_glossary_impact(
    *,
    session: Session,
    project_id: str,
    changes: Iterable[GlossaryImpactChange],
) -> GlossaryImpactResult:
    if not isinstance(session, Session):
        raise TypeError("Glossary impact analysis requires a database session.")
    if not isinstance(project_id, str) or not project_id.strip():
        raise InvalidGlossaryImpactRequestError("A project identifier is required.")

    materialized = tuple(changes)
    if not materialized:
        raise InvalidGlossaryImpactRequestError("At least one glossary change is required.")
    if not all(isinstance(change, GlossaryImpactChange) for change in materialized):
        raise InvalidGlossaryImpactRequestError(
            "Every proposed change must be a glossary impact change."
        )
    term_ids = tuple(change.term_id for change in materialized)
    if len(term_ids) != len(set(term_ids)):
        raise InvalidGlossaryImpactRequestError(
            "A glossary term may appear only once in an impact request."
        )

    project = session.scalar(
        select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise GlossaryImpactProjectNotFoundError("The project was not found.")

    rules = _active_project_rules(session, project_id)
    rules_by_id = {rule.id: rule for rule in rules}
    missing = tuple(sorted(set(term_ids) - rules_by_id.keys()))
    if missing:
        raise GlossaryImpactTermNotFoundError(missing)

    changes_by_id = {change.term_id: change for change in materialized}
    effective_ids = tuple(
        term_id
        for term_id in term_ids
        if _changes_behavior(rules_by_id[term_id], changes_by_id[term_id])
    )
    conflicts = _new_conflicts(rules, changes_by_id)
    if not effective_ids:
        return GlossaryImpactResult(
            affected_segments=0,
            unreviewed_segments=0,
            approved_segments=0,
            locked_segments=0,
            safe_replacement_segments=0,
            retranslation_recommended_segments=0,
            conflicts=conflicts,
        )

    occurrences = tuple(
        session.scalars(
            select(TermOccurrence)
            .where(
                TermOccurrence.project_id == project_id,
                TermOccurrence.term_id.in_(effective_ids),
            )
            .order_by(TermOccurrence.segment_id, TermOccurrence.id)
        )
    )
    by_segment: dict[str, list[TermOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        by_segment[occurrence.segment_id].append(occurrence)

    segment_ids = tuple(sorted(by_segment))
    if not segment_ids:
        return GlossaryImpactResult(
            affected_segments=0,
            unreviewed_segments=0,
            approved_segments=0,
            locked_segments=0,
            safe_replacement_segments=0,
            retranslation_recommended_segments=0,
            conflicts=conflicts,
        )

    segments = tuple(
        session.scalars(
            select(DocumentSegment)
            .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
            .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
            .join(Document, Document.id == DocumentPage.document_id)
            .where(
                DocumentSegment.id.in_(segment_ids),
                Document.project_id == project_id,
            )
            .order_by(DocumentSegment.id)
        )
    )
    if {segment.id for segment in segments} != set(segment_ids):
        raise GlossaryImpactIntegrityError(
            "A glossary occurrence references a segment outside its project context."
        )

    locked = sum(_is_locked(segment) for segment in segments)
    approved = sum(not _is_locked(segment) and _is_approved(segment) for segment in segments)
    unreviewed = sum(
        not _is_locked(segment)
        and not _is_approved(segment)
        and segment.review_status == ReviewStatus.NOT_REVIEWED.value
        for segment in segments
    )
    safe = sum(
        _is_safe_exact_replacement(
            segment,
            by_segment[segment.id],
            rules_by_id,
            changes_by_id,
        )
        for segment in segments
    )

    return GlossaryImpactResult(
        affected_segments=len(segments),
        unreviewed_segments=unreviewed,
        approved_segments=approved,
        locked_segments=locked,
        safe_replacement_segments=safe,
        retranslation_recommended_segments=len(segments) - safe,
        conflicts=conflicts,
    )


def _active_project_rules(session: Session, project_id: str) -> tuple[GlossaryTerm, ...]:
    return tuple(
        session.scalars(
            select(GlossaryTerm)
            .join(Glossary, Glossary.id == GlossaryTerm.glossary_id)
            .where(
                Glossary.deleted_at.is_(None),
                Glossary.status == _ACTIVE,
                or_(Glossary.project_id == project_id, Glossary.project_id.is_(None)),
                GlossaryTerm.status == _ACTIVE,
            )
            .order_by(GlossaryTerm.id)
        )
    )


def _changes_behavior(term: GlossaryTerm, change: GlossaryImpactChange) -> bool:
    return (
        term.rule_type != change.proposed_rule_type.value
        or term.target_term != change.proposed_target_term
    )


def _new_conflicts(
    terms: tuple[GlossaryTerm, ...],
    changes: dict[str, GlossaryImpactChange],
) -> tuple[DetectedConflict, ...]:
    try:
        current_rules = tuple(_conflict_rule(term) for term in terms)
        proposed_rules = tuple(
            replace(
                rule,
                rule_type=changes[rule.term_id].proposed_rule_type,
                target_term=changes[rule.term_id].proposed_target_term,
            )
            if rule.term_id in changes
            else rule
            for rule in current_rules
        )
        detector = ConflictDetector()
        current = detector.detect(current_rules).conflicts
        proposed = detector.detect(proposed_rules).conflicts
    except (TypeError, ValueError, InvalidConflictRuleError) as exc:
        raise GlossaryImpactIntegrityError(
            "Stored glossary rules cannot be analyzed for conflicts."
        ) from exc

    existing = {_conflict_identity(conflict) for conflict in current}
    return tuple(conflict for conflict in proposed if _conflict_identity(conflict) not in existing)


def _conflict_rule(term: GlossaryTerm) -> ConflictRule:
    return ConflictRule(
        term_id=term.id,
        normalized_source_term=term.normalized_source_term,
        rule_type=GlossaryRuleType(term.rule_type),
        scope=GlossaryScope(term.scope),
        scope_reference_id=term.scope_reference_id,
        priority=term.priority,
        target_term=term.target_term,
    )


def _conflict_identity(conflict: DetectedConflict) -> tuple[object, ...]:
    return (
        conflict.conflict_type,
        conflict.normalized_source_term,
        conflict.term_ids,
        conflict.resolution_status,
        conflict.winner_term_id,
    )


def _is_locked(segment: DocumentSegment) -> bool:
    return bool(segment.is_locked) or segment.status == SegmentStatus.LOCKED.value


def _is_approved(segment: DocumentSegment) -> bool:
    return (
        segment.review_status == ReviewStatus.APPROVED.value
        or segment.status == SegmentStatus.APPROVED.value
    )


def _is_safe_exact_replacement(
    segment: DocumentSegment,
    occurrences: list[TermOccurrence],
    terms: dict[str, GlossaryTerm],
    changes: dict[str, GlossaryImpactChange],
) -> bool:
    if (
        _is_locked(segment)
        or _is_approved(segment)
        or segment.status != SegmentStatus.MACHINE_TRANSLATED.value
        or segment.review_status != ReviewStatus.NOT_REVIEWED.value
        or segment.reviewed_translation is not None
        or segment.machine_translation is None
        or segment.final_text != segment.machine_translation
    ):
        return False

    occurrence_counts = Counter(
        occurrence.term_id for occurrence in occurrences if occurrence.term_id is not None
    )
    replacements: list[tuple[int, int, str]] = []
    for term_id, expected_count in occurrence_counts.items():
        term = terms.get(term_id)
        change = changes.get(term_id)
        if term is None or change is None:
            raise GlossaryImpactIntegrityError(
                "A glossary occurrence references an unavailable proposed change."
            )
        old_text = _enforced_text(
            term.source_term,
            GlossaryRuleType(term.rule_type),
            term.target_term,
        )
        new_text = _enforced_text(
            term.source_term,
            change.proposed_rule_type,
            change.proposed_target_term,
        )
        if old_text is None or new_text is None or "\n" in old_text or "\n" in new_text:
            return False
        if old_text == new_text:
            continue
        matches = tuple(re.finditer(re.escape(old_text), segment.machine_translation))
        if len(matches) != expected_count:
            return False
        replacements.extend((match.start(), match.end(), new_text) for match in matches)

    ordered = sorted(replacements, key=lambda item: (item[0], item[1]))
    if any(first[1] > second[0] for first, second in zip(ordered, ordered[1:], strict=False)):
        return False

    updated = segment.machine_translation
    for start, end, replacement in reversed(ordered):
        updated = f"{updated[:start]}{replacement}{updated[end:]}"
    return _placeholder_inventory(updated) == _placeholder_inventory(segment.machine_translation)


def _enforced_text(
    source_term: str,
    rule_type: GlossaryRuleType,
    target_term: str | None,
) -> str | None:
    if rule_type is GlossaryRuleType.KEEP_ORIGINAL:
        return source_term
    if rule_type is GlossaryRuleType.TRANSLATE_AS:
        return target_term
    if rule_type is GlossaryRuleType.ORIGINAL_THEN_TRANSLATION and target_term is not None:
        return f"{source_term} ({target_term})"
    if rule_type is GlossaryRuleType.TRANSLATION_THEN_ORIGINAL and target_term is not None:
        return f"{target_term} ({source_term})"
    return None


def _placeholder_inventory(value: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _PLACEHOLDER_PATTERN.finditer(value))
