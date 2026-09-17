import importlib.util
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

if sys.platform != "linux":
    pytest.skip("Linux launcher contract", allow_module_level=True)

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts/start_local.py"


@pytest.fixture
def launcher(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("start_local", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path / "Trial Data"))
    monkeypatch.delenv("TRANSLOKA_API_HOST", raising=False)
    monkeypatch.delenv("TRANSLOKA_API_PORT", raising=False)
    monkeypatch.delenv("TRANSLOKA_WEB_ORIGINS", raising=False)
    return module


@pytest.fixture
def prerequisites(launcher: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(launcher.shutil, "which", lambda name: name)

    def version(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, "v24.0.0" if command[0] == "node" else "11.0.0"
        )

    monkeypatch.setattr(launcher.subprocess, "run", version)
    return launcher


def test_check_only_has_no_side_effects(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check-only"])
    assert prerequisites.main() == 0
    assert not Path(os.environ["TRANSLOKA_DATA_DIR"]).exists()


@pytest.mark.parametrize("value", ["", "relative", "/", str(ROOT / "runtime")])
def test_unsafe_data_root_is_rejected(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", value)
    with pytest.raises(prerequisites.StartupError):
        prerequisites.check_prerequisites()


def test_symlink_into_repository_is_rejected(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    link = tmp_path / "linked-repository"
    link.symlink_to(ROOT, target_is_directory=True)
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(link / "runtime"))
    with pytest.raises(prerequisites.StartupError):
        prerequisites.check_prerequisites()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TRANSLOKA_API_HOST", "0.0.0.0"),
        ("TRANSLOKA_API_PORT", "8123"),
        ("TRANSLOKA_WEB_ORIGINS", "http://localhost:3000"),
    ],
)
def test_incompatible_api_configuration_fails_before_migration(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    migrate = Mock()
    monkeypatch.setattr(prerequisites.Supervisor, "migrate", migrate)
    assert prerequisites.main() == 1
    migrate.assert_not_called()


def test_missing_tool_is_actionable(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prerequisites.shutil, "which", lambda _name: None)
    with pytest.raises(prerequisites.StartupError, match="Required tool 'node'"):
        prerequisites.check_prerequisites()


def test_broken_workspace_import_is_actionable_and_sanitized(
    prerequisites: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        prerequisites.importlib, "import_module", Mock(side_effect=ImportError("private detail"))
    )
    assert prerequisites.main() == 1
    error = capsys.readouterr().err
    assert "uv sync --locked" in error
    assert "private detail" not in error


def test_occupied_port_does_not_kill_existing_listener(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setattr(launcher, "PORTS", (port,))
        with pytest.raises(launcher.StartupError, match=f"Port {port} is occupied"):
            launcher.check_ports()
        assert listener.getsockname() == ("127.0.0.1", port)


def test_duplicate_launcher_is_rejected(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl

    data = prerequisites.check_prerequisites()
    data.mkdir(parents=True)
    migrate = Mock()
    monkeypatch.setattr(prerequisites.Supervisor, "migrate", migrate)
    with (data / ".local-stack.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert prerequisites.main() == 1
    migrate.assert_not_called()


def test_lock_file_symlink_is_rejected(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = prerequisites.check_prerequisites()
    data.mkdir(parents=True)
    target = tmp_path / "unrelated"
    target.write_bytes(b"unchanged")
    (data / ".local-stack.lock").symlink_to(target)
    migrate = Mock()
    monkeypatch.setattr(prerequisites.Supervisor, "migrate", migrate)
    assert prerequisites.main() == 1
    assert target.read_bytes() == b"unchanged"
    migrate.assert_not_called()


def test_prepare_only_migrates_idempotently_from_another_directory(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--prepare-only"])
    monkeypatch.setattr(launcher, "check_ports", lambda: None)
    for _attempt in range(2):
        assert launcher.main() == 0
    with sqlite3.connect(Path(os.environ["TRANSLOKA_DATA_DIR"]) / "database/transloka.db") as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0017_backups",)
        assert db.execute("SELECT count(*) FROM projects").fetchone() == (0,)


def test_failed_migration_starts_no_components(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prerequisites, "check_ports", lambda: None)
    process = Mock(pid=1234, returncode=1)
    process.poll.return_value = 1
    start = Mock(return_value=process)
    run = Mock()
    close = Mock()
    monkeypatch.setattr(prerequisites.Supervisor, "start", start)
    monkeypatch.setattr(prerequisites.Supervisor, "run_components", run)
    monkeypatch.setattr(prerequisites.Supervisor, "close", close)
    assert prerequisites.main() == 1
    assert start.call_args.args[0] == "migration"
    run.assert_not_called()
    close.assert_called_once()


def test_child_exit_and_partial_start_failure_clean_up(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prerequisites, "check_ports", lambda: None)
    monkeypatch.setattr(prerequisites.Supervisor, "migrate", lambda _self: True)
    process = Mock(pid=1234)
    process.poll.return_value = 0
    close = Mock()
    monkeypatch.setattr(prerequisites.Supervisor, "close", close)
    popen = Mock(return_value=process)
    monkeypatch.setattr(prerequisites.subprocess, "Popen", popen)
    assert prerequisites.main() == 1
    assert popen.call_count == 3
    assert all(call.kwargs["start_new_session"] for call in popen.call_args_list)
    web_command = popen.call_args.args[0]
    assert web_command[-4:] == ["--hostname", "127.0.0.1", "--port", "3000"]
    assert "--" not in web_command
    close.assert_called_once()

    popen.side_effect = [process, OSError("private failure detail")]
    close.reset_mock()
    assert prerequisites.main() == 1
    close.assert_called_once()


def test_shutdown_only_signals_owned_process_groups(launcher: ModuleType) -> None:
    supervisor = launcher.Supervisor()
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
    )
    child = supervisor.start("test child", [sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        supervisor.request_stop(signal.SIGTERM, None)
        assert supervisor.stop_requested
        supervisor.close()
        assert child.poll() is not None
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)


def test_shutdown_escalates_even_when_group_leader_exited(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = launcher.Supervisor()
    process = Mock(pid=1234)
    process.poll.return_value = 0
    supervisor.children.append(("web", process))
    send = Mock(return_value=True)
    monkeypatch.setattr(supervisor, "_signal_group", send)
    monkeypatch.setattr(launcher, "SHUTDOWN_TIMEOUT", 0)
    supervisor.close()
    assert send.call_args_list[0].args == (1234, signal.SIGTERM)
    assert send.call_args_list[-1].args == (1234, signal.SIGKILL)
    process.wait.assert_called_once()


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("Timed out waiting for test subprocess.")
        time.sleep(0.02)


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_real_signal_stops_the_launcher_and_its_children(tmp_path: Path, stop_signal: int) -> None:
    driver = f"""
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('launcher', {str(SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path({str(tmp_path)!r})
module.check_prerequisites = lambda: root / 'data'
module.check_ports = lambda: None
module.Supervisor.migrate = lambda self: True
original_start = module.Supervisor.start
def start(self, name, command):
    process = original_start(self, name, [sys.executable, '-c', 'import time; time.sleep(60)'])
    (root / name).write_text(str(process.pid))
    return process
module.Supervisor.start = start
sys.argv = ['start_local.py']
raise SystemExit(module.main())
"""
    process = subprocess.Popen([sys.executable, "-c", driver], start_new_session=True)
    pids: list[int] = []
    try:
        wait_until(lambda: (tmp_path / "web").exists())
        pids = [int((tmp_path / name).read_text()) for name in ("API", "worker", "web")]
        process.send_signal(stop_signal)
        assert process.wait(timeout=5) == 0
        for pid in pids:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
    finally:
        for pid in [process.pid, *pids]:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def test_real_grandchild_is_killed_after_leader_exits(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ready = tmp_path / "ready"
    grandchild = (
        "import os, signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    leader = f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {grandchild!r}])"
    supervisor = launcher.Supervisor()
    monkeypatch.setattr(launcher, "SHUTDOWN_TIMEOUT", 0.2)
    process = supervisor.start("leader", [sys.executable, "-c", leader])
    try:
        wait_until(ready.exists)
        assert process.wait(timeout=5) == 0
        pid = int(ready.read_text())
        supervisor.close()

        def stopped() -> bool:
            status = Path(f"/proc/{pid}/stat")
            return not status.exists() or status.read_text().split()[2] == "Z"

        wait_until(stopped)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def test_interrupted_migration_cleans_up_and_releases_lock(tmp_path: Path) -> None:
    import fcntl

    driver = f"""
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('launcher', {str(SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path({str(tmp_path)!r})
module.check_prerequisites = lambda: root / 'data'
module.check_ports = lambda: None
original_start = module.Supervisor.start
def start(self, name, command):
    process = original_start(self, name, [sys.executable, '-c', 'import time; time.sleep(60)'])
    (root / name).write_text(str(process.pid))
    return process
module.Supervisor.start = start
sys.argv = ['start_local.py']
raise SystemExit(module.main())
"""
    process = subprocess.Popen([sys.executable, "-c", driver], start_new_session=True)
    migration_pid: int | None = None
    try:
        wait_until(lambda: (tmp_path / "migration").exists())
        migration_pid = int((tmp_path / "migration").read_text())
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(migration_pid, 0)
        assert not any((tmp_path / name).exists() for name in ("API", "worker", "web"))
        with (tmp_path / "data/.local-stack.lock").open("r+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for pid in [process.pid, *([migration_pid] if migration_pid else [])]:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def test_ollama_opt_in_requires_installed_executable(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--with-ollama", "--check-only"])
    monkeypatch.delenv("TRANSLOKA_OLLAMA_EXECUTABLE", raising=False)
    assert prerequisites.main() == 1


def test_ollama_opt_in_pins_local_host_and_disables_cloud(
    prerequisites: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--with-ollama", "--check-only"])
    monkeypatch.setenv("TRANSLOKA_OLLAMA_EXECUTABLE", sys.executable)
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11434")
    monkeypatch.setenv("OLLAMA_NO_CLOUD", "0")
    assert prerequisites.main() == 0
    assert os.environ["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert os.environ["OLLAMA_NO_CLOUD"] == "1"
    assert not Path(os.environ["TRANSLOKA_DATA_DIR"]).exists()


def test_ollama_is_supervised_without_implicit_model_download(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = launcher.Supervisor()
    process = Mock(pid=1234)
    process.poll.return_value = 1
    popen = Mock(return_value=process)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)
    with pytest.raises(launcher.StartupError, match="Ollama"):
        supervisor.run_components("/local/ollama")
    assert popen.call_args_list[0].args[0] == ["/local/ollama", "serve"]
    assert popen.call_count == 4
    assert all(call.kwargs["start_new_session"] for call in popen.call_args_list)
