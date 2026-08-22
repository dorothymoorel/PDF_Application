import hashlib
from pathlib import Path

from transloka_core.recovery import (
    ArtifactDatabaseState,
    ArtifactKind,
    ArtifactRecoveryCandidate,
    ArtifactRecoveryService,
    ArtifactRecoveryState,
)


def _service(tmp_path: Path) -> tuple[ArtifactRecoveryService, Path, Path]:
    data_root = tmp_path / "data"
    temporary_root = data_root / "temp"
    temporary_root.mkdir(parents=True)
    return (
        ArtifactRecoveryService(data_root=data_root, temporary_root=temporary_root),
        data_root,
        temporary_root,
    )


def test_incomplete_export_is_removed_and_reported(tmp_path: Path) -> None:
    service, _data_root, temporary_root = _service(tmp_path)
    partial = temporary_root / "export-123.partial"
    partial.write_bytes(b"partial export")

    report = service.recover(
        (
            ArtifactRecoveryCandidate(
                artifact_id="export-123",
                kind=ArtifactKind.EXPORT,
                temporary_paths=(partial,),
                database_state=ArtifactDatabaseState(status="RUNNING", is_complete=False),
            ),
        )
    )

    assert not partial.exists()
    assert report.scanned_temporary_paths == (partial,)
    assert report.removed_temporary_paths == (partial,)
    assert report.results[0].state is ArtifactRecoveryState.INCOMPLETE_REMOVED


def test_stale_page_uses_database_state_and_cleans_temp_file(tmp_path: Path) -> None:
    service, _data_root, temporary_root = _service(tmp_path)
    partial = temporary_root / "page-7.partial"
    partial.write_bytes(b"interrupted page")
    final = tmp_path / "data" / "projects" / "project-1" / "page-7.bin"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"prior page")

    report = service.recover(
        (
            ArtifactRecoveryCandidate(
                artifact_id="page-7",
                kind=ArtifactKind.PAGE,
                temporary_paths=(partial,),
                final_path=final,
                database_state=ArtifactDatabaseState(status="RUNNING", is_complete=False),
            ),
        )
    )

    assert not partial.exists()
    assert final.exists()
    assert report.results[0].state is ArtifactRecoveryState.PRESENT_UNVERIFIED
    assert report.results[0].database_status == "RUNNING"


def test_incomplete_backup_is_removed(tmp_path: Path) -> None:
    service, _data_root, temporary_root = _service(tmp_path)
    partial = temporary_root / "backup-9.zip.partial"
    partial.write_bytes(b"truncated backup")

    report = service.recover(
        (
            ArtifactRecoveryCandidate(
                artifact_id="backup-9",
                kind=ArtifactKind.BACKUP,
                temporary_paths=(partial,),
                database_state=ArtifactDatabaseState(status="FAILED", is_complete=False),
            ),
        )
    )

    assert not partial.exists()
    assert report.results[0].kind is ArtifactKind.BACKUP
    assert report.results[0].state is ArtifactRecoveryState.INCOMPLETE_REMOVED


def test_valid_atomic_file_is_preserved_only_with_complete_db_integrity(tmp_path: Path) -> None:
    service, data_root, _temporary_root = _service(tmp_path)
    final = data_root / "projects" / "project-1" / "snapshot.bin"
    final.parent.mkdir(parents=True)
    content = b"atomic snapshot"
    final.write_bytes(content)

    report = service.recover(
        (
            ArtifactRecoveryCandidate(
                artifact_id="snapshot-1",
                kind=ArtifactKind.SNAPSHOT,
                final_path=final,
                database_state=ArtifactDatabaseState(
                    status="COMPLETED",
                    is_complete=True,
                    checksum_sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                ),
            ),
        )
    )

    assert final.read_bytes() == content
    assert report.results[0].state is ArtifactRecoveryState.VALID_PRIOR_RESULT
    assert report.results[0].preserved_final_path == final


def test_file_existence_alone_is_not_completion_evidence(tmp_path: Path) -> None:
    service, data_root, _temporary_root = _service(tmp_path)
    final = data_root / "projects" / "project-1" / "export.pdf"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"unverified output")

    report = service.recover(
        (
            ArtifactRecoveryCandidate(
                artifact_id="export-1",
                kind=ArtifactKind.EXPORT,
                final_path=final,
                database_state=ArtifactDatabaseState(status="RUNNING", is_complete=False),
            ),
        )
    )

    assert final.exists()
    assert report.results[0].state is ArtifactRecoveryState.PRESENT_UNVERIFIED
