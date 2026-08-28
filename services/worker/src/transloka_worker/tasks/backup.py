from collections.abc import Callable
from typing import Any

BACKUP_TASK_NAME = "transloka.backup.execute"


def register_backup_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The backup task handler must be callable.")

    @huey.task(name=BACKUP_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_backup(job_id: str) -> object:
        return handler(job_id)

    return execute_backup
