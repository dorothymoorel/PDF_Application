from collections.abc import Callable
from typing import Any

RECONSTRUCTION_TASK_NAME = "transloka.reconstruction.execute"


def register_reconstruction_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The reconstruction task handler must be callable.")

    @huey.task(name=RECONSTRUCTION_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_reconstruction(job_id: str) -> object:
        return handler(job_id)

    return execute_reconstruction
