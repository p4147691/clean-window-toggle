param(
    [Parameter(Mandatory = $true)]
    [string]$RequestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-CodexCommand {
    foreach ($name in @('codex', 'codex.cmd', 'codex.exe')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $(if ($command.Path) { $command.Path } else { $command.Source }) }
    }
    return $null
}

function Select-ReasoningEffort($request) {
    $allowed = @('low', 'medium', 'high', 'xhigh')
    $explicit = ([string]$request.effort).ToLowerInvariant()
    if ($explicit -and $allowed -contains $explicit) { return $explicit }

    $mode = ([string]$request.mode).ToLowerInvariant()
    $task = [string]$request.task
    $constraintCount = @($request.constraints).Count
    $acceptanceCount = @($request.acceptance).Count
    if ($task -match '(?i)repeated failure|multiple failed attempts|반복 실패|여러 차례 실패') { return 'xhigh' }
    if ($task.Length -gt 1400 -or $constraintCount -ge 6 -or $acceptanceCount -ge 6) { return 'high' }
    if ($mode -eq 'inspect' -and $task.Length -lt 900) { return 'low' }
    return 'medium'
}

function Invoke-Git([string[]]$Arguments, [string]$SafeDirectory, [string]$AuthHeader = $null) {
    $args = @('-c', "safe.directory=$SafeDirectory")
    if ($AuthHeader) { $args += @('-c', "http.extraheader=$AuthHeader") }
    $args += $Arguments
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git failed: git $($Arguments -join ' ')" }
}

if (-not (Test-Path -LiteralPath $RequestPath)) { throw "Codex bridge request not found: $RequestPath" }
$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$request.project -ne 'CleanWindow') { throw "Unexpected project in request: $($request.project)" }
if ([string]$request.requested_by -ne 'chatgpt') { throw 'Codex bridge only accepts requested_by=chatgpt.' }
if (-not $request.task -or [string]::IsNullOrWhiteSpace([string]$request.task)) { throw 'Codex bridge request task is empty.' }
if ($request.fast_mode -eq $true) { throw 'Fast mode is forbidden unless the user explicitly authorizes a bridge policy change.' }

$mode = ([string]$request.mode).ToLowerInvariant()
if (@('inspect', 'implement', 'test') -notcontains $mode) { throw "Unsupported bridge mode: $mode" }
$effort = Select-ReasoningEffort $request
$sandbox = if ($mode -eq 'implement') { 'workspace-write' } else { 'read-only' }

$codex = Resolve-CodexCommand
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if (-not $codex) { throw "Official Codex CLI is not on PATH for Runner account ($identity). No cross-user/profile fallback is allowed." }
Write-Host "BRIDGE_RUNNER_ACCOUNT=$identity"
Write-Host "BRIDGE_CODEX=$codex"
& $codex --version
if ($LASTEXITCODE -ne 0) { throw 'codex --version failed.' }
& $codex login status
if ($LASTEXITCODE -ne 0) { throw "Codex login is not valid for the same Runner account: $identity" }

$repo = (Get-Location).Path
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw "Bridge checkout is not a Git repository: $repo" }
$token = $env:GITHUB_TOKEN
if ([string]::IsNullOrWhiteSpace($token)) { throw 'GITHUB_TOKEN is unavailable.' }
$authBytes = [Text.Encoding]::ASCII.GetBytes("x-access-token:$token")
$authHeader = 'AUTHORIZATION: basic ' + [Convert]::ToBase64String($authBytes)

$runKey = "$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
$resultBranch = "codex/result-$runKey"
$workspace = Join-Path $env:RUNNER_TEMP "clean-window-codex-$runKey"
$outputDir = Join-Path $env:RUNNER_TEMP "clean-window-codex-output-$runKey"
$workspaceSafe = $workspace.Replace('\\', '/')
$repoSafe = $repo.Replace('\\', '/')
$summaryPath = Join-Path $outputDir 'codex_last_message.txt'
$eventsPath = Join-Path $outputDir 'codex_events.jsonl'
if (Test-Path -LiteralPath $workspace) { throw "Isolated workspace already exists unexpectedly: $workspace" }
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

Write-Host "BRIDGE_EFFORT=$effort"
Write-Host "BRIDGE_SANDBOX=$sandbox"
Write-Host 'BRIDGE_FAST_MODE=disabled'
Write-Host "BRIDGE_RESULT_BRANCH=$resultBranch"

