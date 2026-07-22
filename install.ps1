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
$InstallManifestRelative = '.agents/zzzops/INSTALL_MANIFEST'

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
$SourceRevision = (& git -C $SourceRoot rev-parse HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $SourceRevision -notmatch '^[0-9a-f]{40,64}$') {
    Stop-Install 'Source revision could not be read from the ZzzOps base repository'
}
$SourceVersion = (& git -c core.excludesFile=NUL -C $SourceRoot describe --tags --always --long --dirty 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $SourceVersion -notmatch '^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$') {
    Stop-Install 'Source version could not be read from the ZzzOps base repository'
}

function Get-FileDigest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $digest = (& git hash-object --no-filters -- $Path 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^[0-9a-f]{40,64}$') { throw "Could not hash $Path" }
    return $digest
}

function Read-InstallManifest {
    $path = Join-Path $TargetRoot ($InstallManifestRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [pscustomobject]@{ Exists = $false; Valid = $true; Revision = $null; Version = $null; Files = @{}; Path = $path }
    }
    $lines = @(Get-Content -LiteralPath $path -Encoding UTF8)
    $files = @{}
    $revision = $null
    $version = $null
    $valid = $lines.Count -ge 2 -and $lines[0] -eq 'zzzops-install-manifest-v1'
    foreach ($line in @($lines | Select-Object -Skip 1)) {
        $fields = $line -split "`t", 3
        if ($fields.Count -eq 2 -and $fields[0] -eq 'revision' -and $fields[1] -match '^[0-9a-f]{40,64}$' -and -not $revision) {
            $revision = $fields[1]
        } elseif ($fields.Count -eq 2 -and $fields[0] -eq 'version' -and $fields[1] -match '^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$' -and -not $version) {
            $version = $fields[1]
        } elseif ($fields.Count -eq 3 -and $fields[0] -eq 'file' -and $fields[1] -match '^[0-9a-f]{40,64}$' -and $fields[2] -and -not $files.ContainsKey($fields[2])) {
            $files[$fields[2]] = $fields[1]
        } else {
            $valid = $false
        }
    }
    if (-not $revision) { $valid = $false }
    return [pscustomobject]@{ Exists = $true; Valid = $valid; Revision = $revision; Version = $version; Files = $files; Path = $path }
}

