Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

function Get-RequiredApplication {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Correction
    )

    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        throw "[TransLoka] Required tool '$Name' was not found. $Correction"
    }
    return $command.Source
}

function Assert-RepositoryFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $path = Join-Path $repositoryRoot $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "[TransLoka] Required repository file is missing: $RelativePath"
    }
}

Write-Host "[TransLoka] Checking development prerequisites..."

$nodePath = Get-RequiredApplication "node.exe" "Install Node.js 24 and reopen PowerShell."
$pnpmPath = Get-RequiredApplication "pnpm.cmd" "Install pnpm 11 and reopen PowerShell."
$uvPath = Get-RequiredApplication "uv.exe" "Install uv and reopen PowerShell."

$nodeVersion = (& $nodePath --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch "^v24(\.|$)") {
    throw "[TransLoka] Node.js 24 is required; detected '$nodeVersion'."
}

$pnpmVersion = (& $pnpmPath --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pnpmVersion -notmatch "^11(\.|$)") {
    throw "[TransLoka] pnpm 11 is required; detected '$pnpmVersion'."
}

@(
    "pnpm-workspace.yaml"
    "pnpm-lock.yaml"
    "package.json"
    "pyproject.toml"
    "uv.lock"
    "apps/web/package.json"
    "services/api/src/transloka_api/main.py"
    "services/worker/src/transloka_worker/__main__.py"
) | ForEach-Object {
    Assert-RepositoryFile $_
}

if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot "node_modules") -PathType Container)) {
    throw "[TransLoka] Node dependencies are missing. Run 'pnpm install --frozen-lockfile' explicitly."
}
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".venv") -PathType Container)) {
    throw "[TransLoka] Python environment is missing. Run 'uv sync --locked' explicitly."
}

Push-Location -LiteralPath $repositoryRoot
try {
    $pythonVersion = (
        & $uvPath run --no-sync python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1 |
            Out-String
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.12") {
        throw "[TransLoka] Python 3.12 through uv is required; detected '$pythonVersion'."
    }

    & $uvPath run --no-sync python -c "import transloka_api, transloka_worker" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "[TransLoka] Python workspace packages are unavailable. Run 'uv sync --locked' explicitly."
    }
}
finally {
    Pop-Location
}

Write-Host "[TransLoka] Development prerequisites are ready."
