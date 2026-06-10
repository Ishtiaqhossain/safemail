import time
from typing import Any
from sqlalchemy.orm import Session
from app.models.task_log import TaskLog


def write_task_log(
    db: Session,
    task_name: str,
    status: str,
    *,
    error: str | None = None,
    duration_ms: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(TaskLog(
        task_name=task_name,
        status=status,
        error=error,
        duration_ms=duration_ms,
        meta=meta,
    ))
    db.commit()


class TaskTimer:
    def __init__(self):
        self._start = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)
