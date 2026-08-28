# mypy: ignore-errors
import json
from types import SimpleNamespace

import pytest
from transloka_worker.backup import (
    BACKUP_COMMAND_SCHEMA,
    BackupCommand,
    BackupWorkerError,
    map_public_backup_request,
)


def test_backup_command_round_trips_valid_payload_for_each_supported_type() -> None:
    for backup_type in ("DATABASE_ONLY", "METADATA", "FULL_PROJECTS"):
        cmd = BackupCommand(backup_type=backup_type)
        payload = cmd.to_payload()
        assert payload["schema"] == BACKUP_COMMAND_SCHEMA
        assert payload["backup_type"] == backup_type
        assert payload["include_queue_database"] is False
        assert payload["include_temporary"] is False
        restored = BackupCommand.from_payload_json(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        assert restored == cmd
        assert restored.backup_type == backup_type


def test_backup_command_rejects_duplicate_json_keys() -> None:
    raw = '{"schema":"transloka.backup.command.v1","backup_type":"DATABASE_ONLY","include_queue_database":false,"include_temporary":false,"backup_type":"DATABASE_ONLY"}'
    with pytest.raises(BackupWorkerError):
        BackupCommand.from_payload_json(raw)


def test_backup_command_rejects_unknown_field() -> None:
    payload = {
        "schema": "transloka.backup.command.v1",
        "backup_type": "DATABASE_ONLY",
        "include_queue_database": False,
        "include_temporary": False,
        "extra": True,
    }
    with pytest.raises(BackupWorkerError, match="fields"):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_rejects_missing_field() -> None:
    payload = {
        "schema": "transloka.backup.command.v1",
        "backup_type": "DATABASE_ONLY",
        "include_queue_database": False,
    }
    with pytest.raises(BackupWorkerError):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_rejects_wrong_schema() -> None:
    payload = {
        "schema": "transloka.backup.command.v2",
        "backup_type": "DATABASE_ONLY",
        "include_queue_database": False,
        "include_temporary": False,
    }
    with pytest.raises(BackupWorkerError, match="schema"):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_rejects_full_application_type() -> None:
    payload = {
        "schema": "transloka.backup.command.v1",
        "backup_type": "FULL_APPLICATION",
        "include_queue_database": False,
        "include_temporary": False,
    }
    with pytest.raises(BackupWorkerError):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_rejects_pre_restore_type() -> None:
    payload = {
        "schema": "transloka.backup.command.v1",
        "backup_type": "PRE_RESTORE",
        "include_queue_database": False,
        "include_temporary": False,
    }
    with pytest.raises(BackupWorkerError):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_rejects_non_bool_flag() -> None:
    payload = {
        "schema": "transloka.backup.command.v1",
        "backup_type": "DATABASE_ONLY",
        "include_queue_database": 0,
        "include_temporary": False,
    }
    with pytest.raises(BackupWorkerError):
        BackupCommand.from_payload_json(json.dumps(payload))


def test_backup_command_canonical_json_is_deterministic() -> None:
    cmd = BackupCommand(
        backup_type="METADATA", include_queue_database=False, include_temporary=False
    )
    payload = cmd.to_payload()
    first = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))
    assert first == second
    assert payload == json.loads(first)


def test_backup_command_public_mapping_accepts_only_all_false_flags() -> None:
    request = SimpleNamespace(
        backup_type="METADATA",
        include_original_files=False,
        include_exports=False,
        include_intermediate_files=False,
    )

    command = map_public_backup_request(request)

    assert command == BackupCommand(
        backup_type="METADATA",
        include_queue_database=False,
        include_temporary=False,
    )


@pytest.mark.parametrize(
    "field",
    ("include_original_files", "include_exports", "include_intermediate_files"),
)
def test_backup_command_public_mapping_rejects_each_true_include_flag(field: str) -> None:
    values = {
        "backup_type": "DATABASE_ONLY",
        "include_original_files": False,
        "include_exports": False,
        "include_intermediate_files": False,
    }
    values[field] = True

    with pytest.raises(BackupWorkerError, match=field):
        map_public_backup_request(SimpleNamespace(**values))
