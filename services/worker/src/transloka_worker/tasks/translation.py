from collections.abc import Callable
from typing import Any

TRANSLATION_TASK_NAME = "transloka.translation.execute"


def register_translation_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The translation task handler must be callable.")

    @huey.task(name=TRANSLATION_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_translation(job_id: str) -> object:
        return handler(job_id)

    return execute_translation
