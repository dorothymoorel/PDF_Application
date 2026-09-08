import asyncio
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
from transloka_translation.providers import (
    CancellationSignal,
    LocalModel,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.schemas import TranslationRequest


def _module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "performance/cloud_translation_evaluation.py"
    spec = importlib.util.spec_from_file_location("transloka_cloud_evaluation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evaluation = _module()
REQUIRED_CATEGORIES = evaluation.REQUIRED_CATEGORIES
EvaluationError = evaluation.EvaluationError
load_dataset = evaluation.load_dataset
run_evaluation = evaluation.run_evaluation


@dataclass
class Provider:
    references: dict[str, str]
    models: tuple[str, ...] = ("qwen/qwen3.8-27b",)
    failure: TranslationProviderError | None = None
    calls: int = 0
    raw_response: str | None = None
    metadata_checked: bool = False

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(ProviderHealthStatus.AVAILABLE)

    async def list_models(self) -> list[LocalModel]:
        self.metadata_checked = True
        return [LocalModel(name=model) for model in self.models]

    async def translate(
        self,
        request: TranslationRequest,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> str:
        del cancellation
        assert self.metadata_checked
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        if self.raw_response is not None:
            return self.raw_response
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": segment.segment_id,
                        "translated_text": self.references[segment.segment_id],
                    }
                    for segment in request.segments
                ]
            }
        )


def test_dataset_has_exact_bounded_coverage() -> None:
    version, cases = load_dataset()

    assert version == "cloud_translation_en_id_v1"
    assert len(cases) == 50
    assert {case.category for case in cases} == REQUIRED_CATEGORIES
    assert all(case.source and case.reference for case in cases)


def test_evaluation_uses_ten_batches_and_omits_text_from_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter(range(20))
    monkeypatch.setattr(evaluation, "perf_counter", lambda: next(ticks))
    version, cases = load_dataset()
    provider = Provider({case.case_id: case.reference for case in cases})

    report = asyncio.run(
        run_evaluation(
            provider,
            model_name="qwen/qwen3.8-27b",
            cases=cases,
            dataset_version=version,
        )
    )

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["completed_cases"] == 50
    assert aggregate["validation_rate"] == 1
    assert aggregate["request_count"] == 10
    assert provider.calls == 10
    assert aggregate["total_latency_seconds"] == 10
    assert aggregate["average_batch_latency_seconds"] == 1
    serialized = json.dumps(report)
    assert cases[0].source not in serialized
    assert cases[0].reference not in serialized


def test_metadata_and_provider_stop_prevent_extra_requests() -> None:
    version, cases = load_dataset()
    missing = Provider({}, models=())
    with pytest.raises(EvaluationError, match="not available"):
        asyncio.run(
            run_evaluation(
                missing,
                model_name="qwen/qwen3.8-27b",
                cases=cases,
                dataset_version=version,
            )
        )
    assert missing.calls == 0

    limited = Provider(
        {},
        failure=TranslationProviderError(
            ProviderErrorCode.RATE_LIMIT,
            "rate limited",
            retryable=True,
            retry_after_seconds=12,
        ),
    )
    report = asyncio.run(
        run_evaluation(
            limited,
            model_name="qwen/qwen3.8-27b",
            cases=cases,
            dataset_version=version,
        )
    )
    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["attempted_cases"] == 5
    assert aggregate["unattempted_cases"] == 45
    assert aggregate["automatic_retries"] == 0
    assert aggregate["retry_after_seconds"] == 12
    assert limited.calls == 1


@pytest.mark.parametrize("defect", ["invalid_json", "missing_placeholder"])
def test_invalid_output_is_not_counted_as_valid(defect: str) -> None:
    version, cases = load_dataset()
    references = {case.case_id: case.reference for case in cases}
    references["cloud_019"] = "Buka jalur untuk melihat laporan."
    provider = Provider(references, raw_response="not-json" if defect == "invalid_json" else None)
    report = asyncio.run(
        run_evaluation(
            provider,
            model_name="qwen/qwen3.8-27b",
            cases=cases,
            dataset_version=version,
        )
    )
    assert report["status"] == "INCOMPLETE"
    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["failed_cases"] == (50 if defect == "invalid_json" else 1)
    assert aggregate["validation_rate"] == (0 if defect == "invalid_json" else 49 / 50)


def test_dataset_rejects_missing_cases_and_duplicate_ids(tmp_path: Path) -> None:
    payload = json.loads(evaluation.DATASET_PATH.read_text(encoding="utf-8"))
    payload["cases"][1]["id"] = payload["cases"][0]["id"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvaluationError, match="unique"):
        load_dataset(path)
    payload["cases"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvaluationError, match="exactly 50"):
        load_dataset(path)


def test_missing_key_stops_before_network_or_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def unexpected_provider(**kwargs: object) -> None:
        pytest.fail("Missing key must stop before creating the live provider.")

    monkeypatch.setattr(evaluation, "GroqTranslationProvider", unexpected_provider)
    destination = tmp_path / "report.json"
    with pytest.raises(SystemExit) as exc:
        evaluation.main(["--model", "qwen/qwen3.8-27b", "--output", str(destination)])
    assert exc.value.code == 2
    assert not destination.exists()


def test_report_writer_preserves_existing_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "report.json"
    evaluation.write_report({"status": "test"}, destination)
    with pytest.raises(FileExistsError):
        evaluation.write_report({"status": "changed"}, destination)
    assert json.loads(destination.read_text()) == {"status": "test"}
