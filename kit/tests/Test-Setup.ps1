# ek-setup 시제품 테스트 (DryRun 전용). 실패 시 exit 1.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root 'ek-setup.ps1'
$fail = New-Object System.Collections.ArrayList

function Check([bool]$cond, [string]$name) {
    if ($cond) { Write-Host ("  PASS  " + $name) -ForegroundColor Green }
    else { Write-Host ("  FAIL  " + $name) -ForegroundColor Red; $null = $fail.Add($name) }
}

if (-not (Test-Path -LiteralPath $script)) { Write-Host 'FAIL ek-setup.ps1 not found'; exit 1 }

$expectedPlan = @{ basic = 6; creator = 7; dev = 8 }
$repoRoot = Split-Path -Parent $root
$tmpBase = Join-Path $repoRoot ('.tmp/ek-setup-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))

foreach ($prof in @('basic', 'creator', 'dev')) {
    Write-Host ("=== profile: " + $prof)
    $dir = Join-Path $tmpBase $prof
    $fakeHome = Join-Path $tmpBase 'home'
    $null = New-Item -ItemType Directory -Path $fakeHome -Force
    $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -DryRun -Profile $prof -ReportDir $dir -TargetHome $fakeHome
    $code = $LASTEXITCODE
    Check ($code -eq 0) "ek-setup exit code 0 ($prof)"

    $jp = Join-Path $dir 'report.json'
    $mp = Join-Path $dir 'report.md'
    Check (Test-Path -LiteralPath $jp) "report.json exists ($prof)"
    Check (Test-Path -LiteralPath $mp) "report.md exists ($prof)"
    if (-not (Test-Path -LiteralPath $jp)) { continue }

    $raw = Get-Content -LiteralPath $jp -Raw -Encoding UTF8
    $r = $null
    try { $r = $raw | ConvertFrom-Json; Check $true "report.json parses ($prof)" }
    catch { Check $false "report.json parses ($prof)"; continue }

    Check ($r.schema -eq 'ek-setup/0.1') "schema == ek-setup/0.1 ($prof)"
    Check ($r.mode -eq 'dryrun') "mode == dryrun ($prof)"
    Check ($r.profile -eq $prof) "profile field ($prof)"
    Check ($null -ne $r.PSObject.Properties['warnings'] -and ($r.warnings -is [array] -or $null -eq $r.warnings -or $r.warnings.Count -ge 0)) "warnings is array ($prof)"
    Check ($r.plan -is [array]) "plan is array ($prof)"
    Check (@($r.plan).Count -eq $expectedPlan[$prof]) ("plan count == " + $expectedPlan[$prof] + " ($prof), actual " + @($r.plan).Count)
    Check ($null -ne $r.diagnostics.os -and $null -ne $r.diagnostics.tools) "diagnostics has os/tools ($prof)"
    Check (@('ok', 'caution', 'action') -contains $r.overall) "overall valid ($prof)"
    $execInstalled = @($r.execution | Where-Object { $_.status -eq 'ok' })
    Check ($execInstalled.Count -eq 0) "no real install executed in DryRun ($prof)"
    $runtimeInstalls = @($r.plan | Where-Object { $_.tool -in @('node','python') -and $_.action -eq 'install' })
    Check ($runtimeInstalls.Count -eq 0) "Node/Python are never installed ($prof)"
    Check (@($r.plan | Where-Object { $_.tool -eq 'claude' -and $_.kind -eq 'native' }).Count -eq 1) "Claude native installer is default ($prof)"
    Check (@($r.plan | Where-Object { $_.tool -eq 'codex' -and $_.command -eq 'irm https://chatgpt.com/codex/install.ps1 | iex' }).Count -eq 1) "Codex official installer ($prof)"

    # 개인정보 누출 검사
    $mdRaw = Get-Content -LiteralPath $mp -Raw -Encoding UTF8
    $leak = $false
    if ($env:USERNAME -and $env:USERNAME.Length -ge 3) {
        if ($raw -match [regex]::Escape($env:USERNAME) -or $mdRaw -match [regex]::Escape($env:USERNAME)) { $leak = $true }
    }
    if ($env:USERPROFILE -and ($raw -match [regex]::Escape($env:USERPROFILE) -or $mdRaw -match [regex]::Escape($env:USERPROFILE))) { $leak = $true }
    Check (-not $leak) "no username/profile path leak ($prof)"
}

# 증거는 저장소 .tmp 안에 보존합니다. 실제 사용자 설정은 쓰지 않습니다.

Write-Host ''
if ($fail.Count -gt 0) {
    Write-Host ("FAILED: " + $fail.Count + " check(s)") -ForegroundColor Red
    exit 1
}
Write-Host 'ALL PASSED' -ForegroundColor Green
exit 0
