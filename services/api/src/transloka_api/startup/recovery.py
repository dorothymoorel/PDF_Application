from collections.abc import Mapping
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker
from transloka_core.jobs.recovery import (
    DEFAULT_STALE_THRESHOLD,
    JobRecoveryResult,
    JobRecoveryService,
    RecoveryArtifact,
)
from transloka_core.storage import LocalDataDirectories


def recover_stale_jobs(
    session_factory: sessionmaker[Session],
    directories: LocalDataDirectories,
    *,
    stale_threshold: timedelta = DEFAULT_STALE_THRESHOLD,
    artifacts: Mapping[str, RecoveryArtifact] | None = None,
    now: datetime | None = None,
) -> tuple[JobRecoveryResult, ...]:
    """Run the idempotent stale-job recovery step during controlled startup."""
    return JobRecoveryService(
        session_factory,
        data_root=directories.root,
        temporary_root=directories.temporary,
    ).recover(
        stale_threshold=stale_threshold,
        artifacts=artifacts,
        now=now,
    )
