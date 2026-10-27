<#
.SYNOPSIS
    Local watchdog for a long-running / multi-stage compute chain on an HPC cluster.

.DESCRIPTION
    It ONLY WATCHES. It never submits anything and never decides anything: a
    failed or non-converged job needs judgement, so the follow-up belongs to the
    agent/user.

    Mechanism
      * runs on the LOCAL machine and only calls `ssh <alias> squeue / sacct`;
        it consumes nothing on the cluster (no CPU, no queue slot)
      * discovers which jobs to watch from `squeue` using the regexes in the
        watch config, so resubmitted jobs / new attempts / new systems are picked
        up automatically - you never edit job ids
      * exits as soon as a watched job leaves the queue, printing which job
        ended, its sacct state, what is still running, and optionally the output
        of a status command executed on the cluster

    IMPORTANT: to receive a completion notification from the agent harness this
    must be started as a TRACKED background job (the harness notifies when the
    process it started exits). A child process started from inside the script is
    not tracked, so the watchdog CANNOT relaunch itself - the agent relaunches it
    in the same turn in which it was woken up. Each launch therefore covers one
    "event", which is what a layered workflow needs.

    Where the connection details come from (first match wins)
      1. `host_alias` / `remote_user` in the watch config   (-Config)
      2. platform entry in the hpc-cluster config          (-HpcConfig / -Platform)
         default path: ~/.compchemkit/config.json

.PARAMETER Config
    Watch config JSON (patterns, poll_seconds, max_hours, status_command).
    Default: watch_jobs_config.json next to this script.

.PARAMETER Platform
    Platform name inside the hpc-cluster config file.

.PARAMETER HpcConfig
    Path to the hpc-cluster config file. Default: ~/.compchemkit/config.json

.EXAMPLE
    pwsh -File watch_jobs.ps1 -Status
    pwsh -File watch_jobs.ps1 -WakeOnlyOnTrouble          # start in background
    pwsh -File watch_jobs.ps1 -Config jobs.json -Platform mycluster -PollSeconds 300

.NOTES
    exit codes: 0 = a watched job left the queue (read the report)
                2 = timeout, nothing happened
                3 = nothing matched the patterns / cannot reach the cluster
#>
param(
    [string]$Config = (Join-Path $PSScriptRoot 'watch_jobs_config.json'),
    [string]$Platform = '',
    [string]$HpcConfig = (Join-Path $HOME '.compchemkit/config.json'),
    [switch]$Status,
    [int]$PollSeconds = 0,
    [double]$MaxHours = 0,
    [switch]$WakeOnlyOnTrouble
)

$ErrorActionPreference = 'Continue'

# keep the run log next to the watch config (i.e. inside the project), not in the skill dir
$logDir = Split-Path -Parent $Config
if (-not $logDir) { $logDir = $PSScriptRoot }
$log = Join-Path $logDir 'watch_jobs.log'

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

if (-not (Test-Path $Config)) { Say "watch config not found: $Config"; exit 3 }
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
if ($PollSeconds -le 0) { $PollSeconds = [int]($cfg.poll_seconds | ForEach-Object { if ($_) { $_ } else { 600 } }) }
if ($MaxHours -le 0) { $MaxHours = [double]($cfg.max_hours | ForEach-Object { if ($_) { $_ } else { 72 } }) }
$patterns = @($cfg.patterns)

# ---------------------------------------------------------------- connection info
$hostAlias = $cfg.host_alias
$user = $cfg.remote_user
if ((-not $hostAlias) -or (-not $user)) {
    if (-not (Test-Path $HpcConfig)) {
        Say "no host_alias/remote_user in $Config and no hpc config at $HpcConfig"
        Say "run:  python scripts/hpc_config.py init --platform <name> --host <host> --user <user>"
        exit 3
    }
    $hpc = Get-Content $HpcConfig -Raw | ConvertFrom-Json
    $name = $Platform
    if (-not $name) { $name = $hpc.default_platform }
    if (-not $name) { Say "hpc config has no default_platform and -Platform was not given"; exit 3 }
    $entry = $hpc.platforms.PSObject.Properties[$name]
    if (-not $entry) { Say "platform '$name' not found in $HpcConfig"; exit 3 }
    $plat = $entry.Value
    if (-not $hostAlias) { $hostAlias = if ($plat.ssh_alias) { $plat.ssh_alias } else { $name } }
    if (-not $user) { $user = $plat.user }
    Say "platform '$name' -> $user@$hostAlias"
}
if (-not $user) { Say "cannot determine the remote user"; exit 3 }

function Remote($cmd) {
    return (ssh -o ConnectTimeout=25 -o ServerAliveInterval=15 $hostAlias $cmd 2>$null)
}

$queueCmd = "squeue -u $user -o '%.10i %.12j %.9P %.2t %.10M %.20R'"

