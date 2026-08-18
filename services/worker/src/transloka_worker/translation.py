from __future__ import annotations

import asyncio
from collections.abc import Callable

from transloka_translation.orchestration import (
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunResult,
)


class TranslationJobRunner:
    """Small worker boundary that keeps queue concerns separate from the pipeline."""

    def __init__(
        self,
        orchestrator: TranslationOrchestrator,
        operation_loader: Callable[[str], TranslationOperation],
    ) -> None:
        self._orchestrator = orchestrator
        self._operation_loader = operation_loader

    def run(self, job_id: str) -> TranslationRunResult:
        if type(job_id) is not str or not job_id.strip():
            raise ValueError("job_id must be a non-empty string.")
        operation = self._operation_loader(job_id)
        if not isinstance(operation, TranslationOperation):
            raise TypeError("operation_loader must return TranslationOperation.")
        return asyncio.run(self._orchestrator.run(operation))


def run_translation_job(
    job_id: str,
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> TranslationRunResult:
    return TranslationJobRunner(orchestrator, operation_loader).run(job_id)


def create_translation_task(
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> Callable[[str], TranslationRunResult]:
    runner = TranslationJobRunner(orchestrator, operation_loader)
    return runner.run
