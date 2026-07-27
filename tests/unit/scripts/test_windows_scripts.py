import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[3]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"
EXPECTED_SCRIPTS = (
    "setup-local.ps1",
    "start.ps1",
    "stop.ps1",
)
RESOLVER_SCRIPT = SCRIPTS_DIRECTORY / "resolve-executable.ps1"
ALL_SCRIPTS = (*EXPECTED_SCRIPTS, RESOLVER_SCRIPT.name)


def _powershell() -> str:
    executable = shutil.which("powershell.exe")
    if executable is None:
        pytest.skip("Windows PowerShell is unavailable.")
    return executable


def _quote_for_powershell(path: Path) -> str:
    return str(path).replace("'", "''")


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )


def test_expected_scripts_exist_and_parse() -> None:
    errors: list[str] = []
    for script_name in ALL_SCRIPTS:
        script = SCRIPTS_DIRECTORY / script_name
        assert script.is_file()
        command = (
            "$tokens = $null; $errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{_quote_for_powershell(script)}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | Out-String | Write-Error; exit 1 }"
        )
        result = _run_powershell(command)
        if result.returncode != 0:
            errors.append(f"{script_name}: {result.stderr}")
    assert errors == []


def test_scripts_use_safe_baseline_and_repository_relative_paths() -> None:
    for script_name in EXPECTED_SCRIPTS:
        contents = (SCRIPTS_DIRECTORY / script_name).read_text(encoding="utf-8")
        assert "Set-StrictMode -Version Latest" in contents
        assert '$ErrorActionPreference = "Stop"' in contents
        assert "$PSScriptRoot" in contents
        assert "Join-Path" in contents
        assert str(REPOSITORY_ROOT) not in contents


def test_scripts_exclude_unsafe_commands_and_bindings() -> None:
    combined = "\n".join(
        (SCRIPTS_DIRECTORY / script_name).read_text(encoding="utf-8") for script_name in ALL_SCRIPTS
    )
    forbidden = (
        "Invoke-Expression",
        "0.0.0.0",
        "Set-ExecutionPolicy",
        "-Verb RunAs",
        "Stop-Process -Name",
        "taskkill /IM",
        "pip install",
        "uv add",
        "pnpm add",
    )
    for value in forbidden:
        assert value not in combined
    assert re.search(r"(?<!p)\bnpm install\b", combined) is None


def test_prerequisite_checker_requires_approved_versions_and_files() -> None:
    contents = (SCRIPTS_DIRECTORY / "setup-local.ps1").read_text(encoding="utf-8")

    assert re.search(r"\^v24", contents)
    assert '"3.12"' in contents
    assert "uvPath run --no-sync python" in contents
    assert "pnpm-workspace.yaml" in contents
    assert "apps/web/package.json" in contents
    assert "transloka_api/main.py" in contents
    assert "transloka_worker/__main__.py" in contents


def test_start_script_uses_supported_local_entrypoints() -> None:
    contents = (SCRIPTS_DIRECTORY / "start.ps1").read_text(encoding="utf-8")

    assert "@transloka/web" in contents
    assert '"--hostname", "127.0.0.1"' in contents
    assert '"--port", "3000"' in contents
    assert '"transloka-api"' in contents
    assert '"-m", "transloka_worker"' in contents
    assert '"--no-sync"' in contents
    assert "Stop-Process -Id" in contents
    assert 'Resolve-TransLokaExecutable "pnpm.cmd"' in contents
    assert 'Resolve-TransLokaExecutable "uv.exe"' in contents
    assert ").Source" not in contents


@pytest.mark.parametrize(
    ("sources", "expected"),
    (
        (r"C:\Program Files\pnpm\pnpm.cmd", r"C:\Program Files\pnpm\pnpm.cmd"),
        (
            "C:\\first\\pnpm.cmd', 'C:\\second\\pnpm.cmd",
            r"C:\first\pnpm.cmd",
        ),
    ),
)
def test_executable_resolver_returns_first_match_as_string(sources: str, expected: str) -> None:
    command = (
        "function Get-Command { "
        "param($Name, $CommandType, [switch]$All, $ErrorAction); "
        f"@('{sources}') | ForEach-Object {{ [PSCustomObject]@{{ Source = $_ }} }} "
        "}; "
        f". '{_quote_for_powershell(RESOLVER_SCRIPT)}'; "
        "$result = Resolve-TransLokaExecutable 'pnpm.cmd' 'Install pnpm.'; "
        "[Console]::WriteLine($result.GetType().FullName); "
        "[Console]::WriteLine($result)"
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["System.String", expected]


def test_executable_resolver_reports_missing_tool() -> None:
    command = (
        "function Get-Command { @() }; "
        f". '{_quote_for_powershell(RESOLVER_SCRIPT)}'; "
        "try { "
        "Resolve-TransLokaExecutable 'pnpm.cmd' 'Install pnpm and reopen PowerShell.'; "
        "exit 2 "
        "} catch { "
        "[Console]::WriteLine($_.Exception.Message); exit 0 "
        "}"
    )
    result = _run_powershell(command)

    assert result.returncode == 0, result.stderr
    assert "Required tool 'pnpm.cmd' was not found." in result.stdout
    assert "Install pnpm and reopen PowerShell." in result.stdout


def test_check_only_works_outside_repository(tmp_path: Path) -> None:
    script = SCRIPTS_DIRECTORY / "start.ps1"
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-CheckOnly",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Development prerequisites are ready." in result.stdout
    assert "Validation-only check completed." in result.stdout


def test_missing_prerequisite_returns_nonzero(tmp_path: Path) -> None:
    script = SCRIPTS_DIRECTORY / "setup-local.ps1"
    command = f"$env:PATH = ''; & '{_quote_for_powershell(script)}'"
    environment = os.environ.copy()
    result = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Required tool" in (result.stdout + result.stderr)
