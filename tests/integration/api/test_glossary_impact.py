from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_api.routers.glossaries import router
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.glossary import TermOccurrence
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import DocumentType

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
CREATED_AT = "2026-08-12T00:00:00.000Z"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 1)
DOCUMENT_ID = _id("doc_", 2)
PAGE_ID = _id("pag_", 3)
BLOCK_ID = _id("blk_", 4)
UNREVIEWED_SEGMENT_ID = _id("seg_", 5)
APPROVED_SEGMENT_ID = _id("seg_", 6)
LOCKED_SEGMENT_ID = _id("seg_", 7)
EDITED_SEGMENT_ID = _id("seg_", 8)
MULTIPLE_SEGMENT_ID = _id("seg_", 9)


@pytest.fixture
def impact_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], str]]:
    root = tmp_path / "glossary impact api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    application.include_router(router)
    with TestClient(application) as client:
        project_id = _create_project(client)
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_document(factory, project_id)
        yield client, factory, project_id


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=CLIENT_HEADERS,
        json={
            "name": "Impact Project",
            "description": None,
            "source_language": "en",
            "target_language": "id",
            "document_type": "TECHNICAL_BOOK",
            "translation_style": "PROFESSIONAL",
            "reconstruction_mode": "HYBRID",
        },
    )
    assert response.status_code == 201
    return cast(str, response.json()["data"]["id"])


def _create_glossary(client: TestClient, project_id: str, name: str) -> str:
    response = client.post(
        "/api/v1/glossaries",
        headers=CLIENT_HEADERS,
        json={
            "project_id": project_id,
            "name": name,
            "description": None,
            "source_language": "en",
            "target_language": "id",
            "scope": "PROJECT",
            "domain": None,
            "is_default": name == "Primary",
        },
    )
    assert response.status_code == 201, response.text
    return cast(str, response.json()["data"]["id"])


def _create_term(
    client: TestClient,
    glossary_id: str,
    project_id: str,
    *,
    source_term: str,
    target_term: str,
    priority: int = 100,
) -> str:
    response = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json={
            "source_term": source_term,
            "rule_type": "TRANSLATE_AS",
            "target_term": target_term,
            "scope": "PROJECT",
            "scope_reference_id": project_id,
            "priority": priority,
            "case_sensitive": False,
            "whole_word": True,
            "match_mode": "PHRASE",
            "capitalization_policy": "MATCH_SENTENCE_POSITION",
            "inflection_policy": "USE_BASE_TERM",
            "first_use_policy": "NONE",
        },
    )
    assert response.status_code == 201, response.text
    return cast(str, response.json()["data"]["id"])


def _seed_document(factory: sessionmaker[Session], project_id: str) -> None:
    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=ORIGINAL_FILE_ID,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=f"projects/{project_id}/original/source.pdf",
                original_filename="source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                checksum_sha256="a" * 64,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=project_id,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Impact document",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=20,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.TRANSLATED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number=None,
                width_points=595.0,
                height_points=842.0,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.TRANSLATED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=1.0,
                ocr_confidence=None,
                structure_confidence=1.0,
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
                source_text="workflow and pipeline",
                normalized_source_text="workflow and pipeline",
                source_geometry_json=(
                    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,'
                    '"y":120.0,"width":200.0,"height":40.0}'
                ),
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.TRANSLATED.value,
                confidence=1.0,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add_all(
            (
                _segment(UNREVIEWED_SEGMENT_ID, 0, "alur kerja dimulai"),
                _segment(
                    APPROVED_SEGMENT_ID,
                    1,
                    "alur kerja disetujui",
                    status=SegmentStatus.APPROVED,
                    review_status=ReviewStatus.APPROVED,
                ),
                _segment(
                    LOCKED_SEGMENT_ID,
                    2,
                    "alur kerja terkunci",
                    status=SegmentStatus.LOCKED,
                    is_locked=True,
                ),
                _segment(
                    EDITED_SEGMENT_ID,
                    3,
                    "alur kerja manual",
                    status=SegmentStatus.USER_EDITED,
                    review_status=ReviewStatus.EDITED,
                    reviewed_translation="alur kerja manual",
                ),
                _segment(MULTIPLE_SEGMENT_ID, 4, "alur kerja memakai saluran"),
            )
        )


