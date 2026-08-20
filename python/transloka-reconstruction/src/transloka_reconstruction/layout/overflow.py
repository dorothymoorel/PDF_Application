"""Deterministic overflow detection for reconstructed layout regions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class OverflowAxis(StrEnum):
    HORIZONTAL = "HORIZONTAL"
    VERTICAL = "VERTICAL"
    PAGE = "PAGE"
    CELL = "CELL"


class OverflowSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """A finite, non-negative rectangle in document points."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("Bounding box values must be finite numbers.")
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Bounding box values must be finite numbers.")
        if self.width < 0 or self.height < 0:
            raise ValueError("Bounding box width and height must be non-negative.")
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "width", float(self.width))
        object.__setattr__(self, "height", float(self.height))

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains(self, other: Self, *, tolerance: float = 0.0) -> bool:
        return (
            other.x >= self.x - tolerance
            and other.y >= self.y - tolerance
            and other.right <= self.right + tolerance
            and other.bottom <= self.bottom + tolerance
        )

    def intersection(self, other: Self) -> BoundingBox | None:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return BoundingBox(left, top, right - left, bottom - top)


@dataclass(frozen=True, slots=True)
class Overflow:
    """One auditable overflow event."""

    overflow_id: str
    block_id: str
    axis: OverflowAxis
    overflow_points: float
    severity: OverflowSeverity
    resolved: bool = False
    region_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.overflow_id) is not str or not self.overflow_id.strip():
            raise ValueError("overflow_id must be a non-empty string.")
        if type(self.block_id) is not str or not self.block_id.strip():
            raise ValueError("block_id must be a non-empty string.")
        if not isinstance(self.axis, OverflowAxis):
            try:
                object.__setattr__(self, "axis", OverflowAxis(self.axis))
            except ValueError as exc:
                raise ValueError("axis must be a known overflow axis.") from exc
        if not isinstance(self.severity, OverflowSeverity):
            try:
                object.__setattr__(self, "severity", OverflowSeverity(self.severity))
            except ValueError as exc:
                raise ValueError("severity must be a known overflow severity.") from exc
        if isinstance(self.overflow_points, bool) or not isinstance(
            self.overflow_points, (int, float)
        ):
            raise ValueError("overflow_points must be a finite non-negative number.")
        if not math.isfinite(float(self.overflow_points)) or self.overflow_points < 0:
            raise ValueError("overflow_points must be a finite non-negative number.")
        if type(self.resolved) is not bool:
            raise ValueError("resolved must be a boolean.")
        if self.region_id is not None and (
            type(self.region_id) is not str or not self.region_id.strip()
        ):
            raise ValueError("region_id must be a non-empty string or None.")
        object.__setattr__(self, "overflow_points", float(self.overflow_points))


def severity_for_overflow(
    overflow_points: float, *, page_boundary: bool = False
) -> OverflowSeverity:
    """Map overflow distance to a stable severity.

    Page-boundary overflow is critical as soon as content is clipped; smaller
    local overflow remains actionable without blocking export by itself.
    """

    if isinstance(overflow_points, bool) or not isinstance(overflow_points, (int, float)):
        raise ValueError("overflow_points must be a finite non-negative number.")
    points = float(overflow_points)
    if not math.isfinite(points) or points < 0:
        raise ValueError("overflow_points must be a finite non-negative number.")
    if points == 0:
        return OverflowSeverity.INFO
    if page_boundary:
        return OverflowSeverity.CRITICAL
    if points <= 2:
        return OverflowSeverity.LOW
    if points <= 8:
        return OverflowSeverity.MEDIUM
    if points <= 24:
        return OverflowSeverity.HIGH
    return OverflowSeverity.CRITICAL


def detect_overflow(
    block_id: str,
    content: BoundingBox,
    *,
    bounds: BoundingBox | None = None,
    page: BoundingBox | None = None,
    cell: BoundingBox | None = None,
    clipping_region: BoundingBox | None = None,
    overflow_id_prefix: str | None = None,
    resolved: bool = False,
) -> tuple[Overflow, ...]:
    """Detect local, page, and cell overflow without mutating geometry.

    ``bounds`` is the local text region and yields horizontal/vertical events.
    ``page`` (or ``clipping_region``) yields a page event when any content is
    clipped.  ``cell`` yields a cell event for table-cell fitting.
    """

    if type(block_id) is not str or not block_id.strip():
        raise ValueError("block_id must be a non-empty string.")
    if type(resolved) is not bool:
        raise ValueError("resolved must be a boolean.")
    if page is not None and clipping_region is not None:
        raise ValueError("Pass page or clipping_region, not both.")
    prefix = overflow_id_prefix or f"overflow_{block_id}"
    events: list[Overflow] = []

    if bounds is not None:
        horizontal = _outside_distance(content.x, content.right, bounds.x, bounds.right)
        vertical = _outside_distance(content.y, content.bottom, bounds.y, bounds.bottom)
        if horizontal > 0:
            events.append(
                Overflow(
                    overflow_id=f"{prefix}_horizontal",
                    block_id=block_id,
                    axis=OverflowAxis.HORIZONTAL,
                    overflow_points=horizontal,
                    severity=severity_for_overflow(horizontal),
                    resolved=resolved,
                    region_id="bounds",
                )
            )
        if vertical > 0:
            events.append(
                Overflow(
                    overflow_id=f"{prefix}_vertical",
                    block_id=block_id,
                    axis=OverflowAxis.VERTICAL,
                    overflow_points=vertical,
                    severity=severity_for_overflow(vertical),
                    resolved=resolved,
                    region_id="bounds",
                )
            )

    page_region = page or clipping_region
    if page_region is not None:
        page_overflow = _outside_distance(
            content.x,
            content.right,
            page_region.x,
            page_region.right,
            content.y,
            content.bottom,
            page_region.y,
            page_region.bottom,
        )
        if page_overflow > 0:
            events.append(
                Overflow(
                    overflow_id=f"{prefix}_page",
                    block_id=block_id,
                    axis=OverflowAxis.PAGE,
                    overflow_points=page_overflow,
                    severity=severity_for_overflow(page_overflow, page_boundary=True),
                    resolved=resolved,
                    region_id="page",
                )
            )

    if cell is not None:
        cell_overflow = _outside_distance(
            content.x,
            content.right,
            cell.x,
            cell.right,
            content.y,
            content.bottom,
            cell.y,
            cell.bottom,
        )
        if cell_overflow > 0:
            events.append(
                Overflow(
                    overflow_id=f"{prefix}_cell",
                    block_id=block_id,
                    axis=OverflowAxis.CELL,
                    overflow_points=cell_overflow,
                    severity=severity_for_overflow(cell_overflow),
                    resolved=resolved,
                    region_id="cell",
                )
            )
    return tuple(events)


def has_critical_overflow(events: tuple[Overflow, ...] | list[Overflow]) -> bool:
    return any(
        event.severity is OverflowSeverity.CRITICAL and not event.resolved for event in events
    )


def _outside_distance(
    left: float,
    right: float,
    bound_left: float,
    bound_right: float,
    top: float | None = None,
    bottom: float | None = None,
    bound_top: float | None = None,
    bound_bottom: float | None = None,
) -> float:
    horizontal = max(bound_left - left, right - bound_right, 0.0)
    if top is None or bottom is None or bound_top is None or bound_bottom is None:
        return horizontal
    vertical = max(bound_top - top, bottom - bound_bottom, 0.0)
    return max(horizontal, vertical)