function Get-ManifestText([array]$Actions) {
    $lines = [System.Collections.ArrayList]::new()
    [void]$lines.Add('zzzops-install-manifest-v1')
    [void]$lines.Add("revision`t$SourceRevision")
    [void]$lines.Add("version`t$SourceVersion")
    foreach ($action in @($Actions | Sort-Object Relative)) {
        [void]$lines.Add("file`t$($action.SourceHash)`t$($action.Relative)")
    }
    return (($lines -join "`n") + "`n")
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
        '.agents/zzzops/zzzops.py', '.agents/zzzops/policy.py', 'LICENSE'
    )
    foreach ($relative in $fixed) {
        $destination = if ($relative -eq 'LICENSE') { '.agents/zzzops/LICENSE' } else { $relative }
        Add-InstallPair $pairs (Join-Path $SourceRoot ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))) $destination
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
    $manifest = Read-InstallManifest
    if ($manifest.Exists -and -not $manifest.Valid -and -not $OverwriteMechanical) {
        [void]$errors.Add("The installed ZzzOps manifest is invalid. Review $InstallManifestRelative before using -OverwriteMechanical.")
    }
    foreach ($pair in Get-InstallPairs) {
        if (Test-UnsafeReparsePoint $pair.Relative) {
            [void]$errors.Add("A managed path uses a symlink or junction: $($pair.Relative)")
            continue
        }
        $sourceHash = Get-FileDigest $pair.Source
        $expectedHash = Get-FileDigest $pair.Destination
        $installedHash = if ($manifest.Valid -and $manifest.Files.ContainsKey($pair.Relative)) { $manifest.Files[$pair.Relative] } else { $null }
        if (Test-Path -LiteralPath $pair.Destination -PathType Container) {
            $action = 'conflict'
            [void]$errors.Add("ZzzOps manages $($pair.Relative) as a file, but the target contains a directory there.")
        } elseif (-not $manifest.Exists -and $null -eq $expectedHash) {
            $action = 'create'
        } elseif (-not $manifest.Exists -and $expectedHash -eq $sourceHash) {
            $action = 'unchanged'
        } elseif (-not $manifest.Exists -and $OverwriteMechanical) {
            $action = 'overwrite'
        } elseif (-not $manifest.Exists) {
            $action = 'conflict'
            [void]$errors.Add("ZzzOps already manages $($pair.Relative), but no installed baseline proves it is safe to upgrade. Review it before using -OverwriteMechanical.")
        } elseif (-not $manifest.Valid) {
            $action = if ($OverwriteMechanical) { if ($null -eq $expectedHash) { 'create' } else { 'overwrite' } } else { 'conflict' }
        } elseif ($null -eq $installedHash -and $null -eq $expectedHash) {
            $action = 'create'
        } elseif ($null -eq $installedHash -or $expectedHash -ne $installedHash) {
            if ($OverwriteMechanical) { $action = 'overwrite' }
            else {
                $action = 'conflict'
                [void]$errors.Add("ZzzOps-managed file $($pair.Relative) is locally divergent from its installed baseline. Review it before using -OverwriteMechanical.")
            }
        } elseif ($expectedHash -eq $sourceHash) {
            $action = 'unchanged'
        } else {
            $action = 'upgrade'
        }
        [void]$actions.Add([pscustomobject]@{
            Relative = $pair.Relative; Source = $pair.Source; Destination = $pair.Destination
            Action = $action; SourceHash = $sourceHash; ExpectedHash = $expectedHash; InstalledHash = $installedHash
        })
    }
    $ignore = Get-IgnoredMechanicRoots
    $signatureData = [pscustomobject]@{
        Files = @($actions | ForEach-Object { @($_.Relative, $_.Action, $_.SourceHash, $_.ExpectedHash) })
        ManifestExpectedHash = Get-FileDigest $manifest.Path
        ManifestRevision = $manifest.Revision
        ManifestVersion = $manifest.Version
        SourceRevision = $SourceRevision
        SourceVersion = $SourceVersion
        Ignored = @($ignore.Roots)
        IgnoreWarning = $ignore.Warning
    }
    $manifestNeedsUpdate = [bool]($manifest.Exists -and $manifest.Valid -and ($manifest.Revision -ne $SourceRevision -or $manifest.Version -ne $SourceVersion))
    return [pscustomobject]@{
        Actions = @($actions); Errors = @($errors); Ignored = @($ignore.Roots); IgnoreWarning = $ignore.Warning
        Manifest = $manifest; ManifestExpectedHash = Get-FileDigest $manifest.Path
        ManifestNeedsUpdate = $manifestNeedsUpdate
        IsUpgrade = [bool]($manifest.Exists -and $manifest.Valid -and ($manifestNeedsUpdate -or @($actions | Where-Object Action -in @('create', 'upgrade')).Count))
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
    $sourceDisplay = "$SourceVersion ($($SourceRevision.Substring(0, 7)))"
    $installedDisplay = if (-not $Plan.Manifest.Exists) { 'not installed' } elseif (-not $Plan.Manifest.Valid -or -not $Plan.Manifest.Revision) { 'invalid manifest' } elseif ($Plan.Manifest.Version) { "$($Plan.Manifest.Version) ($($Plan.Manifest.Revision.Substring(0, 7)))" } else { "revision $($Plan.Manifest.Revision.Substring(0, 7))" }
    Write-Host "ZzzOps version: $installedDisplay -> $sourceDisplay."
    $newCount = @($Plan.Actions | Where-Object Action -eq 'create').Count
    $updatedCount = @($Plan.Actions | Where-Object Action -in @('upgrade', 'overwrite')).Count
    if ($Plan.IsUpgrade) {
        Write-Host "Upgrade available: $($Plan.Manifest.Revision.Substring(0, 7)) -> $($SourceRevision.Substring(0, 7))."
        Write-Host 'Managed files to update:'
        foreach ($action in @($Plan.Actions | Where-Object Action -in @('create', 'upgrade'))) { Write-Host "- $($action.Relative)" }
        Write-Host 'Changes since installed version:'
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $subjects = @(& git -C $SourceRoot log --no-merges --format='- %s' --max-count=8 "$($Plan.Manifest.Revision)..$SourceRevision" 2>$null)
        $historyCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorAction
        if ($historyCode -eq 0 -and $subjects.Count) { foreach ($subject in $subjects) { Write-Host $subject } }
        else { Write-Host '- revision history is unavailable; inspect the managed-file list above' }
    } elseif ($newCount -or $updatedCount) {
        Write-Host "Planned changes: $newCount new, $updatedCount updated."
    } elseif (-not $Plan.Errors.Count) {
        Write-Host 'Planned changes: ZzzOps is already up to date.'
    }
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
        if ((Get-FileDigest $Plan.Manifest.Path) -ne $Plan.ManifestExpectedHash) { throw "Target changed after confirmation: $InstallManifestRelative" }
        foreach ($action in $Plan.Actions | Where-Object { $_.Action -in @('create', 'upgrade', 'overwrite') }) {
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
        $manifestDestination = $Plan.Manifest.Path
        if ((Get-FileDigest $manifestDestination) -ne $Plan.ManifestExpectedHash) { throw "Target changed after confirmation: $InstallManifestRelative" }
        $manifestBackup = Join-Path $backupRoot ($InstallManifestRelative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $manifestHadBefore = Test-Path -LiteralPath $manifestDestination -PathType Leaf
        if ($manifestHadBefore) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $manifestBackup) -Force | Out-Null
            Copy-Item -LiteralPath $manifestDestination -Destination $manifestBackup -Force
        }
        [void]$written.Add([pscustomobject]@{ Destination = $manifestDestination; Backup = $manifestBackup; HadBefore = $manifestHadBefore })
        $manifestParent = Split-Path -Parent $manifestDestination
        New-Item -ItemType Directory -Path $manifestParent -Force | Out-Null
        $manifestTemporary = Join-Path $manifestParent ('.zzzops-install-' + [guid]::NewGuid().ToString('N') + '.tmp')
        [IO.File]::WriteAllText($manifestTemporary, (Get-ManifestText $Plan.Actions), [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $manifestTemporary -Destination $manifestDestination -Force
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
$pendingChanges = @($plan.Actions | Where-Object { $_.Action -in @('create', 'upgrade', 'overwrite') }).Count + [int]$plan.ManifestNeedsUpdate
if (-not $pendingChanges) {
    Write-Host 'ZzzOps is already up to date. No further action is necessary.'
    exit 0
}
$prompt = if ($plan.IsUpgrade) { 'Upgrade ZzzOps? [y/N]' } else { 'Install these changes? [y/N]' }
$answer = Read-Host $prompt
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
if ($confirmedPlan.IsUpgrade) { Write-Host 'ZzzOps was upgraded.' }
else { Write-Host 'ZzzOps is installed. Open the target repository in Codex or Claude Code; restart or reopen the harness if the new skills are not discovered. Begin with review-zzzops-policy.' }
exit 0
