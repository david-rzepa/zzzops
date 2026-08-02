[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Target,
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$Restore
)

$ErrorActionPreference = 'Stop'
$engine = Join-Path $PSScriptRoot '.agents/zzzops/installer.py'
$python = Get-Command python -ErrorAction SilentlyContinue
$pythonPrefix = @()
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    $pythonPrefix = @('-3')
}
if (-not $python) {
    Write-Host 'Cannot install yet: Python 3.10 or newer is required.'
    exit 2
}
$null = & $python.Source @pythonPrefix -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Cannot install yet: Python 3.10 or newer is required.'
    exit 2
}
$arguments = @($engine, $Target)
if ($DryRun) { $arguments += '--dry-run' }
if ($Yes) { $arguments += '--yes' }
if ($Restore) { $arguments += '--restore' }
& $python.Source @pythonPrefix @arguments
exit $LASTEXITCODE
