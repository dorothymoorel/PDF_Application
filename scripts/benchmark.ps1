[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $BenchmarkArgs
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$benchmarkPath = Join-Path $repoRoot "tests/performance/performance_benchmark.py"

uv run python $benchmarkPath @BenchmarkArgs
exit $LASTEXITCODE
