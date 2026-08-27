import json
from uuid import UUID

import pytest
from transloka_worker.ocr import OCRCommand, OCRWorkerError


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
DOCUMENT_ID = _id("doc_", 2)
PAGE_ID = _id("pag_", 3)


def _command(**overrides: object) -> OCRCommand:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "mode": "FORCE",
        "page_ids": (PAGE_ID,),
        "language": "en",
        "detect_tables": True,
        "detect_formulas": True,
    }
    values.update(overrides)
    return OCRCommand(**values)  # type: ignore[arg-type]


def test_ocr_command_round_trips_exact_versioned_payload() -> None:
    command = _command()

    decoded = OCRCommand.from_payload_json(json.dumps(command.to_payload()))

    assert decoded == command
    assert decoded.to_payload()["schema"] == "transloka.ocr.command.v1"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mode": "AUTO", "page_ids": (PAGE_ID,)}, "Automatic OCR"),
        ({"mode": "FORCE", "page_ids": ()}, "requires page identifiers"),
        ({"timeout_seconds": 301.0}, "timeout"),
        ({"max_attempts": 6}, "maximum attempts"),
    ],
)
def test_ocr_command_rejects_conflicting_or_unbounded_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(OCRWorkerError, match=message):
        _command(**overrides)


def test_ocr_command_rejects_duplicate_and_unknown_json_fields() -> None:
    payload = json.dumps(_command().to_payload())
    duplicate = payload[:-1] + ',"mode":"FORCE"}'
    unknown = json.loads(payload)
    unknown["path"] = "C:/secret.pdf"

    with pytest.raises(OCRWorkerError, match="duplicated"):
        OCRCommand.from_payload_json(duplicate)
    with pytest.raises(OCRWorkerError, match="fields"):
        OCRCommand.from_payload_json(json.dumps(unknown))
