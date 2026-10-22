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
$tmpBase = Join-Path ([IO.Path]::GetTempPath()) ('ek-setup-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))

foreach ($prof in @('basic', 'creator', 'dev')) {
    Write-Host ("=== profile: " + $prof)
    $dir = Join-Path $tmpBase $prof
    $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -DryRun -Profile $prof -ReportDir $dir
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

    # 개인정보 누출 검사
    $mdRaw = Get-Content -LiteralPath $mp -Raw -Encoding UTF8
    $leak = $false
    if ($env:USERNAME -and $env:USERNAME.Length -ge 3) {
        if ($raw -match [regex]::Escape($env:USERNAME) -or $mdRaw -match [regex]::Escape($env:USERNAME)) { $leak = $true }
    }
    if ($env:USERPROFILE -and ($raw -match [regex]::Escape($env:USERPROFILE) -or $mdRaw -match [regex]::Escape($env:USERPROFILE))) { $leak = $true }
    Check (-not $leak) "no username/profile path leak ($prof)"
}

# 정리 (임시 폴더만)
try { Remove-Item -LiteralPath $tmpBase -Recurse -Force -ErrorAction SilentlyContinue } catch { }

Write-Host ''
if ($fail.Count -gt 0) {
    Write-Host ("FAILED: " + $fail.Count + " check(s)") -ForegroundColor Red
    exit 1
}
Write-Host 'ALL PASSED' -ForegroundColor Green
exit 0
