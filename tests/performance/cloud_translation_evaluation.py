"""Run the bounded CLOUD-04 Groq translation evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from transloka_translation.batching import estimate_tokens
from transloka_translation.parsing import ResponseParseError, parse_translation_response
from transloka_translation.providers import TranslationProvider, TranslationProviderError
from transloka_translation.providers.groq import GROQ_MODELS, GroqTranslationProvider
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationPlaceholder,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationStyle,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "translation"
    / "cloud_translation_evaluation_en_id_v1.json"
)
REPORT_VERSION = "1.0"
BATCH_SIZE = 5
REQUIRED_CATEGORIES = frozenset(
    {
        "general_prose",
        "glossary",
        "placeholder",
        "long_sentence",
        "formatting_marker",
        "numbers",
        "instruction_like",
    }
)
_PLACEHOLDER_PATTERN = re.compile(r"__TLK_[A-Z0-9_]+__")


class EvaluationError(RuntimeError):
    """Raised before or during a bounded evaluation."""


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    category: str
    source: str
    reference: str
    glossary: tuple[TranslationGlossaryEntry, ...] = ()


def load_dataset(path: Path = DATASET_PATH) -> tuple[str, tuple[EvaluationCase, ...]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("The evaluation dataset could not be loaded.") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "dataset_version",
        "provenance",
        "cases",
    }:
        raise EvaluationError("The evaluation dataset has an invalid top-level shape.")
    version = _text(payload["dataset_version"], "dataset_version")
    _text(payload["provenance"], "provenance")
    records = payload["cases"]
    if not isinstance(records, list) or len(records) != 50:
        raise EvaluationError("The evaluation dataset must contain exactly 50 cases.")

    cases = tuple(_case(record, index) for index, record in enumerate(records))
    if len({case.case_id for case in cases}) != len(cases):
        raise EvaluationError("Evaluation case IDs must be unique.")
    if {case.category for case in cases} != REQUIRED_CATEGORIES:
        raise EvaluationError("The evaluation dataset does not cover every required category.")
    return version, cases


async def run_evaluation(
    provider: TranslationProvider[TranslationRequest, str],
    *,
    model_name: str,
    cases: Sequence[EvaluationCase],
    dataset_version: str,
    show_review_text: bool = False,
) -> dict[str, object]:
    if model_name not in GROQ_MODELS:
        raise EvaluationError("Select an allowlisted Groq model.")
    if len(cases) != 50 or len({case.case_id for case in cases}) != 50:
        raise EvaluationError("The evaluation requires exactly 50 unique cases.")
    models = await provider.list_models()
    if not any(model.name == model_name for model in models):
        raise EvaluationError("The selected Groq model is not available in provider metadata.")

    case_results: list[dict[str, object]] = []
    request_count = 0
    retryable_stops = 0
    retry_after_seconds: float | None = None
    stop = False
    total_latency = 0.0
    for offset in range(0, len(cases), BATCH_SIZE):
        batch = tuple(cases[offset : offset + BATCH_SIZE])
        request = _request(batch)
        started = perf_counter()
        request_count += 1
        try:
            raw_response = await provider.translate(request)
            elapsed = max(0.0, perf_counter() - started)
            response = parse_translation_response(
                raw_response,
                known_segment_ids=(case.case_id for case in batch),
            )
            translated = {item.segment_id: item.translated_text for item in response.segments}
            for case in batch:
                output = translated[case.case_id]
                placeholders_valid = Counter(_placeholders(case.source)) == Counter(
                    _placeholders(output)
                )
                case_results.append(
                    _case_result(
                        case,
                        status="COMPLETED" if placeholders_valid else "FAILED",
                        latency_seconds=elapsed,
                        output=output,
                        schema_valid=True,
                        placeholders_valid=placeholders_valid,
                        error_code=None if placeholders_valid else "PLACEHOLDER_MISMATCH",
                    )
                )
                if show_review_text:
                    _print_review(case, output)
        except TranslationProviderError as exc:
            elapsed = max(0.0, perf_counter() - started)
            retryable_stops += int(exc.retryable)
            retry_after_seconds = exc.retry_after_seconds
            case_results.extend(
                _case_result(
                    case,
                    status="FAILED",
                    latency_seconds=elapsed,
                    output=None,
                    schema_valid=False,
                    placeholders_valid=False,
                    error_code=exc.code.value,
                )
                for case in batch
            )
            stop = True
        except ResponseParseError as exc:
            elapsed = max(0.0, perf_counter() - started)
            case_results.extend(
                _case_result(
                    case,
                    status="FAILED",
                    latency_seconds=elapsed,
                    output=None,
                    schema_valid=False,
                    placeholders_valid=False,
                    error_code=exc.code.value,
                )
                for case in batch
            )
        total_latency += elapsed
        if stop:
            break

    completed = sum(item["status"] == "COMPLETED" for item in case_results)
    validated = sum(
        item["schema_valid"] is True and item["placeholders_valid"] is True for item in case_results
    )
    total = len(cases)
    return {
        "report_version": REPORT_VERSION,
        "dataset_version": dataset_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "GROQ",
        "model": model_name,
        "status": "COMPLETED" if completed == total else "INCOMPLETE",
        "batch_size": BATCH_SIZE,
        "validation_scope": "schema and placeholder checks only; semantic quality needs review",
        "token_measurement": "deterministic segment-text estimate; not billed Groq usage",
        "aggregate": {
            "total_cases": total,
            "attempted_cases": len(case_results),
            "completed_cases": completed,
            "failed_cases": len(case_results) - completed,
            "unattempted_cases": total - len(case_results),
            "completion_rate": completed / total,
            "validation_rate": validated / total,
            "request_count": request_count,
            "automatic_retries": 0,
            "retryable_stops": retryable_stops,
            "retry_after_seconds": retry_after_seconds,
            "estimated_input_tokens": sum(
                cast(int, item["estimated_input_tokens"]) for item in case_results
            ),
            "estimated_output_tokens": sum(
                cast(int, item["estimated_output_tokens"]) for item in case_results
            ),
            "total_latency_seconds": total_latency,
            "average_batch_latency_seconds": total_latency / request_count,
        },
        "cases": case_results,
        "human_review": {
            "status": "PENDING",
            "reviewed_cases": 0,
            "note": "Pending human assessment; references are AI-authored, not a gold standard.",
        },
    }


def write_report(report: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=GROQ_MODELS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--review", action="store_true", help="Show synthetic text for review in this terminal."
    )
    args = parser.parse_args(argv)
    if not os.environ.get("GROQ_API_KEY"):
        parser.error("GROQ_API_KEY is not set in the current process.")
    if args.output.exists():
        parser.error("The output already exists; choose a new report path.")

    version, cases = load_dataset()
    provider = GroqTranslationProvider(
        enabled=True,
        cloud_consent=True,
        model_name=args.model,
    )
    try:
        report = asyncio.run(
            run_evaluation(
                provider,
                model_name=args.model,
                cases=cases,
                dataset_version=version,
                show_review_text=args.review,
            )
        )
    except TranslationProviderError as exc:
        parser.error(f"Groq preflight failed: {exc.code.value}.")
    except EvaluationError as exc:
        parser.error(str(exc))
    write_report(report, args.output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))
    return 0 if report["status"] == "COMPLETED" else 1


def _case(value: object, index: int) -> EvaluationCase:
    if not isinstance(value, dict):
        raise EvaluationError(f"Case {index} must be an object.")
    required = {"id", "category", "source", "reference"}
    if not required <= set(value) or set(value) - required - {"glossary"}:
        raise EvaluationError(f"Case {index} has invalid fields.")
    glossary_value = value.get("glossary", [])
    if not isinstance(glossary_value, list):
        raise EvaluationError(f"Case {index} glossary must be a list.")
    glossary: list[TranslationGlossaryEntry] = []
    for item in glossary_value:
        if not isinstance(item, dict) or set(item) != {"source_term", "target_term"}:
            raise EvaluationError(f"Case {index} has an invalid glossary entry.")
        glossary.append(
            TranslationGlossaryEntry(
                _text(item["source_term"], "source_term"),
                _text(item["target_term"], "target_term"),
                "REPLACE",
            )
        )
    return EvaluationCase(
        _text(value["id"], "id"),
        _text(value["category"], "category"),
        _text(value["source"], "source"),
        _text(value["reference"], "reference"),
        tuple(glossary),
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationError(f"{field} must be a non-empty string.")
    return value


def _request(cases: tuple[EvaluationCase, ...]) -> TranslationRequest:
    return TranslationRequest(
        segments=tuple(TranslationRequestSegment(case.case_id, case.source) for case in cases),
        context=TranslationContext("en", "id", document_type="cloud-evaluation"),
        glossary=tuple(entry for case in cases for entry in case.glossary),
        placeholders=tuple(
            TranslationPlaceholder(case.case_id, placeholder, "EVALUATION")
            for case in cases
            for placeholder in _placeholders(case.source)
        ),
        style=TranslationStyle.PROFESSIONAL,
    )


def _case_result(
    case: EvaluationCase,
    *,
    status: str,
    latency_seconds: float,
    output: str | None,
    schema_valid: bool,
    placeholders_valid: bool,
    error_code: str | None,
) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "category": case.category,
        "status": status,
        "schema_valid": schema_valid,
        "placeholders_valid": placeholders_valid,
        "batch_latency_seconds": latency_seconds,
        "estimated_input_tokens": estimate_tokens(case.source),
        "estimated_output_tokens": estimate_tokens(output or ""),
        "error_code": error_code,
    }


def _placeholders(value: str) -> tuple[str, ...]:
    return tuple(_PLACEHOLDER_PATTERN.findall(value))


def _print_review(case: EvaluationCase, output: str) -> None:
    print(f"\n[{case.case_id}] {case.category}")
    print(f"SOURCE: {case.source}")
    print(f"REFERENCE: {case.reference}")
    print(f"TRANSLATION: {output}")


if __name__ == "__main__":
    raise SystemExit(main())
