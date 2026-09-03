param(
    [string]$RunnerDir = 'C:\actions-runner-cleanwindow',
    [switch]$ElevatedStage,
    [switch]$RestoreService
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$launcherName = 'START_CLEAN_WINDOW_RUNNER_HIDDEN.vbs'

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-CodexCommand {
    foreach ($name in @('codex', 'codex.cmd', 'codex.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $(if ($command.Path) { $command.Path } else { $command.Source }) }
    }
    return $null
}

function Get-RunnerService {
    $marker = Join-Path $RunnerDir '.service'
    if (Test-Path -LiteralPath $marker) {
        $name = (Get-Content -LiteralPath $marker -Raw -ErrorAction SilentlyContinue).Trim()
        if ($name) {
            $service = Get-Service -Name $name -ErrorAction SilentlyContinue
            if ($service) { return $service }
        }
    }
    $normalized = [IO.Path]::GetFullPath($RunnerDir).TrimEnd('\')
    $candidate = Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Where-Object {
        ([string]$_.PathName).IndexOf($normalized, [StringComparison]::OrdinalIgnoreCase) -ge 0
    } | Select-Object -First 1
    if ($candidate) { return Get-Service -Name $candidate.Name -ErrorAction SilentlyContinue }
    return $null
}

function Get-RunnerProcesses {
    $root = [IO.Path]::GetFullPath($RunnerDir)
    $matches = @()
    foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction SilentlyContinue)) {
        try {
            if (-not $process.ExecutablePath) { continue }
            $exe = [IO.Path]::GetFullPath($process.ExecutablePath)
            if ($exe.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { $matches += $process }
        } catch {}
    }
    return @($matches)
}

function Write-HiddenRunnerVbs([string]$Destination) {
    $runCmd = Join-Path $RunnerDir 'run.cmd'
    $escapedRoot = $RunnerDir.Replace('"', '""')
    $escapedRun = $runCmd.Replace('"', '""')
    $content = @(
        'Option Explicit',
        'Dim shell',
        'Set shell = CreateObject("WScript.Shell")',
        ('shell.CurrentDirectory = "{0}"' -f $escapedRoot),
        ('shell.Run Chr(34) & "{0}" & Chr(34), 0, False' -f $escapedRun)
    ) -join "`r`n"
    [IO.File]::WriteAllText($Destination, $content + "`r`n", (New-Object Text.UTF8Encoding($false)))
}

function Invoke-ElevatedStage([switch]$Restore) {
    $args = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $PSCommandPath + '"'),
        '-RunnerDir', ('"' + $RunnerDir.Replace('"', '""') + '"'),
        '-ElevatedStage'
    )
    if ($Restore) { $args += '-RestoreService' }
    $process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Normal -ArgumentList ($args -join ' ') -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Elevated Runner service stage failed with exit code $($process.ExitCode)." }
}

if ($ElevatedStage) {
    if (-not (Test-IsAdministrator)) { throw 'ElevatedStage requires administrator rights.' }
    $service = Get-RunnerService
    if (-not $service) { exit 0 }
    if ($RestoreService) {
        Set-Service -Name $service.Name -StartupType Automatic
        if ((Get-Service -Name $service.Name).Status -ne 'Running') { Start-Service -Name $service.Name }
        exit 0
    }
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $service.Name -Force
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
    }
    Set-Service -Name $service.Name -StartupType Disabled
    exit 0
}

$runCmd = Join-Path $RunnerDir 'run.cmd'
if (-not (Test-Path -LiteralPath $runCmd) -or -not (Test-Path -LiteralPath (Join-Path $RunnerDir '.runner'))) {
    Write-Host ''
    Write-Host 'Clean Window self-hosted Runner is not registered on this PC yet.' -ForegroundColor Yellow
    Write-Host "Expected Runner folder: $RunnerDir"
    Write-Host 'Register one repository Runner for p4147691/clean-window-toggle with label: cleanwindow-local'
    Write-Host 'After registration, run this setup again normally (not as administrator).'
    exit 2
}

$startupVbs = $null
$launcherVbs = $null
$serviceStageCompleted = $false
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($identity -match '^NT AUTHORITY\\') { throw "Run this setup from the normal Windows user that owns Codex: $identity" }
    if (Test-IsAdministrator) { throw 'Run this setup normally, not as administrator.' }

    $codex = Resolve-CodexCommand
    if (-not $codex) { throw 'Official Codex CLI is not on PATH for this Windows user. No cross-user/profile fallback is allowed.' }
    Write-Host "Windows user : $identity"
    Write-Host "Codex CLI    : $codex"
    & $codex --version
    if ($LASTEXITCODE -ne 0) { throw 'codex --version failed.' }
    & $codex login status
    if ($LASTEXITCODE -ne 0) { throw 'Codex is not logged in for this same Windows user.' }

    $service = Get-RunnerService
    if ($service) {
        Invoke-ElevatedStage
        $serviceStageCompleted = $true
    }

    if (@(Get-RunnerProcesses).Count -eq 0) {
        $startupDir = [Environment]::GetFolderPath('Startup')
        if ([string]::IsNullOrWhiteSpace($startupDir)) { throw 'Could not resolve this Windows user Startup folder.' }
        if (-not (Test-Path -LiteralPath $startupDir)) { New-Item -ItemType Directory -Path $startupDir -Force | Out-Null }

        $launcherDir = Join-Path $env:LOCALAPPDATA 'CleanWindowCodexBridge'
        New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
        $launcherVbs = Join-Path $launcherDir $launcherName
        $startupVbs = Join-Path $startupDir $launcherName
        Write-HiddenRunnerVbs -Destination $launcherVbs
        Copy-Item -LiteralPath $launcherVbs -Destination $startupVbs -Force
        Start-Process -FilePath "$env:WINDIR\System32\wscript.exe" -ArgumentList @('//B', '//Nologo', ('"' + $launcherVbs + '"')) | Out-Null
        Start-Sleep -Seconds 5
    }

    if (@(Get-RunnerProcesses).Count -eq 0) { throw 'Clean Window user-session Runner did not remain running.' }

    Write-Host ''
    Write-Host 'SUCCESS: Clean Window Codex Bridge Runner is ready.' -ForegroundColor Green
    Write-Host '- Runner runs hidden in this normal logged-in Windows user session.'
    Write-Host '- Startup entry belongs to this same Windows user.'
    Write-Host '- Codex PATH/login are used only from this same user session.'
    Write-Host '- No auth.json, USERPROFILE, HOME, or CODEX_HOME was copied or overridden.'
}
catch {
    Write-Host "SETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    if ($startupVbs) { Remove-Item -LiteralPath $startupVbs -Force -ErrorAction SilentlyContinue }
    if ($launcherVbs) { Remove-Item -LiteralPath $launcherVbs -Force -ErrorAction SilentlyContinue }
    if ($serviceStageCompleted) {
        try { Invoke-ElevatedStage -Restore } catch { Write-Warning "Automatic service rollback failed: $($_.Exception.Message)" }
    }
    throw
}