function StatusBlock {
    $out = @()
    $out += Remote $queueCmd
    if ($cfg.status_command) {
        $out += ""
        $out += Remote $cfg.status_command
    }
    return ($out -join "`n")
}

# ---------------------------------------------------------------- one-shot mode
if ($Status) {
    Write-Output "=== queue ==="
    Remote $queueCmd
    if ($cfg.status_command) {
        Write-Output ""
        Write-Output "=== status command ==="
        Remote $cfg.status_command
    }
    exit 0
}

# ------------------------------------------------------- discover what to watch
$queueRaw = Remote "squeue -u $user -h -o '%i|%j|%T'"
if (-not $queueRaw) { Say "cannot reach the cluster or no jobs in the queue"; exit 3 }

$watched = [ordered]@{}
foreach ($line in $queueRaw) {
    $f = $line -split '\|'
    if ($f.Count -lt 3) { continue }
    foreach ($p in $patterns) {
        if ($f[1] -match $p) { $watched[$f[0]] = $f[1]; break }
    }
}
if ($watched.Count -eq 0) { Say "no job matched the watch patterns: $($patterns -join ', ')"; exit 3 }

$ids = $watched.Keys -join ','
$mode = if ($WakeOnlyOnTrouble) { "trouble or all done" } else { "any job leaving the queue" }
Say "watchdog started: $($watched.Count) jobs ($ids)"
Say "poll ${PollSeconds}s, max ${MaxHours}h, wakes on: $mode"

# --------------------------------------------------------------------- waiting
$deadline = (Get-Date).AddHours($MaxHours)
while ((Get-Date) -lt $deadline) {
    $raw = Remote @"
squeue -u $user -h -o '%i|%T|%M'
echo '@@@'
sacct -j $ids --noheader --parsable2 --format=JobID,JobName,State,ExitCode,Elapsed 2>/dev/null | grep -v '\.'
"@
    if (-not $raw) { Start-Sleep -Seconds $PollSeconds; continue }
    $parts = ($raw -join "`n") -split '@@@'

    $queue = @{}
    foreach ($l in ($parts[0] -split "`n")) {
        if ($l -match '^(\d+)\|(\S+)\|(\S+)') { $queue[$Matches[1]] = $Matches[2] }
    }
    $final = @{}
    foreach ($l in ($parts[1] -split "`n")) {
        if ($l -match '^(\d+)\|([^|]*)\|([^|]*)\|([^|]*)\|') {
            $final[$Matches[1]] = [pscustomobject]@{ name = $Matches[2]; state = $Matches[3]; exit = $Matches[4] }
        }
    }

    $gone = @(); $bad = @(); $cancelled = @(); $inQueue = 0
    foreach ($id in $watched.Keys) {
        if ($queue.ContainsKey($id)) { $inQueue++; continue }
        $gone += $id
        $f = $final[$id]
        if (-not $f) { $bad += $id; continue }
        if ($f.state -like 'COMPLETED*' -and $f.exit -eq '0:0') { continue }
        # A deliberate `scancel` (e.g. resubmitting with new settings) is NOT
        # trouble: it always shows up as CANCELLED by <uid>.
        if ($f.state -like 'CANCELLED*') { $cancelled += $id; continue }
        $bad += $id
    }

    $fire = $false
    if (-not $WakeOnlyOnTrouble -and $gone.Count -gt 0) { $fire = $true }
    if ($WakeOnlyOnTrouble -and ($bad.Count -gt 0 -or $inQueue -eq 0)) { $fire = $true }

    if ($fire) {
        if ($bad.Count -gt 0) { Say "EVENT: abnormal ending -> $($bad -join ', ')" }
        elseif ($inQueue -eq 0) { Say "EVENT: every watched job finished" }
        else { Say "EVENT: $($gone.Count) job(s) left the queue -> $($gone -join ', ')" }
        if ($cancelled.Count -gt 0) { Say "note: deliberately cancelled (ignored) -> $($cancelled -join ', ')" }

        Write-Output ""
        Write-Output "================ JOB FINISHED ================"
        foreach ($g in $gone) { Write-Output ("  ended: {0}  {1}" -f $g, $watched[$g]) }
        Write-Output ""
        Write-Output "sacct:"
        Write-Output ($parts[1] -join "`n")
        Write-Output ""
        Write-Output "still queued / running:"
        $any = $false
        foreach ($id in $watched.Keys) {
            if ($queue.ContainsKey($id)) {
                Write-Output ("  {0,-8} {1,-24} {2}" -f $id, $watched[$id], $queue[$id]); $any = $true
            }
        }
        if (-not $any) { Write-Output "  (nothing left in the queue)" }
        if ($cfg.status_command) {
            Write-Output ""
            Write-Output "status:"
            Remote $cfg.status_command
        }
        Write-Output "=============================================="
        exit 0
    }
    Start-Sleep -Seconds $PollSeconds
}

Say "TIMEOUT after $MaxHours h - no watched job changed state"
exit 2
