Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

function Get-RepositoryFingerprint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Path.ToLowerInvariant())
        $hash = $sha256.ComputeHash($bytes)
        return (($hash[0..7] | ForEach-Object { $_.ToString("x2") }) -join "")
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-ProcessTreeIds {
    param(
        [Parameter(Mandatory = $true)]
        [int]$RootProcessId
    )

    $snapshot = @(
        Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue |
            Select-Object ProcessId, ParentProcessId
    )
    $pending = New-Object "System.Collections.Generic.Queue[int]"
    $result = New-Object "System.Collections.Generic.List[int]"
    $pending.Enqueue($RootProcessId)

    while ($pending.Count -gt 0) {
        $parentId = $pending.Dequeue()
        if ($result.Contains($parentId)) {
            continue
        }
        $result.Add($parentId)
        foreach ($child in $snapshot | Where-Object { $_.ParentProcessId -eq $parentId }) {
            $pending.Enqueue([int]$child.ProcessId)
        }
    }
    return $result.ToArray()
}

function Test-TrackedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Entry
    )

    try {
        $process = Get-Process -Id ([int]$Entry.process_id) -ErrorAction Stop
        $expectedStart = [DateTime]::Parse(
            [string]$Entry.start_time_utc,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).ToUniversalTime()
        $actualStart = $process.StartTime.ToUniversalTime()
        return [Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -lt 2
    }
    catch {
        return $false
    }
}

function Stop-TrackedProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Entry
    )

    if (-not (Test-TrackedProcess $Entry)) {
        Write-Host "[TransLoka] Skipping stale process record for $($Entry.name)."
        return
    }

    $processIds = @(Get-ProcessTreeIds ([int]$Entry.process_id))
    [Array]::Reverse($processIds)
    foreach ($processId in $processIds) {
        if ($processId -eq $PID) {
            continue
        }
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
    }
    Write-Host "[TransLoka] Stopped $($Entry.name)."
}

$fingerprint = Get-RepositoryFingerprint $repositoryRoot
$stateFile = Join-Path ([System.IO.Path]::GetTempPath()) "transloka-dev-$fingerprint.json"
$stopFile = "$stateFile.stop"
if (-not (Test-Path -LiteralPath $stateFile -PathType Leaf)) {
    Write-Host "[TransLoka] No recorded development processes are running."
    return
}

$state = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
if ($state.repository_fingerprint -ne $fingerprint) {
    throw "[TransLoka] The development process record does not belong to this repository."
}

Write-Host "[TransLoka] Stopping recorded development processes..."
Set-Content -LiteralPath $stopFile -Value "stop" -Encoding ASCII
try {
    @($state.processes) | ForEach-Object {
        Stop-TrackedProcessTree $_
    }
}
finally {
    Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
}
Write-Host "[TransLoka] Stop request completed."
