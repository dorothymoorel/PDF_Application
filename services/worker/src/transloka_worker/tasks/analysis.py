from collections.abc import Callable
from typing import Any

ANALYSIS_TASK_NAME = "transloka.analysis.execute"


def register_analysis_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The analysis task handler must be callable.")

    @huey.task(name=ANALYSIS_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_analysis(job_id: str) -> object:
        return handler(job_id)

    return execute_analysis