try {
    Invoke-Git @('fetch', 'origin', 'main') $repoSafe $authHeader
    Invoke-Git @('worktree', 'add', '-b', $resultBranch, $workspace, 'origin/main') $repoSafe

    $constraints = @($request.constraints) | ForEach-Object { "- $_" }
    $acceptance = @($request.acceptance) | ForEach-Object { "- $_" }
    $prompt = @(
        'You are the Codex execution expert in a ChatGPT-led development workflow.',
        'ChatGPT remains the development lead and final reviewer.',
        'Work ONLY inside ISOLATED_WORKSPACE, the current isolated Git worktree.',
        'Never seek or modify any original Clean Window working folder outside this worktree.',
        'Do not commit, push, open pull requests, change authentication, or inspect/copy credential files.',
        'Fast mode is forbidden. Use standard/default service tier only.',
        "Sandbox for this request is $sandbox. Never use danger-full-access.",
        '',
        "REQUEST MODE: $mode",
        'TASK:',
        [string]$request.task,
        '',
        'CONSTRAINTS:',
        ($constraints -join "`n"),
        '',
        'ACCEPTANCE CRITERIA:',
        ($acceptance -join "`n"),
        '',
        'Inspect relevant code first. Make only the smallest safe changes allowed by the request mode.',
        'Run relevant local checks when useful. Leave implementation edits uncommitted for the Bridge wrapper.',
        'Finish with a concise summary of evidence, changed files, and checks run.'
    ) -join "`n"

    Push-Location $workspace
    try {
        $codexArgs = @(
            'exec',
            '-C', $workspace,
            '--sandbox', $sandbox,
            '--json',
            '--ephemeral',
            '--output-last-message', $summaryPath,
            '-c', "model_reasoning_effort='$effort'",
            '-c', "service_tier='default'",
            '-'
        )
        $prompt | & $codex @codexArgs 2>&1 | Tee-Object -FilePath $eventsPath
        $codexExit = $LASTEXITCODE
        if ($codexExit -ne 0) { throw "Codex exec failed with exit code $codexExit" }

        git -c "safe.directory=$workspaceSafe" diff --check
        if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed.' }

        $node = Get-Command node -ErrorAction SilentlyContinue
        if ($node) {
            foreach ($file in @('background.js', 'windowed_fullscreen.js', 'fullscreen_guard.js')) {
                if (Test-Path -LiteralPath $file) {
                    & $node.Source --check $file
                    if ($LASTEXITCODE -ne 0) { throw "node --check failed: $file" }
                }
            }
        }

        $status = @(git -c "safe.directory=$workspaceSafe" status --porcelain)
        if ($LASTEXITCODE -ne 0) { throw 'git status failed in isolated workspace.' }
        if ($mode -eq 'implement' -and -not $status) { throw 'Codex implement request produced no repository changes.' }
        if ($mode -ne 'implement' -and $status) { throw "Read-only $mode request unexpectedly modified the workspace." }

        if ($status) {
            git -c "safe.directory=$workspaceSafe" add -A
            if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
            git -c "safe.directory=$workspaceSafe" config user.name 'Clean Window Codex Bridge'
            git -c "safe.directory=$workspaceSafe" config user.email 'codex-bridge@users.noreply.github.com'
            git -c "safe.directory=$workspaceSafe" commit -m "Codex bridge result $runKey"
            if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        }

        $resultCommit = (git -c "safe.directory=$workspaceSafe" rev-parse HEAD).Trim()
        Invoke-Git @('push', 'origin', "HEAD:refs/heads/$resultBranch") $workspaceSafe $authHeader

        if ($mode -eq 'implement') {
            $summary = if (Test-Path -LiteralPath $summaryPath) { (Get-Content -LiteralPath $summaryPath -Raw -Encoding UTF8).Trim() } else { '' }
            if ($summary.Length -gt 3500) { $summary = $summary.Substring(0, 3500) + "`n...(truncated)" }
            $headers = @{
                Authorization = "Bearer $token"
                Accept = 'application/vnd.github+json'
                'X-GitHub-Api-Version' = '2022-11-28'
            }
            $body = @{
                title = "[Codex Bridge] Clean Window $runKey"
                head = $resultBranch
                base = 'main'
                body = @(
                    'Automated ChatGPT ↔ Codex Bridge result for review.',
                    '',
                    "- Runner account: $identity",
                    "- Reasoning effort: $effort",
                    '- Fast mode: disabled',
                    "- Sandbox: $sandbox",
                    '- Original Clean Window folder modified by Codex: no',
                    '- Independent checks: git diff --check + node --check extension JS files',
                    '',
                    '### Codex final summary',
                    $summary,
                    '',
                    'ChatGPT must review the diff and test evidence before merge.'
                ) -join "`n"
            } | ConvertTo-Json -Depth 6
            try {
                $pr = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$env:GITHUB_REPOSITORY/pulls" -Headers $headers -ContentType 'application/json' -Body $body
                Write-Host "BRIDGE_RESULT_PR=$($pr.number)"
            } catch {
                Write-Warning 'Result branch was pushed, but automatic PR creation failed.'
            }
        }

        Write-Host "BRIDGE_RESULT_COMMIT=$resultCommit"
        Write-Host 'BRIDGE_RESULT=OK'
    }
    finally { Pop-Location }
}
finally {
    if (Test-Path -LiteralPath $workspace) {
        try { Invoke-Git @('worktree', 'remove', '--force', $workspace) $repoSafe } catch { Write-Warning $_ }
    }
    try { Invoke-Git @('worktree', 'prune') $repoSafe } catch { Write-Warning $_ }
    Remove-Item -LiteralPath $outputDir -Recurse -Force -ErrorAction SilentlyContinue
}
