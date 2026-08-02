[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Target,
    [switch]$DryRun,
    [switch]$OverwriteMechanical,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$engine = Join-Path $PSScriptRoot '.agents/zzzops/installer.py'
$arguments = @($engine, $Target)
if ($DryRun) { $arguments += '--dry-run' }
if ($OverwriteMechanical) { $arguments += '--overwrite-mechanical' }
if ($Yes) { $arguments += '--yes' }
& python @arguments
exit $LASTEXITCODE
