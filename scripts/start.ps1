param(
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$setupScript = Join-Path $PSScriptRoot "setup-local.ps1"
. (Join-Path $PSScriptRoot "resolve-executable.ps1")

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

function Stop-StartedProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$RootProcessId
    )

    $processIds = @(Get-ProcessTreeIds $RootProcessId)
    [Array]::Reverse($processIds)
    foreach ($processId in $processIds) {
        if ($processId -eq $PID) {
            continue
        }
        Stop-Process -Id $processId -ErrorAction SilentlyContinue
    }
}

function Start-Component {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "[TransLoka] Starting $Name..."
    $process = Start-Process `
        -FilePath $Executable `
        -ArgumentList $Arguments `
        -WorkingDirectory $repositoryRoot `
        -NoNewWindow `
        -PassThru
    return [PSCustomObject]@{
        Name = $Name
        Process = $process
    }
}

& $setupScript
if ($CheckOnly) {
    Write-Host "[TransLoka] Validation-only check completed."
    return
}

$fingerprint = Get-RepositoryFingerprint $repositoryRoot
$stateFile = Join-Path ([System.IO.Path]::GetTempPath()) "transloka-dev-$fingerprint.json"
$stopFile = "$stateFile.stop"
if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
    throw "[TransLoka] A development process record already exists. Run scripts\stop.ps1 first."
}
Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue

$pnpmPath = Resolve-TransLokaExecutable "pnpm.cmd" "Install pnpm 11 and reopen PowerShell."
$uvPath = Resolve-TransLokaExecutable "uv.exe" "Install uv and reopen PowerShell."
$started = New-Object "System.Collections.Generic.List[object]"
$exitCode = 0

try {
    $started.Add(
        (Start-Component `
            "web on http://127.0.0.1:3000" `
            $pnpmPath `
            @("--filter", "@transloka/web", "dev", "--hostname", "127.0.0.1", "--port", "3000"))
    )
    $started.Add(
        (Start-Component `
            "API on http://127.0.0.1:8000" `
            $uvPath `
            @("run", "--no-sync", "transloka-api"))
    )
    $started.Add(
        (Start-Component `
            "local worker" `
            $uvPath `
            @("run", "--no-sync", "python", "-m", "transloka_worker"))
    )

    $state = [PSCustomObject]@{
        repository_fingerprint = $fingerprint
        coordinator_process_id = $PID
        processes = @(
            $started | ForEach-Object {
                [PSCustomObject]@{
                    name = $_.Name
                    process_id = $_.Process.Id
                    start_time_utc = $_.Process.StartTime.ToUniversalTime().ToString("o")
                }
            }
        )
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8

    $started | ForEach-Object {
        Write-Host "[TransLoka] $($_.Name) process ID: $($_.Process.Id)"
    }
    Write-Host "[TransLoka] Development stack is running. Press Ctrl+C to stop it."

    :monitor while ($true) {
        if (Test-Path -LiteralPath $stopFile -PathType Leaf) {
            Write-Host "[TransLoka] Stop requested."
            break monitor
        }
        foreach ($component in $started) {
            $component.Process.Refresh()
            if ($component.Process.HasExited) {
                if (Test-Path -LiteralPath $stopFile -PathType Leaf) {
                    break monitor
                }
                $childExitCode = $component.Process.ExitCode
                $exitCode = if ($childExitCode -eq 0) { 1 } else { $childExitCode }
                Write-Error "[TransLoka] $($component.Name) exited unexpectedly with code $childExitCode."
                break monitor
            }
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host "[TransLoka] Stopping development processes..."
    foreach ($component in $started) {
        Stop-StartedProcessTree $component.Process.Id
    }
    Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    Write-Host "[TransLoka] Development processes stopped."
}

exit $exitCode
