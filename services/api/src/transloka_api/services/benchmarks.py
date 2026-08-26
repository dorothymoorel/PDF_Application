from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database.models.models import LocalModelRecord
from transloka_translation.benchmark import (
    FullBenchmarkResult,
    FullBenchmarkRunner,
    HardwareProfile,
    QuickBenchmarkResult,
    QuickBenchmarkRunner,
    detect_hardware_profile,
)
from transloka_translation.providers.ollama import (
    OllamaTranslationProvider,
    RemoteOllamaEndpointError,
)


class BenchmarkConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


ProviderFactory = Callable[[str, float], OllamaTranslationProvider]
HardwareProfileFactory = Callable[[], HardwareProfile]


class ProductionQuickBenchmarkRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory or _create_provider

    async def run(
        self,
        model_id: str,
        *,
        dataset_version: str,
        temperature: float,
        batch_sizes: list[int],
        benchmark_id: str,
    ) -> QuickBenchmarkResult:
        model_name = _resolve_model_name(self._session_factory, model_id)
        try:
            provider = self._provider_factory(model_name, temperature)
        except RemoteOllamaEndpointError:
            raise BenchmarkConfigurationError(
                "REMOTE_OLLAMA_BLOCKED",
                "The configured Ollama endpoint is not local.",
                403,
            ) from None
        result = await QuickBenchmarkRunner(provider).run(
            model_name,
            dataset_version=dataset_version,
            temperature=temperature,
            batch_sizes=batch_sizes,
            benchmark_id=benchmark_id,
        )
        return replace(result, model_id=model_id)


class ProductionFullBenchmarkRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        provider_factory: ProviderFactory | None = None,
        hardware_profile_factory: HardwareProfileFactory = detect_hardware_profile,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory or _create_provider
        self._hardware_profile_factory = hardware_profile_factory

    async def run(
        self,
        model_id: str,
        *,
        dataset_version: str,
        temperature: float,
        batch_sizes: list[int],
        context_lengths: list[str],
        benchmark_id: str,
    ) -> FullBenchmarkResult:
        model_name = _resolve_model_name(self._session_factory, model_id)
        try:
            provider = self._provider_factory(model_name, temperature)
        except RemoteOllamaEndpointError:
            raise BenchmarkConfigurationError(
                "REMOTE_OLLAMA_BLOCKED",
                "The configured Ollama endpoint is not local.",
                403,
            ) from None
        hardware_profile = self._hardware_profile_factory()
        try:
            provider_health = await provider.health_check()
        except Exception:
            provider_health = None
        if provider_health is not None and provider_health.version:
            hardware_profile = replace(
                hardware_profile,
                ollama_version=provider_health.version,
            )
        result = await FullBenchmarkRunner(
            provider,
            hardware_profile=hardware_profile,
        ).run(
            model_name,
            dataset_version=dataset_version,
            temperature=temperature,
            batch_sizes=batch_sizes,
            context_lengths=context_lengths,
            benchmark_id=benchmark_id,
        )
        return replace(result, model_id=model_id)


def _resolve_model_name(
    session_factory: sessionmaker[Session],
    model_id: str,
) -> str:
    with session_factory() as session:
        record = session.get(LocalModelRecord, model_id)
        if record is None:
            raise BenchmarkConfigurationError(
                "MODEL_NOT_FOUND",
                "The requested local model was not found.",
                404,
            )
        if not record.is_installed:
            raise BenchmarkConfigurationError(
                "OLLAMA_MODEL_NOT_INSTALLED",
                "The selected local model is not installed.",
                409,
            )
        return record.ollama_model_name


def _create_provider(model_name: str, temperature: float) -> OllamaTranslationProvider:
    return OllamaTranslationProvider(model_name=model_name, temperature=temperature)
