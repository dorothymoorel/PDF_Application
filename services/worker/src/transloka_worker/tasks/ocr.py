from collections.abc import Callable
from typing import Any

OCR_TASK_NAME = "transloka.ocr.execute"


def register_ocr_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The OCR task handler must be callable.")

    @huey.task(name=OCR_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_ocr(job_id: str) -> object:
        return handler(job_id)

    return execute_ocr
