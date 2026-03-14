param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [int]$PollIntervalSeconds = 600,

    [int]$StalledThresholdMinutes = 30,

    [switch]$RunOnce,

    [switch]$SkipProcessCheck,

    [string]$ProcessNameOverride = 'matlab'
)

$ErrorActionPreference = 'Stop'

function Get-LatestFile {
    param(
        [string]$Path,
        [string]$Filter
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    Get-ChildItem -LiteralPath $Path -Filter $Filter -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-HeartbeatSummary {
    param([string]$RootPath)

    $heartbeatFile = Join-Path $RootPath 'status\heartbeat_latest.json'
    if (-not (Test-Path -LiteralPath $heartbeatFile)) {
        return $null
    }

    $heartbeat = Get-Content -LiteralPath $heartbeatFile -Raw | ConvertFrom-Json
    $updatedAt = (Get-Item -LiteralPath $heartbeatFile).LastWriteTime
    if ($heartbeat.updated_at) {
        try {
            $updatedAt = [datetime]::Parse($heartbeat.updated_at)
        } catch {
            $updatedAt = (Get-Item -LiteralPath $heartbeatFile).LastWriteTime
        }
    }

    $currentFrame = 0
    if ($null -ne $heartbeat.current_frame) {
        $currentFrame = [int]$heartbeat.current_frame
    }

    $totalFrames = 0
    if ($null -ne $heartbeat.total_frames) {
        $totalFrames = [int]$heartbeat.total_frames
    }

    [pscustomobject]@{
        source          = 'heartbeat'
        status          = [string]$heartbeat.status
        step            = [string]$heartbeat.step
        current_frame   = $currentFrame
        total_frames    = $totalFrames
        last_checkpoint = [string]$heartbeat.last_checkpoint
        matlab_pid      = if ($null -ne $heartbeat.matlab_pid) { [int]$heartbeat.matlab_pid } else { 0 }
        hostname        = [string]$heartbeat.hostname
        last_update     = $updatedAt
        note            = ''
        output_path     = [string]$heartbeat.output_path
    }
}

function Get-ProgressSummary {
    param([string]$RootPath)

    $progressFile = Join-Path $RootPath 'progress\progress_latest.csv'
    if (-not (Test-Path -LiteralPath $progressFile)) {
        return $null
    }

    $rows = Import-Csv -LiteralPath $progressFile
    [pscustomobject]@{
        current_frame = $rows.Count
        last_update   = (Get-Item -LiteralPath $progressFile).LastWriteTime
    }
}

function Get-CheckpointSummary {
    param([string]$RootPath)

    $checkpoint = Get-LatestFile -Path $RootPath -Filter 'checkpoint_*.mat'
    if (-not $checkpoint) {
        return $null
    }

    $frame = 0
    if ($checkpoint.Name -match 'checkpoint_(\d+)\.mat') {
        $frame = [int]$Matches[1]
    }

    [pscustomobject]@{
        path        = $checkpoint.FullName
        name        = $checkpoint.Name
        current_frame = $frame
        last_update = $checkpoint.LastWriteTime
    }
}

function Get-LogSummary {
    param([string]$RootPath)

    $logDir = Join-Path $RootPath 'logs'
    $logFile = Get-LatestFile -Path $logDir -Filter 'pipeline_log_*.txt'
    if (-not $logFile) {
        return $null
    }

    $tail = Get-Content -LiteralPath $logFile.FullName -Tail 400
    $frameMatch = $tail | Select-String -Pattern '--- Frame\s+(\d+)\s*/\s*(\d+) ---' | Select-Object -Last 1
    $stepMatch = $tail | Select-String -Pattern 'STEP\s+([0-5]):' | Select-Object -Last 1
    $completed = Select-String -Path $logFile.FullName -Pattern 'Pipeline completed' -SimpleMatch -Quiet

    $currentFrame = 0
    $totalFrames = 0
    if ($frameMatch) {
        $frameText = [string]$frameMatch.Matches[0].Value
        if ($frameText -match '--- Frame\s+(\d+)\s*/\s*(\d+) ---') {
            $currentFrame = [int]$Matches[1]
            $totalFrames = [int]$Matches[2]
        }
    }

    if ($totalFrames -eq 0) {
        $framesLine = Select-String -Path $logFile.FullName -Pattern 'Frames to analyze:\s+(\d+)' | Select-Object -First 1
        if ($framesLine -and $framesLine.Line -match 'Frames to analyze:\s+(\d+)') {
            $totalFrames = [int]$Matches[1]
        }
    }

    $step = ''
    if ($stepMatch -and $stepMatch.Line -match 'STEP\s+([0-5]):') {
        $step = 'STEP ' + $Matches[1]
    } elseif ($currentFrame -gt 0) {
        $step = 'STEP 4'
    }

    [pscustomobject]@{
        path          = $logFile.FullName
        current_frame = $currentFrame
        total_frames  = $totalFrames
        step          = $step
        completed     = [bool]$completed
        last_update   = $logFile.LastWriteTime
    }
}

function Test-ProcessById {
    param(
        [int]$ProcessId,
        [switch]$SkipCheck
    )

    if ($SkipCheck) {
        return $null
    }

    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Test-MatlabRunning {
    param(
        [string]$ProcessName = 'matlab',
        [switch]$SkipCheck
    )

    if ($SkipCheck) {
        return $null
    }

    return [bool](Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
}

function Get-RunSummary {
    param(
        [string]$RootPath,
        [int]$StalledThresholdMinutes,
        [switch]$SkipProcessCheck
    )

    $heartbeat = Get-HeartbeatSummary -RootPath $RootPath
    if ($heartbeat) {
        $status = $heartbeat.status
        $ageMinutes = ((Get-Date) - $heartbeat.last_update).TotalMinutes
        $heartbeatPid = [int]$heartbeat.matlab_pid
        $pidRunning = $null
        if ($heartbeatPid -gt 0) {
            $pidRunning = Test-ProcessById -ProcessId $heartbeatPid -SkipCheck:$SkipProcessCheck
        }
        if ($status -eq 'running' -and $ageMinutes -ge $StalledThresholdMinutes) {
            if (($null -ne $pidRunning) -and (-not $pidRunning) -and $heartbeatPid -gt 0) {
                $status = 'crashed'
            } else {
                $status = 'stalled'
            }
        }

        $note = $heartbeat.note
        if ($heartbeatPid -gt 0) {
            if ($note) {
                $note += ' '
            }
            $note += "pid=$heartbeatPid"
        }

        return [pscustomobject]@{
            status          = $status
            step            = $heartbeat.step
            current_frame   = $heartbeat.current_frame
            total_frames    = $heartbeat.total_frames
            last_checkpoint = $heartbeat.last_checkpoint
            last_update     = $heartbeat.last_update
            output_path     = if ($heartbeat.output_path) { $heartbeat.output_path } else { $RootPath }
            note            = $note
            source          = 'heartbeat'
        }
    }

    $progress = Get-ProgressSummary -RootPath $RootPath
    $checkpoint = Get-CheckpointSummary -RootPath $RootPath
    $log = Get-LogSummary -RootPath $RootPath
    $matlabRunning = Test-MatlabRunning -ProcessName $ProcessNameOverride -SkipCheck:$SkipProcessCheck

    $currentFrame = 0
    $totalFrames = 0
    $step = ''
    $lastCheckpoint = ''
    $timestamps = @()

    if ($progress) {
        $currentFrame = [int]$progress.current_frame
        $timestamps += $progress.last_update
    }
    if ($checkpoint) {
        if ($checkpoint.current_frame -gt $currentFrame) {
            $currentFrame = [int]$checkpoint.current_frame
        }
        $lastCheckpoint = $checkpoint.path
        $timestamps += $checkpoint.last_update
    }
    if ($log) {
        if ($log.current_frame -gt $currentFrame) {
            $currentFrame = [int]$log.current_frame
        }
        if ($log.total_frames -gt 0) {
            $totalFrames = [int]$log.total_frames
        }
        if ($log.step) {
            $step = $log.step
        }
        $timestamps += $log.last_update
    }
    if (-not $step -and $currentFrame -gt 0) {
        $step = 'STEP 4'
    }

    $lastUpdate = $null
    if ($timestamps.Count -gt 0) {
        $lastUpdate = ($timestamps | Sort-Object -Descending | Select-Object -First 1)
    }

    $status = 'unknown'
    if ($log -and $log.completed) {
        $status = 'completed'
    } elseif ($lastUpdate) {
        $ageMinutes = ((Get-Date) - $lastUpdate).TotalMinutes
        if ($ageMinutes -lt $StalledThresholdMinutes) {
            $status = 'running'
        } elseif (($null -ne $matlabRunning) -and (-not $matlabRunning)) {
            $status = 'crashed'
        } else {
            $status = 'stalled'
        }
    }

    [pscustomobject]@{
        status          = $status
        step            = $step
        current_frame   = $currentFrame
        total_frames    = $totalFrames
        last_checkpoint = $lastCheckpoint
        last_update     = $lastUpdate
        output_path     = $RootPath
        note            = 'heartbeat missing, using log fallback'
        source          = 'fallback'
    }
}

function Format-Age {
    param([datetime]$Timestamp)

    if (-not $Timestamp) {
        return 'n/a'
    }

    $span = (Get-Date) - $Timestamp
    if ($span.TotalMinutes -lt 1) {
        return ([math]::Round($span.TotalSeconds)).ToString() + 's'
    }
    if ($span.TotalHours -lt 1) {
        return ([math]::Round($span.TotalMinutes, 1)).ToString() + 'm'
    }
    return ([math]::Round($span.TotalHours, 1)).ToString() + 'h'
}

function Format-Frame {
    param(
        [int]$CurrentFrame,
        [int]$TotalFrames
    )

    if ($TotalFrames -gt 0) {
        return "$CurrentFrame/$TotalFrames"
    }
    if ($CurrentFrame -gt 0) {
        return "$CurrentFrame/-"
    }
    return 'n/a'
}

function Format-RunSummary {
    param($Summary)

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $frameText = Format-Frame -CurrentFrame $Summary.current_frame -TotalFrames $Summary.total_frames
    $ageText = Format-Age -Timestamp $Summary.last_update
    $checkpointText = if ($Summary.last_checkpoint) { Split-Path -Leaf $Summary.last_checkpoint } else { 'none' }
    $stepText = if ($Summary.step) { $Summary.step } else { 'unknown' }

    $line = "[${timestamp}] status=$($Summary.status) step=$stepText frame=$frameText checkpoint=$checkpointText last_update_age=$ageText output=$($Summary.output_path)"
    if ($Summary.note) {
        $line += " note=$($Summary.note)"
    }
    return $line
}

$resolvedOutputPath = (Resolve-Path -LiteralPath $OutputPath).Path

while ($true) {
    $summary = Get-RunSummary -RootPath $resolvedOutputPath -StalledThresholdMinutes $StalledThresholdMinutes -SkipProcessCheck:$SkipProcessCheck
    Write-Output (Format-RunSummary -Summary $summary)

    if ($summary.status -in @('completed', 'paused', 'failed', 'crashed', 'stalled')) {
        if ($summary.status -in @('completed', 'paused')) {
            exit 0
        }
        exit 1
    }

    if ($RunOnce) {
        exit 0
    }

    Start-Sleep -Seconds $PollIntervalSeconds
}
