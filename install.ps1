[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Target,
    [switch]$DryRun,
    [switch]$OverwriteMechanical
)

$ErrorActionPreference = 'Stop'
$SourceRoot = $PSScriptRoot
$TargetSkills = @('add-zzzops-goal', 'execute-zzzops', 'migrate-to-zzzops', 'review-zzzops-policy', 'send-zzzops-feedback', 'suggest-zzzops-work')

function Stop-Install([string]$Message) {
    Write-Host "Cannot install yet: $Message"
    exit 2
}

if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
    Stop-Install 'Target is not a directory'
}
$TargetRoot = (Resolve-Path -LiteralPath $Target).Path
if (-not (Test-Path -LiteralPath (Join-Path $TargetRoot '.git'))) {
    Stop-Install 'Target has no .git entry'
}

function Get-FileDigest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Add-InstallPair([System.Collections.ArrayList]$Pairs, [string]$Source, [string]$Relative) {
    [void]$Pairs.Add([pscustomobject]@{
        Source = $Source
        Relative = $Relative.Replace('\', '/')
        Destination = Join-Path $TargetRoot ($Relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    })
}

function Get-InstallPairs {
    $pairs = [System.Collections.ArrayList]::new()
    $fixed = @(
        '.zzzops/rules/BACKENDS.md', '.zzzops/rules/BLOCKERS.md', '.zzzops/rules/CONTINUATION.md',
        '.zzzops/rules/EXECUTION_STRATEGY.md', '.zzzops/rules/FEEDBACK.md', '.zzzops/rules/GOAL_SYSTEM.md', '.zzzops/rules/INITIALIZATION.md',
        '.agents/zzzops/zzzops.py'
    )
    foreach ($relative in $fixed) {
        Add-InstallPair $pairs (Join-Path $SourceRoot ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))) $relative
    }
    Add-InstallPair $pairs (Join-Path $SourceRoot '.agents/.gitignore') '.agents/zzzops/.gitignore'
    $roots = @((Join-Path $SourceRoot '.agents/zzzops/templates/project-goals'))
    foreach ($name in $TargetSkills) { $roots += Join-Path $SourceRoot ".agents/skills/$name" }
    foreach ($root in $roots) {
        foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -File -Force) {
            if ($file.FullName -match '[\\/]__pycache__[\\/]' -or $file.Name.StartsWith('test_')) { continue }
            $relative = $file.FullName.Substring($SourceRoot.Length + 1).Replace('\', '/')
            Add-InstallPair $pairs $file.FullName $relative
        }
    }
    foreach ($name in $TargetSkills) {
        $skillRoot = Join-Path $SourceRoot ".agents/skills/$name"
        foreach ($file in Get-ChildItem -LiteralPath $skillRoot -Recurse -File -Force) {
            if ($file.FullName -match '[\\/]__pycache__[\\/]' -or $file.Name.StartsWith('test_')) { continue }
            $suffix = $file.FullName.Substring($skillRoot.Length + 1).Replace('\', '/')
            Add-InstallPair $pairs $file.FullName ".claude/skills/$name/$suffix"
        }
    }
    Add-InstallPair $pairs (Join-Path $SourceRoot '.agents/zzzops/templates/project-goals/ZZZOPS_GITIGNORE') '.zzzops/.gitignore'
    return @($pairs | Sort-Object Relative -Unique)
}

function Test-UnsafeReparsePoint([string]$Relative) {
    $parts = $Relative.Replace('\', '/').Split('/')
    $current = $TargetRoot
    foreach ($part in $parts) {
        $current = Join-Path $current $part
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
        }
    }
    return $false
}

function Get-IgnoredMechanicRoots {
    $ignored = [System.Collections.ArrayList]::new()
    $warning = $null
    $probes = [ordered]@{
        '.agents' = @('.agents/zzzops/zzzops.py', '.agents/skills/execute-zzzops/SKILL.md')
        '.claude' = @('.claude/skills/execute-zzzops/SKILL.md')
    }
    try {
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        foreach ($root in $probes.Keys) {
            foreach ($probe in $probes[$root]) {
                $null = & git -c "safe.directory=$TargetRoot" -C $TargetRoot check-ignore --no-index --quiet -- $probe 2>$null
                $code = $LASTEXITCODE
                if ($code -eq 0) { [void]$ignored.Add($root); break }
                if ($code -ne 1) {
                    $warning = "Could not verify project mechanic ignore rules: Git exited $code"
                    break
                }
            }
            if ($warning) { break }
        }
        $ErrorActionPreference = $previousErrorAction
    } catch {
        $ErrorActionPreference = $previousErrorAction
        $warning = 'Could not verify project mechanic ignore rules because Git is unavailable.'
    }
    return [pscustomobject]@{ Roots = @($ignored); Warning = $warning }
}

function New-InstallPlan {
    $actions = [System.Collections.ArrayList]::new()
    $errors = [System.Collections.ArrayList]::new()
    foreach ($pair in Get-InstallPairs) {
        if (Test-UnsafeReparsePoint $pair.Relative) {
            [void]$errors.Add("A managed path uses a symlink or junction: $($pair.Relative)")
            continue
        }
        $sourceHash = Get-FileDigest $pair.Source
        $expectedHash = Get-FileDigest $pair.Destination
        if (Test-Path -LiteralPath $pair.Destination -PathType Container) {
            $action = 'conflict'
            [void]$errors.Add("ZzzOps manages $($pair.Relative) as a file, but the target contains a directory there.")
        } elseif ($null -eq $expectedHash) {
            $action = 'create'
        } elseif ($expectedHash -eq $sourceHash) {
            $action = 'unchanged'
        } elseif ($OverwriteMechanical) {
            $action = 'overwrite'
        } else {
            $action = 'conflict'
            [void]$errors.Add("ZzzOps already manages $($pair.Relative), but its contents differ. Review it before using -OverwriteMechanical.")
        }
        [void]$actions.Add([pscustomobject]@{
            Relative = $pair.Relative; Source = $pair.Source; Destination = $pair.Destination
            Action = $action; SourceHash = $sourceHash; ExpectedHash = $expectedHash
        })
    }
    $ignore = Get-IgnoredMechanicRoots
    $signatureData = [pscustomobject]@{
        Files = @($actions | ForEach-Object { @($_.Relative, $_.Action, $_.SourceHash, $_.ExpectedHash) })
        Ignored = @($ignore.Roots)
        IgnoreWarning = $ignore.Warning
    }
    return [pscustomobject]@{
        Actions = @($actions); Errors = @($errors); Ignored = @($ignore.Roots); IgnoreWarning = $ignore.Warning
        Signature = ($signatureData | ConvertTo-Json -Compress -Depth 6)
    }
}

function Show-Preview($Plan) {
    Write-Host 'ZzzOps installation preview'
    Write-Host "Target: $TargetRoot"
    Write-Host 'This will install:'
    Write-Host '- tracked project skills for Codex and Claude Code'
    Write-Host '- shared workflow rules and the ZzzOps control CLI'
    Write-Host '- blank templates for project setup and TODO migration'
    $newCount = @($Plan.Actions | Where-Object Action -eq 'create').Count
    $updatedCount = @($Plan.Actions | Where-Object Action -eq 'overwrite').Count
    if ($newCount -or $updatedCount) { Write-Host "Planned changes: $newCount new, $updatedCount updated." }
    else { Write-Host 'Planned changes: ZzzOps is already up to date.' }
    if ($Plan.Ignored.Count) {
        $names = (($Plan.Ignored | ForEach-Object { "$_/" }) -join ' and ')
        Write-Host "Warning: Git ignores required ZzzOps project mechanics under $names."
        Write-Host 'Remove those ignore rules before committing so collaborators receive the installed workflows.'
    }
    if ($Plan.IgnoreWarning) { Write-Host "Warning: $($Plan.IgnoreWarning)" }
    foreach ($error in $Plan.Errors) { Write-Host "Cannot install yet: $error" }
}

function Restore-Writes([array]$Written) {
    foreach ($entry in $Written) {
        if (Test-Path -LiteralPath $entry.Destination -PathType Leaf) { Remove-Item -LiteralPath $entry.Destination -Force }
        if ($entry.HadBefore) {
            $parent = Split-Path -Parent $entry.Destination
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            Copy-Item -LiteralPath $entry.Backup -Destination $entry.Destination -Force
        }
    }
}

function Apply-Plan($Plan) {
    $backupRoot = Join-Path ([IO.Path]::GetTempPath()) ("zzzops-install-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
    $written = [System.Collections.ArrayList]::new()
    try {
        foreach ($action in $Plan.Actions | Where-Object { $_.Action -in @('create', 'overwrite') }) {
            if ((Get-FileDigest $action.Destination) -ne $action.ExpectedHash) { throw "Target changed after confirmation: $($action.Relative)" }
            $backup = Join-Path $backupRoot ($action.Relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
            $hadBefore = Test-Path -LiteralPath $action.Destination -PathType Leaf
            if ($hadBefore) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
                Copy-Item -LiteralPath $action.Destination -Destination $backup -Force
            }
            [void]$written.Add([pscustomobject]@{ Destination = $action.Destination; Backup = $backup; HadBefore = $hadBefore })
            $parent = Split-Path -Parent $action.Destination
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
            $temporary = Join-Path $parent ('.zzzops-install-' + [guid]::NewGuid().ToString('N') + '.tmp')
            Copy-Item -LiteralPath $action.Source -Destination $temporary -Force
            Move-Item -LiteralPath $temporary -Destination $action.Destination -Force
        }
    } catch {
        Restore-Writes @($written)
        Write-Host "Installation failed and was rolled back: $($_.Exception.Message)"
        return $false
    } finally {
        Remove-Item -LiteralPath $backupRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    return $true
}

$plan = New-InstallPlan
Show-Preview $plan
if ($plan.Errors.Count) { exit 2 }
if ($DryRun) {
    Write-Host 'No files were changed.'
    exit 0
}
$pendingChanges = @($plan.Actions | Where-Object { $_.Action -in @('create', 'overwrite') }).Count
if (-not $pendingChanges) {
    Write-Host 'ZzzOps is already up to date. No further action is necessary.'
    exit 0
}
$answer = Read-Host 'Install these changes? [y/N]'
if ($answer -notmatch '^(?i:y|yes)$') {
    Write-Host 'Installation cancelled; no files were changed.'
    exit 0
}
$confirmedPlan = New-InstallPlan
if ($confirmedPlan.Errors.Count -or $confirmedPlan.Signature -ne $plan.Signature) {
    Write-Host 'The target changed after the preview. Run the installer again; no files were changed.'
    exit 2
}
if (-not (Apply-Plan $confirmedPlan)) { exit 2 }
Write-Host 'ZzzOps is installed. Open the target repository in Codex or Claude Code; restart or reopen the harness if the new skills are not discovered. Begin with review-zzzops-policy.'
exit 0
