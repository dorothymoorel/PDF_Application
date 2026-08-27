import json
from uuid import UUID

import pytest
from transloka_worker.translation import (
    TRANSLATION_COMMAND_SCHEMA,
    TranslationCommand,
    TranslationWorkerError,
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
DOCUMENT_ID = _id("doc_", 2)
MODEL_ID = _id("mdl_", 3)
SNAPSHOT_ID = _id("gsn_", 4)
SECTION_ID = _id("sec_", 5)


def _command(**overrides: object) -> TranslationCommand:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "scope": "FULL_DOCUMENT",
        "section_ids": (),
        "page_ids": (),
        "segment_ids": (),
        "model_id": MODEL_ID,
        "translation_style": "PROFESSIONAL",
        "batch_size": 5,
        "context_mode": "STANDARD",
        "retranslate_existing": False,
        "skip_locked_segments": True,
        "run_semantic_validation": False,
        "glossary_snapshot_id": SNAPSHOT_ID,
    }
    values.update(overrides)
    return TranslationCommand(**values)  # type: ignore[arg-type]


def test_translation_command_round_trips_canonically() -> None:
    command = _command()

    payload = command.to_payload()

    assert payload["schema"] == TRANSLATION_COMMAND_SCHEMA
    assert (
        TranslationCommand.from_payload_json(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        == command
    )


def test_translation_command_rejects_unknown_fields() -> None:
    payload = _command().to_payload()
    payload["unexpected"] = True

    with pytest.raises(TranslationWorkerError, match="fields"):
        TranslationCommand.from_payload_json(json.dumps(payload))


@pytest.mark.parametrize(
    "payload_change",
    [
        {"schema": "transloka.translation.command.v2"},
        {"project_id": "prj_invalid"},
        {"batch_size": 0},
        {"batch_size": 101},
        {"context_mode": "UNBOUNDED"},
        {"skip_locked_segments": 1},
        {"section_ids": "not-a-list"},
    ],
)
def test_translation_command_rejects_invalid_values(
    payload_change: dict[str, object],
) -> None:
    payload = _command().to_payload()
    payload.update(payload_change)

    with pytest.raises(TranslationWorkerError):
        TranslationCommand.from_payload_json(json.dumps(payload))


def test_translation_command_requires_matching_scope_selector() -> None:
    payload = _command(scope="SECTION", section_ids=(SECTION_ID,)).to_payload()
    assert TranslationCommand.from_payload_json(json.dumps(payload)).section_ids == (SECTION_ID,)

    payload["page_ids"] = [_id("pag_", 6)]
    with pytest.raises(TranslationWorkerError, match="selector"):
        TranslationCommand.from_payload_json(json.dumps(payload))
