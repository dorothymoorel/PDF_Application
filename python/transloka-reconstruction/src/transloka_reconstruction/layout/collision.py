"""Deterministic collision detection and export blocking policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from .overflow import BoundingBox


class LayoutItemKind(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    TABLE = "TABLE"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    MARGIN = "MARGIN"
    BLOCK = "BLOCK"


class CollisionType(StrEnum):
    TEXT_TEXT = "TEXT_TEXT"
    TEXT_IMAGE = "TEXT_IMAGE"
    TEXT_TABLE = "TEXT_TABLE"
    TEXT_MARGIN = "TEXT_MARGIN"
    TABLE_IMAGE = "TABLE_IMAGE"
    BLOCK_FOOTER = "BLOCK_FOOTER"
    BLOCK_HEADER = "BLOCK_HEADER"


class CollisionSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class LayoutItem:
    """A renderable region considered during pairwise collision checks."""

    item_id: str
    kind: LayoutItemKind
    bounds: BoundingBox
    important: bool = False
    fixed: bool = False

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or not self.item_id.strip():
            raise ValueError("item_id must be a non-empty string.")
        if not isinstance(self.kind, LayoutItemKind):
            try:
                object.__setattr__(self, "kind", LayoutItemKind(self.kind))
            except ValueError as exc:
                raise ValueError("kind must be a known layout item kind.") from exc
        if type(self.bounds) is not BoundingBox:
            raise TypeError("bounds must be a BoundingBox.")
        if type(self.important) is not bool or type(self.fixed) is not bool:
            raise ValueError("important and fixed must be booleans.")

    @property
    def item_type(self) -> LayoutItemKind:
        return self.kind


@dataclass(frozen=True, slots=True)
class Collision:
    """One auditable overlap between two layout items."""

    collision_id: str
    first_id: str
    second_id: str
    collision_type: CollisionType
    severity: CollisionSeverity
    overlap_area: float
    overlap_ratio: float
    resolved: bool = False

    def __post_init__(self) -> None:
        for field_name in ("collision_id", "first_id", "second_id"):
            value = getattr(self, field_name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")
        if self.first_id == self.second_id:
            raise ValueError("A collision requires two distinct items.")
        for field_name, enum_type in (
            ("collision_type", CollisionType),
            ("severity", CollisionSeverity),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, enum_type):
                try:
                    object.__setattr__(self, field_name, enum_type(value))
                except ValueError as exc:
                    raise ValueError(f"{field_name} must be a known collision value.") from exc
        for field_name in ("overlap_area", "overlap_ratio"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be a finite non-negative number.")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{field_name} must be a finite non-negative number.")
        if self.overlap_ratio > 1.0:
            raise ValueError("overlap_ratio must not exceed 1.")
        if type(self.resolved) is not bool:
            raise ValueError("resolved must be a boolean.")
        object.__setattr__(self, "overlap_area", float(self.overlap_area))
        object.__setattr__(self, "overlap_ratio", float(self.overlap_ratio))


@dataclass(frozen=True, slots=True)
class CollisionReport:
    """Collision findings and the export gate derived from them."""

    collisions: tuple[Collision, ...]

    def __post_init__(self) -> None:
        values = tuple(self.collisions)
        if any(type(collision) is not Collision for collision in values):
            raise TypeError("collisions must contain Collision values.")
        object.__setattr__(self, "collisions", values)

    @property
    def critical_collisions(self) -> tuple[Collision, ...]:
        return tuple(
            collision
            for collision in self.collisions
            if collision.severity is CollisionSeverity.CRITICAL and not collision.resolved
        )

    @property
    def blocks_export(self) -> bool:
        return bool(self.critical_collisions)

    @property
    def export_blocked(self) -> bool:
        return self.blocks_export

    def raise_if_blocked(self) -> None:
        if self.blocks_export:
            raise CriticalCollisionError(self.critical_collisions)


class CriticalCollisionError(ValueError):
    """Raised when unresolved critical collisions make export unsafe."""

    def __init__(self, collisions: tuple[Collision, ...]) -> None:
        if not collisions or any(
            collision.severity is not CollisionSeverity.CRITICAL or collision.resolved
            for collision in collisions
        ):
            raise ValueError("CriticalCollisionError requires unresolved critical collisions.")
        self.collisions = collisions
        super().__init__(f"Export blocked by {len(collisions)} critical collision(s).")


def severity_for_collision(
    overlap_ratio: float,
    *,
    collision_type: CollisionType,
    first: LayoutItem,
    second: LayoutItem,
) -> CollisionSeverity:
    """Classify overlap using coverage and fixed/important content semantics."""

    if isinstance(overlap_ratio, bool) or not isinstance(overlap_ratio, (int, float)):
        raise ValueError("overlap_ratio must be a finite number between 0 and 1.")
    ratio = float(overlap_ratio)
    if not math.isfinite(ratio) or not 0 <= ratio <= 1:
        raise ValueError("overlap_ratio must be a finite number between 0 and 1.")
    if ratio == 0:
        return CollisionSeverity.INFO
    if ratio >= 0.5 or (
        collision_type in {CollisionType.TEXT_IMAGE, CollisionType.TABLE_IMAGE}
        and (first.important or second.important)
    ):
        return CollisionSeverity.CRITICAL
    if collision_type in {CollisionType.BLOCK_HEADER, CollisionType.BLOCK_FOOTER} and (
        first.fixed or second.fixed
    ):
        return CollisionSeverity.CRITICAL
    if collision_type is CollisionType.TEXT_TABLE and ratio >= 0.25:
        return CollisionSeverity.CRITICAL
    if ratio <= 0.05:
        return CollisionSeverity.LOW
    if ratio <= 0.2:
        return CollisionSeverity.MEDIUM
    return CollisionSeverity.HIGH


def detect_collisions(
    items: tuple[LayoutItem, ...] | list[LayoutItem],
    *,
    tolerance: float = 0.0,
    collision_id_prefix: str = "collision",
) -> CollisionReport:
    """Compare every item pair in stable input order."""

    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise ValueError("tolerance must be a finite non-negative number.")
    if not math.isfinite(float(tolerance)) or tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number.")
    if type(collision_id_prefix) is not str or not collision_id_prefix.strip():
        raise ValueError("collision_id_prefix must be a non-empty string.")
    values = tuple(items)
    if any(type(item) is not LayoutItem for item in values):
        raise TypeError("items must contain LayoutItem values.")
    findings: list[Collision] = []
    for first_index, first in enumerate(values):
        for second in values[first_index + 1 :]:
            overlap = first.bounds.intersection(second.bounds)
            if overlap is None or overlap.area <= tolerance:
                continue
            collision_type = _collision_type(first.kind, second.kind)
            if collision_type is None:
                continue
            denominator = min(first.bounds.area, second.bounds.area)
            ratio = overlap.area / denominator if denominator > 0 else 1.0
            findings.append(
                Collision(
                    collision_id=f"{collision_id_prefix}_{len(findings) + 1:03d}",
                    first_id=first.item_id,
                    second_id=second.item_id,
                    collision_type=collision_type,
                    severity=severity_for_collision(
                        ratio,
                        collision_type=collision_type,
                        first=first,
                        second=second,
                    ),
                    overlap_area=overlap.area,
                    overlap_ratio=min(1.0, ratio),
                )
            )
    return CollisionReport(tuple(findings))


def _collision_type(
    first: LayoutItemKind,
    second: LayoutItemKind,
) -> CollisionType | None:
    pair = {first, second}
    if pair == {LayoutItemKind.TEXT}:
        return CollisionType.TEXT_TEXT
    if pair == {LayoutItemKind.TEXT, LayoutItemKind.IMAGE}:
        return CollisionType.TEXT_IMAGE
    if pair == {LayoutItemKind.TEXT, LayoutItemKind.TABLE}:
        return CollisionType.TEXT_TABLE
    if pair == {LayoutItemKind.TEXT, LayoutItemKind.MARGIN}:
        return CollisionType.TEXT_MARGIN
    if pair == {LayoutItemKind.TABLE, LayoutItemKind.IMAGE}:
        return CollisionType.TABLE_IMAGE
    if LayoutItemKind.HEADER in pair:
        return CollisionType.BLOCK_HEADER
    if LayoutItemKind.FOOTER in pair:
        return CollisionType.BLOCK_FOOTER
    return None
