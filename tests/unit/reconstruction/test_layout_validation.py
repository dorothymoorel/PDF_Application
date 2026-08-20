import pytest
from transloka_reconstruction.layout.collision import (
    Collision,
    CollisionReport,
    CollisionSeverity,
    CollisionType,
    CriticalCollisionError,
    LayoutItem,
    LayoutItemKind,
    detect_collisions,
    severity_for_collision,
)
from transloka_reconstruction.layout.overflow import (
    BoundingBox,
    Overflow,
    OverflowAxis,
    OverflowSeverity,
    detect_overflow,
    has_critical_overflow,
    severity_for_overflow,
)


def test_overflow_detects_horizontal_vertical_page_and_cell() -> None:
    events = detect_overflow(
        "block-1",
        BoundingBox(-4, -3, 120, 130),
        bounds=BoundingBox(0, 0, 100, 100),
        page=BoundingBox(0, 0, 110, 110),
        cell=BoundingBox(0, 0, 90, 90),
    )

    assert {event.axis for event in events} == {
        OverflowAxis.HORIZONTAL,
        OverflowAxis.VERTICAL,
        OverflowAxis.PAGE,
        OverflowAxis.CELL,
    }
    assert all(event.overflow_points > 0 for event in events)
    assert any(event.severity is OverflowSeverity.CRITICAL for event in events)


def test_overflow_resolved_events_do_not_block() -> None:
    events = detect_overflow(
        "block-1",
        BoundingBox(0, 0, 101, 10),
        bounds=BoundingBox(0, 0, 100, 100),
        resolved=True,
    )

    assert len(events) == 1
    assert events[0].resolved is True
    assert has_critical_overflow(events) is False


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        (0, OverflowSeverity.INFO),
        (1, OverflowSeverity.LOW),
        (4, OverflowSeverity.MEDIUM),
        (12, OverflowSeverity.HIGH),
        (30, OverflowSeverity.CRITICAL),
    ],
)
def test_overflow_severity_thresholds(points: float, expected: OverflowSeverity) -> None:
    assert severity_for_overflow(points) is expected
    assert severity_for_overflow(0.1, page_boundary=True) is OverflowSeverity.CRITICAL


def _item(
    item_id: str,
    kind: LayoutItemKind,
    x: float,
    y: float,
    width: float = 10,
    height: float = 10,
    **kwargs: bool,
) -> LayoutItem:
    return LayoutItem(item_id, kind, BoundingBox(x, y, width, height), **kwargs)


def test_collision_detects_all_documented_types() -> None:
    items = (
        _item("text-1", LayoutItemKind.TEXT, 0, 0),
        _item("text-2", LayoutItemKind.TEXT, 5, 5),
        _item("image", LayoutItemKind.IMAGE, 5, 5),
        _item("table", LayoutItemKind.TABLE, 5, 5),
        _item("margin", LayoutItemKind.MARGIN, 5, 5),
        _item("header", LayoutItemKind.HEADER, 5, 5, fixed=True),
        _item("footer", LayoutItemKind.FOOTER, 5, 5, fixed=True),
    )
    report = detect_collisions(items)

    assert {collision.collision_type for collision in report.collisions} == {
        CollisionType.TEXT_TEXT,
        CollisionType.TEXT_IMAGE,
        CollisionType.TEXT_TABLE,
        CollisionType.TEXT_MARGIN,
        CollisionType.BLOCK_HEADER,
        CollisionType.BLOCK_FOOTER,
        CollisionType.TABLE_IMAGE,
    }


def test_critical_collision_blocks_export_until_resolved() -> None:
    report = detect_collisions(
        (
            _item("text", LayoutItemKind.TEXT, 0, 0, important=True),
            _item("image", LayoutItemKind.IMAGE, 0, 0),
        )
    )

    assert report.blocks_export is True
    with pytest.raises(CriticalCollisionError, match="critical collision"):
        report.raise_if_blocked()

    resolved = Collision(
        collision_id="c-1",
        first_id="text",
        second_id="image",
        collision_type=CollisionType.TEXT_IMAGE,
        severity=CollisionSeverity.CRITICAL,
        overlap_area=100,
        overlap_ratio=1,
        resolved=True,
    )
    assert CollisionReport((resolved,)).blocks_export is False


@pytest.mark.parametrize("severity", list(CollisionSeverity))
def test_collision_model_accepts_every_severity(severity: CollisionSeverity) -> None:
    collision = Collision(
        collision_id=f"c-{severity.value}",
        first_id="one",
        second_id="two",
        collision_type=CollisionType.TEXT_TEXT,
        severity=severity,
        overlap_area=1,
        overlap_ratio=0.1,
    )
    assert collision.severity is severity


def test_collision_severity_is_deterministic_for_fixed_and_important_content() -> None:
    first = _item("header", LayoutItemKind.HEADER, 0, 0, fixed=True)
    second = _item("text", LayoutItemKind.TEXT, 0, 0)
    assert (
        severity_for_collision(
            0.01,
            collision_type=CollisionType.BLOCK_HEADER,
            first=first,
            second=second,
        )
        is CollisionSeverity.CRITICAL
    )


def test_geometry_and_models_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="Bounding box"):
        BoundingBox(0, 0, -1, 2)
    with pytest.raises(ValueError, match="overflow_points"):
        Overflow("o-1", "block", OverflowAxis.HORIZONTAL, -1, OverflowSeverity.LOW)