def _segment(
    segment_id: str,
    order: int,
    translation: str,
    *,
    status: SegmentStatus = SegmentStatus.MACHINE_TRANSLATED,
    review_status: ReviewStatus = ReviewStatus.NOT_REVIEWED,
    is_locked: bool = False,
    reviewed_translation: str | None = None,
) -> DocumentSegment:
    source = "workflow and pipeline"
    return DocumentSegment(
        id=segment_id,
        block_id=BLOCK_ID,
        section_id=None,
        segment_order=order,
        global_order=order,
        source_text=source,
        native_text=source,
        ocr_text=None,
        resolved_source_text=source,
        normalized_source_text=source,
        protected_source_text=None,
        machine_translation=translation,
        reviewed_translation=reviewed_translation,
        final_text=reviewed_translation or translation,
        source_language="en",
        target_language="id",
        status=status.value,
        review_status=review_status.value,
        is_locked=int(is_locked),
        current_revision=1,
        confidence_overall=1.0,
        confidence_json=None,
        translation_settings_hash=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def _add_occurrences(
    factory: sessionmaker[Session],
    project_id: str,
    term_id: str,
    segment_ids: tuple[str, ...],
    *,
    start: int,
    matched_text: str = "workflow",
) -> None:
    with transaction_scope(factory) as session:
        session.add_all(
            TermOccurrence(
                id=_id("occ_", start + index),
                project_id=project_id,
                document_id=DOCUMENT_ID,
                term_id=term_id,
                candidate_id=None,
                segment_id=segment_id,
                page_id=PAGE_ID,
                start_offset=0,
                end_offset=len(matched_text),
                matched_text=matched_text,
                match_method="EXACT",
                confidence=1.0,
                created_at=CREATED_AT,
            )
            for index, segment_id in enumerate(segment_ids)
        )


def _impact(
    client: TestClient,
    project_id: str,
    changes: list[dict[str, object]],
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/glossary-impact",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "impact-analysis"},
        json={"changes": changes},
    )
    assert response.status_code == 200, response.text
    assert response.json()["meta"] == {"request_id": "impact-analysis"}
    return cast(dict[str, object], response.json()["data"])


def _segment_state(factory: sessionmaker[Session]) -> list[tuple[object, ...]]:
    with factory() as session:
        return [
            (
                segment.id,
                segment.machine_translation,
                segment.reviewed_translation,
                segment.final_text,
                segment.status,
                segment.review_status,
                segment.is_locked,
                segment.current_revision,
                segment.updated_at,
            )
            for segment in session.scalars(select(DocumentSegment).order_by(DocumentSegment.id))
        ]


def test_impact_classifies_unreviewed_approved_locked_and_edited_without_mutation(
    impact_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = impact_api
    glossary_id = _create_glossary(client, project_id, "Primary")
    term_id = _create_term(
        client,
        glossary_id,
        project_id,
        source_term="workflow",
        target_term="alur kerja",
    )
    _add_occurrences(
        factory,
        project_id,
        term_id,
        (
            UNREVIEWED_SEGMENT_ID,
            APPROVED_SEGMENT_ID,
            LOCKED_SEGMENT_ID,
            EDITED_SEGMENT_ID,
        ),
        start=100,
    )
    before = _segment_state(factory)

    data = _impact(
        client,
        project_id,
        [
            {
                "term_id": term_id,
                "proposed_rule_type": "KEEP_ORIGINAL",
                "proposed_target_term": None,
            }
        ],
    )

    assert data == {
        "affected_segments": 4,
        "unreviewed_segments": 1,
        "approved_segments": 1,
        "locked_segments": 1,
        "safe_replacement_segments": 1,
        "retranslation_recommended_segments": 3,
        "conflicts": [],
    }
    assert _segment_state(factory) == before


def test_impact_returns_zero_for_term_without_occurrences(
    impact_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, _factory, project_id = impact_api
    glossary_id = _create_glossary(client, project_id, "Primary")
    term_id = _create_term(
        client,
        glossary_id,
        project_id,
        source_term="orchestrator",
        target_term="orkestrator",
    )

    data = _impact(
        client,
        project_id,
        [
            {
                "term_id": term_id,
                "proposed_rule_type": "TRANSLATE_AS",
                "proposed_target_term": "pengatur",
            }
        ],
    )

    assert data["affected_segments"] == 0
    assert data["safe_replacement_segments"] == 0
    assert data["retranslation_recommended_segments"] == 0


def test_impact_deduplicates_segments_affected_by_multiple_terms(
    impact_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = impact_api
    glossary_id = _create_glossary(client, project_id, "Primary")
    workflow_id = _create_term(
        client,
        glossary_id,
        project_id,
        source_term="workflow",
        target_term="alur kerja",
    )
    pipeline_id = _create_term(
        client,
        glossary_id,
        project_id,
        source_term="pipeline",
        target_term="saluran",
    )
    _add_occurrences(
        factory,
        project_id,
        workflow_id,
        (MULTIPLE_SEGMENT_ID,),
        start=200,
    )
    _add_occurrences(
        factory,
        project_id,
        pipeline_id,
        (MULTIPLE_SEGMENT_ID,),
        start=300,
        matched_text="pipeline",
    )

    data = _impact(
        client,
        project_id,
        [
            {
                "term_id": workflow_id,
                "proposed_rule_type": "TRANSLATE_AS",
                "proposed_target_term": "proses kerja",
            },
            {
                "term_id": pipeline_id,
                "proposed_rule_type": "KEEP_ORIGINAL",
                "proposed_target_term": None,
            },
        ],
    )

    assert data["affected_segments"] == 1
    assert data["unreviewed_segments"] == 1
    assert data["safe_replacement_segments"] == 1
    assert data["retranslation_recommended_segments"] == 0


def test_impact_returns_only_conflicts_introduced_by_proposed_changes(
    impact_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, _factory, project_id = impact_api
    primary = _create_glossary(client, project_id, "Primary")
    secondary = _create_glossary(client, project_id, "Secondary")
    first_id = _create_term(
        client,
        primary,
        project_id,
        source_term="workflow",
        target_term="alur kerja",
    )
    second_id = _create_term(
        client,
        secondary,
        project_id,
        source_term="workflow",
        target_term="alur kerja",
    )

    data = _impact(
        client,
        project_id,
        [
            {
                "term_id": second_id,
                "proposed_rule_type": "TRANSLATE_AS",
                "proposed_target_term": "proses kerja",
            }
        ],
    )

    conflicts = cast(list[dict[str, object]], data["conflicts"])
    assert len(conflicts) == 1
    assert conflicts[0]["conflict_type"] == "TARGET_CONFLICT"
    assert conflicts[0]["term_ids"] == sorted([first_id, second_id])
    assert conflicts[0]["resolution_status"] == "UNRESOLVED"
    assert conflicts[0]["blocking"] is True


def test_impact_rejects_missing_terms_and_invalid_target_rules(
    impact_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, _factory, project_id = impact_api
    missing = _id("trm_", 999)

    missing_response = client.post(
        f"/api/v1/projects/{project_id}/glossary-impact",
        headers=CLIENT_HEADERS,
        json={
            "changes": [
                {
                    "term_id": missing,
                    "proposed_rule_type": "KEEP_ORIGINAL",
                    "proposed_target_term": None,
                }
            ]
        },
    )
    invalid_response = client.post(
        f"/api/v1/projects/{project_id}/glossary-impact",
        headers=CLIENT_HEADERS,
        json={
            "changes": [
                {
                    "term_id": missing,
                    "proposed_rule_type": "TRANSLATE_AS",
                    "proposed_target_term": None,
                }
            ]
        },
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["error"]["code"] == "TERM_NOT_FOUND"
    assert invalid_response.status_code == 422
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"
