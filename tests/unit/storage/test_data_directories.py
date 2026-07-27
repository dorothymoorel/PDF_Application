import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest
from transloka_api.config import Settings
from transloka_core.storage import (
    LocalDataDirectories,
    LocalDataDirectoryError,
    ensure_local_data_directories,
    get_free_disk_bytes,
    resolve_local_data_directories,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
EXPECTED_CHILD_NAMES = {
    "database",
    "projects",
    "cache",
    "models",
    "logs",
    "backups",
    "temp",
}


def test_windows_default_uses_local_app_data_without_creating_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_app_data = tmp_path / "Local App Data"
    monkeypatch.delenv("TRANSLOKA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    directories = resolve_local_data_directories()

    assert directories.root == (local_app_data / "TransLoka").resolve()
    assert directories.root.is_absolute()
    assert not directories.root.exists()
    assert not directories.root.is_relative_to(REPOSITORY_ROOT.resolve())


def test_default_does_not_depend_on_current_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local_app_data = tmp_path / "local"
    first_working_directory = tmp_path / "first"
    second_working_directory = tmp_path / "second"
    first_working_directory.mkdir()
    second_working_directory.mkdir()
    monkeypatch.delenv("TRANSLOKA_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    monkeypatch.chdir(first_working_directory)
    first = resolve_local_data_directories()
    monkeypatch.chdir(second_working_directory)
    second = resolve_local_data_directories()

    assert first == second


def test_linux_default_uses_absolute_xdg_data_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_data_home = tmp_path / "xdg data"
    monkeypatch.delenv("TRANSLOKA_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    directories = resolve_local_data_directories()

    assert directories.root == (xdg_data_home / "TransLoka").resolve()
    assert not directories.root.exists()


def test_absolute_override_supports_spaces_and_non_ascii_characters(tmp_path: Path) -> None:
    root = tmp_path / "Data Pengguna_日本語"

    directories = resolve_local_data_directories(root)

    assert directories.root == root.resolve()
    assert not root.exists()


@pytest.mark.parametrize("value", ["", "   ", ".", "relative/data", "../outside"])
def test_invalid_override_is_rejected(value: str) -> None:
    with pytest.raises(LocalDataDirectoryError, match="TRANSLOKA_DATA_DIR"):
        resolve_local_data_directories(value)


def test_environment_override_is_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "explicit"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))

    assert resolve_local_data_directories().root == root.resolve()


def test_repository_root_is_rejected() -> None:
    with pytest.raises(LocalDataDirectoryError, match="outside the Git repository"):
        resolve_local_data_directories(REPOSITORY_ROOT)


def test_git_worktree_root_is_rejected(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere", encoding="utf-8")

    with pytest.raises(LocalDataDirectoryError, match="outside the Git repository"):
        resolve_local_data_directories(checkout / "data")


def test_child_paths_are_deterministic_and_contained(tmp_path: Path) -> None:
    first = resolve_local_data_directories(tmp_path / "data")
    second = resolve_local_data_directories(tmp_path / "data")
    children = {path.name for name, path in first.items() if name != "root"}

    assert first == second
    assert children == EXPECTED_CHILD_NAMES
    assert all(
        path.is_relative_to(first.root)
        for logical_name, path in first.items()
        if logical_name != "root"
    )


def test_directory_layout_is_immutable(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")

    with pytest.raises(FrozenInstanceError):
        directories.root = tmp_path  # type: ignore[misc]


def test_explicit_initialization_is_idempotent_and_creates_no_database_file(
    tmp_path: Path,
) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")

    ensure_local_data_directories(directories)
    ensure_local_data_directories(directories)

    assert all(path.is_dir() for _, path in directories.items())
    assert {path.name for path in directories.root.iterdir()} == EXPECTED_CHILD_NAMES
    assert list(directories.root.rglob("*.db")) == []


def test_occupied_required_path_fails_before_other_children_are_created(
    tmp_path: Path,
) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    directories.root.mkdir()
    directories.database.write_text("occupied", encoding="utf-8")

    with pytest.raises(LocalDataDirectoryError, match="'database'.*occupied"):
        ensure_local_data_directories(directories)

    assert not directories.projects.exists()


def test_write_permission_failure_is_reported_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")

    def deny_write(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("private path detail")

    monkeypatch.setattr(tempfile, "TemporaryFile", deny_write)

    with pytest.raises(LocalDataDirectoryError, match="'root'.*not writable") as error:
        ensure_local_data_directories(directories)

    assert "private path detail" not in str(error.value)
    assert str(directories.root) not in str(error.value)


def test_free_disk_query_requires_initialized_root_and_returns_bytes(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")

    with pytest.raises(LocalDataDirectoryError, match="must be initialized"):
        get_free_disk_bytes(directories)

    ensure_local_data_directories(directories)

    assert get_free_disk_bytes(directories) > 0


def test_symlink_child_cannot_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "data"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "cache").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable.")

    with pytest.raises(LocalDataDirectoryError, match="escape"):
        resolve_local_data_directories(root)


def test_tampered_layout_cannot_escape_root(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    tampered = replace(directories, cache=tmp_path / "outside")

    with pytest.raises(LocalDataDirectoryError, match="escapes"):
        ensure_local_data_directories(tampered)

    assert not directories.root.exists()


def test_api_settings_use_shared_internal_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "api-data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))

    settings = Settings()

    assert isinstance(settings.data_directories, LocalDataDirectories)
    assert settings.data_directories.root == root.resolve()
    assert "data_directories" not in settings.model_dump()
    assert not root.exists()


@pytest.mark.parametrize(
    "statement",
    (
        "import transloka_core.storage",
        "from transloka_api.main import app; app.openapi()",
        "import transloka_worker",
    ),
)
def test_imports_and_openapi_create_no_data_directories(statement: str, tmp_path: Path) -> None:
    root = tmp_path / "import-data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()
