<#
.SYNOPSIS
    Install the CompChemKit skills into an agent's skills directory.

.DESCRIPTION
    Finds every methods/<skill>/ folder that contains a SKILL.md, plus the knowledge/ knowledge
    base (installed as one skill named by the `name:` field of knowledge/SKILL.md), and installs
    each into the destination skills directory (default: ~/.dsh/skills).

    The default action is a copy, which is the robust choice. -Link tries a directory junction
    first (no administrator rights needed, unlike a symlink) and falls back to a copy with a
    warning if the junction cannot be created.

    An existing skill directory in the destination is never deleted implicitly:
      * without -Force it is skipped with a warning;
      * with -Force the replacement is announced and you must confirm at the prompt.
    A non-interactive run therefore never deletes anything.

.PARAMETER Dest
    Destination skills directory. Default: ~/.dsh/skills

.PARAMETER Link
    Link each skill instead of copying it (directory junction, falling back to copy).

.PARAMETER Force
    Allow an existing skill directory to be replaced. Asks for confirmation.

.PARAMETER Help
    Show this help and exit.

.EXAMPLE
    .\install.ps1

.EXAMPLE
    .\install.ps1 -Dest D:\agent\skills -Link -Force
#>
[CmdletBinding()]
param(
    [string] $Dest = (Join-Path $HOME '.dsh/skills'),
    [switch] $Link,
    [switch] $Force,
    [Alias('?')]
    [switch] $Help
)

$ErrorActionPreference = 'Stop'

function Show-Usage {
    Write-Host @'
CompChemKit skill installer

Usage: .\install.ps1 [-Dest <dir>] [-Link] [-Force]

  -Dest <dir>   Install into <dir> (default: ~/.dsh/skills)
  -Link         Use a directory junction instead of a copy; falls back to copy on failure
  -Force        Allow replacing an existing skill directory (asks for confirmation)
  -?            Show this help

Every methods/<skill>/ folder containing a SKILL.md is installed, plus the knowledge/ knowledge
base as one skill (named by the `name:` field of knowledge/SKILL.md).
'@
}

if ($Help) {
    Show-Usage
    exit 0
}

$repoRoot = $PSScriptRoot
if ([string]::IsNullOrEmpty($repoRoot)) {
    $repoRoot = (Get-Location).ProviderPath
}

# ---- discover skills -------------------------------------------------------
# methods/<skill>/ is one skill per folder (folder name = skill name). knowledge/ is a single
# knowledge-base skill: its folder name is fixed ("knowledge"), so its skill name comes from the
# `name:` field of its SKILL.md.
$skillDirs = @()
$methodsDir = Join-Path $repoRoot 'methods'
if (Test-Path -LiteralPath $methodsDir -PathType Container) {
    foreach ($dir in @(Get-ChildItem -LiteralPath $methodsDir -Directory | Sort-Object Name)) {
        if (Test-Path -LiteralPath (Join-Path $dir.FullName 'SKILL.md') -PathType Leaf) {
            $skillDirs += [pscustomobject]@{ Path = $dir.FullName; Name = $dir.Name }
        }
    }
}
$knowledgeDir = Join-Path $repoRoot 'knowledge'
if (Test-Path -LiteralPath (Join-Path $knowledgeDir 'SKILL.md') -PathType Leaf) {
    $name = ''
    foreach ($line in Get-Content -LiteralPath (Join-Path $knowledgeDir 'SKILL.md') -Encoding utf8) {
        if ($line -match '^name:\s*(.+?)\s*$') { $name = $Matches[1]; break }
    }
    $name = $name.Trim('"').Trim("'")
    if ([string]::IsNullOrWhiteSpace($name)) {
        Write-Warning "knowledge/SKILL.md has no 'name:' field; installing it as 'knowledge'."
        $name = 'knowledge'
    }
    $skillDirs += [pscustomobject]@{ Path = $knowledgeDir; Name = $name }
}

if ($skillDirs.Count -eq 0) {
    Write-Warning "No skills found: no methods/*/SKILL.md and no knowledge/SKILL.md under $repoRoot."
    exit 1
}

# ---- prepare destination ---------------------------------------------------
$destFull = [System.IO.Path]::GetFullPath($Dest)
if (-not (Test-Path -LiteralPath $destFull -PathType Container)) {
    New-Item -ItemType Directory -Path $destFull -Force | Out-Null
    Write-Host "Created destination: $destFull"
}

# ---- install ---------------------------------------------------------------
$rows = @()
$skipped = @()

foreach ($dir in $skillDirs) {
    $name = $dir.Name
    $src = $dir.Path
    $target = Join-Path $destFull $name
    $action = 'copy'

    if (Test-Path -LiteralPath $target) {
        Write-Host "Existing target: $target"
        Write-Host "  would be replaced by: $src"
        if (-not $Force) {
            Write-Warning "Skipped '$name': target already exists (re-run with -Force to replace it)."
            $skipped += $name
            $rows += [pscustomobject]@{ Skill = $name; Action = 'skipped (exists)'; Destination = $target }
            continue
        }
        $answer = ''
        try {
            $answer = Read-Host "Delete and replace '$target'? [y/N]"
        } catch {
            $answer = ''
        }
        if ($answer -notmatch '^y(es)?$') {
            Write-Warning "Skipped '$name': replacement not confirmed; non-interactive runs never delete."
            $skipped += $name
            $rows += [pscustomobject]@{ Skill = $name; Action = 'skipped (no confirm)'; Destination = $target }
            continue
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }

    $done = $false
    if ($Link) {
        try {
            New-Item -ItemType Junction -Path $target -Target $src -ErrorAction Stop | Out-Null
            $action = 'junction'
            $done = $true
        } catch {
            Write-Warning "Junction failed for '$name' ($($_.Exception.Message)); falling back to copy."
        }
    }
    if (-not $done) {
        Copy-Item -LiteralPath $src -Destination $target -Recurse -Force
        $action = 'copy'
    }

    $rows += [pscustomobject]@{ Skill = $name; Action = $action; Destination = $target }
}

# ---- report ----------------------------------------------------------------
Write-Host ''
$rows | Format-Table -AutoSize -Property Skill, Action, Destination | Out-String -Width 200 | Write-Host
$installed = @($rows | Where-Object { $_.Action -ne 'skipped (exists)' -and $_.Action -ne 'skipped (no confirm)' }).Count
Write-Host "Installed $installed skill(s) into $destFull"
if ($skipped.Count -gt 0) {
    Write-Warning "Skipped $($skipped.Count) skill(s): $($skipped -join ', ')"
}
