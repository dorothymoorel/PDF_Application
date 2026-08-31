param(
    [string]$DataRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "resolve-executable.ps1")

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = $env:TRANSLOKA_DATA_DIR
}
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "[TransLoka] LOCALAPPDATA is unavailable; pass -DataRoot with an absolute path."
    }
    $DataRoot = Join-Path $env:LOCALAPPDATA "TransLoka"
}

if (-not [System.IO.Path]::IsPathFullyQualified($DataRoot)) {
    throw "[TransLoka] DataRoot must be an absolute local path."
}

$modelCache = Join-Path $DataRoot "cache\paddleocr"
$uvPath = Resolve-TransLokaExecutable "uv.exe" "Install uv and reopen PowerShell."

Write-Host "[TransLoka] Preparing the local CPU OCR bundle (about 13 MB of model weights)."
Write-Host "[TransLoka] The download is user-initiated and will be stored outside the repository: $modelCache"

Push-Location -LiteralPath $repositoryRoot
try {
    & $uvPath run --no-sync python -m transloka_documents.ocr.provision --model-cache-dir $modelCache
    if ($LASTEXITCODE -ne 0) {
        throw "[TransLoka] Local PaddleOCR model provisioning failed."
    }
}
finally {
    Pop-Location
}

Write-Host "[TransLoka] Local PaddleOCR model bundle is ready. Start the application with scripts\start.ps1."
