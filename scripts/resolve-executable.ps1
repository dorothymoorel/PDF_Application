function Resolve-TransLokaExecutable {
    [OutputType([string])]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Correction
    )

    $command = Get-Command `
        -Name $Name `
        -CommandType Application `
        -All `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        throw "[TransLoka] Required tool '$Name' was not found. $Correction"
    }
    return [string]$command.Source
}
