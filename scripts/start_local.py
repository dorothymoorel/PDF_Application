"""Foreground Linux launcher; run with uv run --no-sync python scripts/start_local.py."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType

if sys.platform != "linux":
    raise SystemExit("This launcher requires Linux. On Windows, use scripts/start.ps1.")

ROOT = Path(__file__).resolve().parents[1]
SHUTDOWN_TIMEOUT = 10.0
PORTS = (3000, 8000)


class StartupError(RuntimeError):
    pass


def check_prerequisites() -> Path:
    if sys.version_info[:2] != (3, 12):
        raise StartupError("This launcher requires Linux and Python 3.12 through uv.")
    for name, prefix in (("node", "v24."), ("pnpm", "11.")):
        executable = shutil.which(name)
        if executable is None:
            raise StartupError(f"Required tool '{name}' was not found.")
        result = subprocess.run(
            [executable, "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip().startswith(prefix):
            raise StartupError(f"Unsupported {name} version; install the documented prerequisite.")
    if not (ROOT / "apps/web/node_modules/next/package.json").is_file():
        raise StartupError("Web dependencies are missing. Run pnpm install --frozen-lockfile.")
    for package in ("transloka_api", "transloka_worker", "alembic"):
        try:
            importlib.import_module(package)
        except ImportError as exc:
            raise StartupError("Python workspace imports failed. Run uv sync --locked.") from exc

    from transloka_api.config import Settings
    from transloka_core.storage import resolve_local_data_directories

    if not os.environ.get("TRANSLOKA_DATA_DIR"):
        raise StartupError("Set TRANSLOKA_DATA_DIR to an absolute path outside the repository.")
    try:
        settings = Settings()
        data_root = resolve_local_data_directories().root
    except (ValueError, RuntimeError) as exc:
        raise StartupError(
            "Invalid API or data-directory configuration; check docs/SETUP.md."
        ) from exc
    if data_root.is_relative_to(ROOT) or ROOT.is_relative_to(data_root):
        raise StartupError("The data directory must be separate from the repository.")
    if settings.host != "127.0.0.1" or settings.port != 8000:
        raise StartupError("The local web client requires API binding 127.0.0.1:8000.")
    if "http://127.0.0.1:3000" not in settings.web_origins:
        raise StartupError("TRANSLOKA_WEB_ORIGINS must include http://127.0.0.1:3000.")
    print("[TransLoka] Development prerequisites are ready.", flush=True)
    return data_root


def check_ports(ports: tuple[int, ...] | None = None) -> None:
    for port in PORTS if ports is None else ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise StartupError(f"Port {port} is occupied; no components were started.") from exc


class Supervisor:
    def __init__(self) -> None:
        self.children: list[tuple[str, subprocess.Popen[bytes]]] = []
        self.stop_requested = False

    def request_stop(self, _signal: int, _frame: FrameType | None) -> None:
        self.stop_requested = True

    def start(self, name: str, command: list[str]) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
        self.children.append((name, process))
        return process

    def migrate(self) -> bool:
        if self.stop_requested:
            return False
        process = self.start("migration", [sys.executable, "-m", "alembic", "upgrade", "head"])
        while process.poll() is None:
            if self.stop_requested:
                return False
            time.sleep(0.1)
        if process.returncode != 0:
            raise StartupError("Database migration failed. No application component was started.")
        self.children.remove(("migration", process))
        print("[TransLoka] Database schema is current.", flush=True)
        return not self.stop_requested

    def run_components(self, ollama_executable: str | None = None) -> int:
        if ollama_executable is not None:
            if self.stop_requested:
                return 0
            self.start("Ollama", [ollama_executable, "serve"])
        commands = (
            ("API", [sys.executable, "-c", "from transloka_api.main import run; run()"]),
            ("worker", [sys.executable, "-m", "transloka_worker"]),
            (
                "web",
                [
                    "pnpm",
                    "--filter",
                    "@transloka/web",
                    "dev",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3000",
                ],
            ),
        )
        for name, command in commands:
            if self.stop_requested:
                return 0
            self.start(name, command)
        print(
            "[TransLoka] Starting local stack. Use Ctrl+C to stop all owned components.", flush=True
        )
        while not self.stop_requested:
            for name, process in self.children:
                if process.poll() is not None:
                    raise StartupError(f"The {name} component exited; stopping the local stack.")
            time.sleep(0.1)
        return 0

    def close(self) -> None:
        # Descendants may outlive the process-group leader (pnpm / Next.js).
        groups = [process.pid for _, process in self.children]
        for group in groups:
            self._signal_group(group, signal.SIGTERM)
        deadline = time.monotonic() + SHUTDOWN_TIMEOUT
        while time.monotonic() < deadline:
            for _, process in self.children:
                process.poll()
            if not any(self._signal_group(group, 0) for group in groups):
                break
            time.sleep(0.1)
        for group in groups:
            self._signal_group(group, signal.SIGKILL)
        for _, process in self.children:
            process.wait()

    @staticmethod
    def _signal_group(group: int, signal_number: int) -> bool:
        try:
            os.killpg(group, signal_number)
            return True
        except ProcessLookupError:
            return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--with-ollama", action="store_true")
    args = parser.parse_args()
    supervisor = Supervisor()
    previous_handlers = {
        number: signal.signal(number, supervisor.request_stop)
        for number in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        data_root = check_prerequisites()
        ollama_executable = None
        if args.with_ollama:
            ollama_executable = os.environ.get("TRANSLOKA_OLLAMA_EXECUTABLE", "")
            if not Path(ollama_executable).is_absolute() or not os.access(
                ollama_executable, os.X_OK
            ):
                raise StartupError("Install the pinned Ollama runtime before using --with-ollama.")
            os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
            os.environ["OLLAMA_NO_CLOUD"] = "1"
        if supervisor.stop_requested:
            return 0
        if args.check_only:
            print("[TransLoka] Validation-only check completed.")
            return 0
        import fcntl

        data_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            data_root / ".local-stack.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "r+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StartupError("A local launcher already owns this data directory.") from exc
            if args.with_ollama:
                check_ports((*PORTS, 11434))
            else:
                check_ports()
            try:
                if not supervisor.migrate():
                    return 0
                if args.prepare_only:
                    print("[TransLoka] Preparation-only check completed.")
                    return 0
                return supervisor.run_components(ollama_executable)
            finally:
                supervisor.close()
    except (StartupError, OSError, subprocess.SubprocessError) as exc:
        message = (
            str(exc)
            if isinstance(exc, StartupError)
            else "Local startup failed; check prerequisites."
        )
        print(f"[TransLoka] {message}", file=sys.stderr)
        return 1
    finally:
        for number, handler in previous_handlers.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
