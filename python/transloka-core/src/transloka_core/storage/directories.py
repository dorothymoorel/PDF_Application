import os
import platform
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

DATA_DIRECTORY_ENVIRONMENT_VARIABLE = "TRANSLOKA_DATA_DIR"
_PRODUCT_DIRECTORY_NAME = "TransLoka"


class LocalDataDirectoryError(RuntimeError):
    """Raised when the local application-data layout cannot be used safely."""


@dataclass(frozen=True, slots=True)
class LocalDataDirectories:
    root: Path
    database: Path
    projects: Path
    cache: Path
    models: Path
    logs: Path
    backups: Path
    temporary: Path

    def items(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("root", self.root),
            ("database", self.database),
            ("projects", self.projects),
            ("cache", self.cache),
            ("models", self.models),
            ("logs", self.logs),
            ("backups", self.backups),
            ("temporary", self.temporary),
        )


def resolve_local_data_directories(
    override: str | os.PathLike[str] | None = None,
) -> LocalDataDirectories:
    configured = override
    if configured is None and DATA_DIRECTORY_ENVIRONMENT_VARIABLE in os.environ:
        configured = os.environ[DATA_DIRECTORY_ENVIRONMENT_VARIABLE]

    root = _normalize_root(configured) if configured is not None else _default_data_root()
    _validate_safe_root(root)

    return LocalDataDirectories(
        root=root,
        database=_contained_child(root, "database"),
        projects=_contained_child(root, "projects"),
        cache=_contained_child(root, "cache"),
        models=_contained_child(root, "models"),
        logs=_contained_child(root, "logs"),
        backups=_contained_child(root, "backups"),
        temporary=_contained_child(root, "temp"),
    )


def ensure_local_data_directories(directories: LocalDataDirectories) -> None:
    _validate_layout(directories)
    for logical_name, path in directories.items():
        if path.exists() and not path.is_dir():
            raise LocalDataDirectoryError(
                f"The local data location for '{logical_name}' is occupied by a file."
            )

    for logical_name, path in directories.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LocalDataDirectoryError(
                f"The local data directory '{logical_name}' could not be created."
            ) from exc

    for logical_name, path in directories.items():
        try:
            with tempfile.TemporaryFile(dir=path):
                pass
        except OSError as exc:
            raise LocalDataDirectoryError(
                f"The local data directory '{logical_name}' is not writable."
            ) from exc


def get_free_disk_bytes(directories: LocalDataDirectories) -> int:
    _validate_layout(directories)
    if not directories.root.is_dir():
        raise LocalDataDirectoryError(
            "The local data directories must be initialized before checking free disk space."
        )
    try:
        return shutil.disk_usage(directories.root).free
    except OSError as exc:
        raise LocalDataDirectoryError("Free disk space could not be determined.") from exc


def _default_data_root() -> Path:
    operating_system = platform.system()
    if operating_system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if not local_app_data:
            raise LocalDataDirectoryError(
                "LOCALAPPDATA is unavailable; set TRANSLOKA_DATA_DIR to an absolute path."
            )
        base = _normalize_absolute_path(local_app_data, "LOCALAPPDATA")
    elif operating_system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif operating_system == "Linux":
        xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        base = (
            _normalize_absolute_path(xdg_data_home, "XDG_DATA_HOME")
            if xdg_data_home
            else Path.home() / ".local" / "share"
        )
    else:
        raise LocalDataDirectoryError(
            "This operating system needs an absolute TRANSLOKA_DATA_DIR override."
        )
    return (base / _PRODUCT_DIRECTORY_NAME).resolve(strict=False)


def _normalize_root(value: str | os.PathLike[str]) -> Path:
    try:
        raw_value = os.fspath(value)
    except TypeError as exc:
        raise LocalDataDirectoryError(
            "TRANSLOKA_DATA_DIR must be an absolute filesystem path."
        ) from exc
    if not isinstance(raw_value, str) or not raw_value.strip() or not raw_value.isprintable():
        raise LocalDataDirectoryError(
            "TRANSLOKA_DATA_DIR must be a non-empty absolute filesystem path."
        )

    candidate = Path(raw_value.strip())
    if ".." in candidate.parts:
        raise LocalDataDirectoryError("TRANSLOKA_DATA_DIR must not contain path traversal.")
    if not candidate.is_absolute():
        raise LocalDataDirectoryError("TRANSLOKA_DATA_DIR must be an absolute path.")
    return candidate.resolve(strict=False)


def _normalize_absolute_path(value: str, source_name: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        raise LocalDataDirectoryError(f"{source_name} must contain an absolute path.")
    return candidate.resolve(strict=False)


def _validate_safe_root(root: Path) -> None:
    if not root.is_absolute() or root == Path(root.anchor):
        raise LocalDataDirectoryError("The selected local data root is unsafe.")
    if root.anchor.startswith("\\\\"):
        raise LocalDataDirectoryError("Network locations cannot be used as the local data root.")

    home = Path.home().resolve(strict=False)
    if root == home:
        raise LocalDataDirectoryError("The user profile itself cannot be used as the data root.")

    for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "WINDIR"):
        value = os.environ.get(environment_name, "").strip()
        if not value:
            continue
        protected_root = Path(value).resolve(strict=False)
        if root == protected_root or root.is_relative_to(protected_root):
            raise LocalDataDirectoryError(
                "Machine-wide system locations cannot be used as the local data root."
            )

    if any((candidate / ".git").exists() for candidate in (root, *root.parents)):
        raise LocalDataDirectoryError("The local data root must be outside the Git repository.")


def _contained_child(root: Path, name: str) -> Path:
    child = (root / name).resolve(strict=False)
    if not child.is_relative_to(root):
        raise LocalDataDirectoryError(
            f"The local data directory '{name}' would escape the selected root."
        )
    return child


def _validate_layout(directories: LocalDataDirectories) -> None:
    if not directories.root.is_absolute():
        raise LocalDataDirectoryError("The local data root must be absolute.")
    if any(not path.is_absolute() for _, path in directories.items()):
        raise LocalDataDirectoryError("Every local data directory must be absolute.")

    root = directories.root.resolve(strict=False)
    _validate_safe_root(root)
    for logical_name, path in directories.items():
        canonical_path = path.resolve(strict=False)
        if logical_name == "root":
            if canonical_path != root:
                raise LocalDataDirectoryError("The local data root is inconsistent.")
        elif not canonical_path.is_relative_to(root):
            raise LocalDataDirectoryError(
                f"The local data directory '{logical_name}' escapes the selected root."
            )
