<#
.SYNOPSIS
  ek-setup v0.1 - AI 작업 환경 원격 세팅 키트 (진단 -> 설치 계획 -> 동의 시 설치 -> 리포트)
.DESCRIPTION
  기본값은 DryRun(아무것도 설치하지 않고 계획만 출력)입니다.
  실제 설치는 -Apply 를 명시하고 동의(Y)했을 때만 실행됩니다.
  Windows PowerShell 5.1 호환. 외부 모듈 설치 없음.
.PARAMETER DryRun
  (기본 동작) 진단 + 계획 + 실행할 명령 출력만 합니다. -Apply 가 없으면 항상 DryRun 입니다.
.PARAMETER Apply
  실제 설치 모드. 동의 확인 후 winget / npm 명령을 실행합니다.
.PARAMETER Profile
  basic | creator | dev
.PARAMETER ReportDir
  report.json / report.md 저장 폴더 (기본 .\report)
.PARAMETER Yes
  실제 모드에서 동의 확인(Y 입력)을 생략합니다. 고객이 내용을 읽고 동의한 경우에만 사용하세요.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Apply,
    [ValidateSet('basic', 'creator', 'dev')]
    [string]$Profile = 'basic',
    [string]$ReportDir = '.\report',
    [switch]$Yes
)

$ErrorActionPreference = 'Continue'
$SchemaVersion = 'ek-setup/0.1'
$IsDry = $true
if ($Apply -and -not $DryRun) { $IsDry = $false }

# ---------- 공통 함수 ----------
function Protect-Text([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return $s }
    if ($env:USERPROFILE) {
        $s = [regex]::Replace($s, [regex]::Escape($env:USERPROFILE), '%USERPROFILE%', 'IgnoreCase')
    }
    if ($env:USERNAME -and $env:USERNAME.Length -ge 2) {
        $s = [regex]::Replace($s, [regex]::Escape($env:USERNAME), '<user>', 'IgnoreCase')
    }
    if ($env:COMPUTERNAME -and $env:COMPUTERNAME.Length -ge 3) {
        $s = [regex]::Replace($s, [regex]::Escape($env:COMPUTERNAME), '<pc>', 'IgnoreCase')
    }
    return $s
}

$script:Warnings = New-Object System.Collections.ArrayList
function Add-Warn([string]$level, [string]$code, [string]$message) {
    $null = $script:Warnings.Add([ordered]@{ level = $level; code = $code; message = $message })
}

function Get-ToolInfo([string]$name, [string[]]$verArgs) {
    $info = [ordered]@{ name = $name; installed = $false; version = $null; pathHint = $null; note = $null }
    $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { return $info }
    $src = $cmd.Source
    if ($src -like '*\WindowsApps\*' -and $name -eq 'python') {
        $info.note = 'Microsoft Store 별칭(stub)만 있고 실제 Python 은 없음'
        $info.pathHint = Protect-Text $src
        return $info
    }
    $info.installed = $true
    $info.pathHint = Protect-Text $src
    try {
        $out = & $src @verArgs 2>$null
        $first = ($out | Select-Object -First 1)
        if ($first) {
            $v = ([string]$first).Trim()
            if ($v.Length -gt 80) { $v = $v.Substring(0, 80) }
            $info.version = Protect-Text $v
        }
    }
    catch {
        $info.note = '버전 확인 실패'
    }
    return $info
}

function Get-Major([string]$v) {
    if ($v -match '(\d+)\.\d+') { return [int]$Matches[1] }
    if ($v -match 'v?(\d+)') { return [int]$Matches[1] }
    return $null
}

# ---------- 1. 동의 배너 ----------
function Show-Banner {
    Write-Host ''
    Write-Host '==============================================================' -ForegroundColor Cyan
    Write-Host ' ek-setup v0.1 - AI 작업 환경 세팅 키트' -ForegroundColor Cyan
    Write-Host '==============================================================' -ForegroundColor Cyan
    Write-Host ' [무엇을 확인하나요?]'
    Write-Host '  - Windows 버전, CPU/메모리/디스크 여유, 실행 정책, 관리자 여부'
    Write-Host '  - git, node, npm, python, VS Code, Claude Code, Codex, Everything 설치 여부'
    Write-Host '  - 프록시 설정, Defender 실시간 보호 상태(조회만), 인터넷 연결(github.com 등 2곳)'
    Write-Host ' [무엇을 설치하나요? (실제 모드에서만, 동의 후)]'
    Write-Host '  - winget 으로 Git / Node.js LTS / VS Code / Everything (프로필에 따라 Python, GitHub CLI)'
    Write-Host '  - npm 으로 Claude Code, Codex CLI (이미 있으면 건너뜀)'
    Write-Host ' [약속]'
    Write-Host '  - 비밀번호, OTP, API 키는 이 스크립트가 묻지도 저장하지도 않습니다. 필요하면 본인이 직접 입력하세요.'
    Write-Host '  - 환경변수 전체, 토큰, 파일 내용은 수집하지 않습니다. 리포트는 report 폴더에 저장되며 자동 전송되지 않습니다.'
    Write-Host '  - 언제든 Ctrl+C 로 중단할 수 있습니다.'
    if ($IsDry) {
        Write-Host ' [모드] DryRun: 아무것도 설치하지 않고 계획만 보여 줍니다.' -ForegroundColor Green
    }
    else {
        Write-Host ' [모드] 실제 설치 모드: 동의하면 위 도구를 설치합니다.' -ForegroundColor Yellow
    }
    Write-Host '==============================================================' -ForegroundColor Cyan
}

Show-Banner

if (-not $IsDry -and -not $Yes) {
    $answer = $null
    try { $answer = Read-Host '위 내용에 동의하고 진행하시겠습니까? (Y/N)' } catch { $answer = 'N' }
    if ($answer -notmatch '^[Yy]') {
        Write-Host '동의하지 않아 중단합니다. 변경된 것은 없습니다.' -ForegroundColor Yellow
        exit 0
    }
}
elseif ($IsDry) {
    Write-Host '(DryRun 이므로 동의 확인 없이 진행합니다.)'
}

# ---------- 2. 진단 (읽기 전용) ----------
Write-Host ''
Write-Host '[1/4] 진단 중... (읽기 전용)' -ForegroundColor Cyan

$diag = [ordered]@{}

# OS / 하드웨어
$os = $null; $cs = $null; $cpu = $null; $disk = $null
try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { }
try { $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop } catch { }
try { $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1 } catch { }
try {
    $sysDrive = $env:SystemDrive
    if (-not $sysDrive) { $sysDrive = 'C:' }
    $disk = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $sysDrive + "'") -ErrorAction Stop
} catch { }

$build = 0
if ($os) { [void][int]::TryParse([string]$os.BuildNumber, [ref]$build) }
$ramGB = $null
if ($cs) { $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1) }
$diskFreeGB = $null; $diskTotalGB = $null
if ($disk) {
    $diskFreeGB = [math]::Round($disk.FreeSpace / 1GB, 1)
    $diskTotalGB = [math]::Round($disk.Size / 1GB, 1)
}
$osCaption = $null; $osVersion = $null; $osArch = $null
if ($os) { $osCaption = [string]$os.Caption; $osVersion = [string]$os.Version; $osArch = [string]$os.OSArchitecture }
$cpuName = $null; $cpuCores = $null
if ($cpu) { $cpuName = ([string]$cpu.Name).Trim(); $cpuCores = [int]$cpu.NumberOfLogicalProcessors }

$diag.os = [ordered]@{ caption = $osCaption; version = $osVersion; build = $build; architecture = $osArch }
$diag.hardware = [ordered]@{ cpu = $cpuName; logicalCores = $cpuCores; ramGB = $ramGB; systemDriveFreeGB = $diskFreeGB; systemDriveTotalGB = $diskTotalGB }

# 사용자명 (이름 자체는 기록하지 않음)
$uname = [string]$env:USERNAME
$profPath = [string]$env:USERPROFILE
$diag.user = [ordered]@{
    usernameHasNonAscii = [bool]($uname -match '[^\x00-\x7F]')
    usernameHasSpace    = [bool]($uname -match '\s')
    profilePathHasNonAscii = [bool]($profPath -match '[^\x00-\x7F]')
    profilePathHasSpace = [bool]($profPath -match '\s')
}

# 실행 정책 / 관리자
$effPolicy = [string](Get-ExecutionPolicy)
$policyList = @()
try {
    $policyList = @(Get-ExecutionPolicy -List | ForEach-Object { [ordered]@{ scope = [string]$_.Scope; policy = [string]$_.ExecutionPolicy } })
} catch { }
$isAdmin = $false
try {
    $wp = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    $isAdmin = $wp.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { }
$diag.executionPolicy = [ordered]@{ effective = $effPolicy; scopes = $policyList }
$diag.isAdmin = $isAdmin

# winget
$wingetInfo = Get-ToolInfo 'winget' @('--version')
$diag.winget = $wingetInfo

# 도구
$tools = [ordered]@{}
$tools.git = Get-ToolInfo 'git' @('--version')
$tools.node = Get-ToolInfo 'node' @('--version')
$tools.npm = Get-ToolInfo 'npm' @('--version')
$tools.python = Get-ToolInfo 'python' @('--version')
if (-not $tools.python.installed) {
    $py = Get-ToolInfo 'py' @('--version')
    if ($py.installed) {
        $tools.python.installed = $true
        $tools.python.version = $py.version
        $tools.python.pathHint = $py.pathHint
        $tools.python.note = 'py 런처로 확인'
    }
}
$tools.code = Get-ToolInfo 'code' @('--version')
$tools.claude = Get-ToolInfo 'claude' @('--version')
$tools.codex = Get-ToolInfo 'codex' @('--version')
$tools.gh = Get-ToolInfo 'gh' @('--version')
$tools.everything = Get-ToolInfo 'es' @('-version')
if (-not $tools.everything.installed) {
    $evPaths = @()
    if ($env:ProgramFiles) { $evPaths += (Join-Path $env:ProgramFiles 'Everything\Everything.exe') }
    if (${env:ProgramFiles(x86)}) { $evPaths += (Join-Path ${env:ProgramFiles(x86)} 'Everything\Everything.exe') }
    foreach ($p in $evPaths) {
        if (Test-Path -LiteralPath $p) {
            $tools.everything.installed = $true
            $tools.everything.note = 'Everything 앱은 있으나 es(CLI) 는 PATH 에 없음'
            break
        }
    }
}
$diag.tools = $tools

# PATH (항목 수 / 문제 항목만)
$pathRaw = [string]$env:Path
$pathItems = @($pathRaw.Split(';') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
$seen = @{}
$dups = New-Object System.Collections.ArrayList
$missing = New-Object System.Collections.ArrayList
foreach ($it in $pathItems) {
    $norm = ([Environment]::ExpandEnvironmentVariables($it)).TrimEnd('\').ToLowerInvariant()
    if ($seen.ContainsKey($norm)) { $null = $dups.Add((Protect-Text $it)) } else { $seen[$norm] = 1 }
    $exp = [Environment]::ExpandEnvironmentVariables($it)
    if (-not (Test-Path -LiteralPath $exp)) { $null = $missing.Add((Protect-Text $it)) }
}
$diag.path = [ordered]@{
    length = $pathRaw.Length
    itemCount = $pathItems.Count
    duplicateCount = $dups.Count
    missingCount = $missing.Count
    problemItems = @(($dups + $missing) | Select-Object -Unique | Select-Object -First 10)
}

# 프록시
$envProxy = [bool]($env:HTTP_PROXY -or $env:HTTPS_PROXY -or $env:http_proxy -or $env:https_proxy)
$ieProxy = $false
try {
    $ie = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
    if ($ie.ProxyEnable -eq 1) { $ieProxy = $true }
} catch { }
$diag.proxy = [ordered]@{ envVarSet = $envProxy; systemProxyEnabled = $ieProxy }

# 기본 셸
$pwshCmd = Get-Command pwsh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$gitBash = $false
if ($tools.git.installed) { $gitBash = $true }
$comspecLeaf = ''
if ($env:ComSpec) { $comspecLeaf = Split-Path -Leaf $env:ComSpec }
$diag.shell = [ordered]@{
    runningHost = 'Windows PowerShell'
    psVersion = $PSVersionTable.PSVersion.ToString()
    pwshInstalled = [bool]$pwshCmd
    comspec = $comspecLeaf
    gitInstalled = $gitBash
}

# Defender (조회만)
$defender = [ordered]@{ realTimeProtection = 'unknown' }
try {
    $mp = Get-MpComputerStatus -ErrorAction Stop
    if ($mp.RealTimeProtectionEnabled) { $defender.realTimeProtection = 'on' } else { $defender.realTimeProtection = 'off' }
} catch { }
$diag.defender = $defender

# 인터넷 (HEAD 1회, DryRun 에서도 허용 / 실패해도 계속)
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
function Test-Url([string]$url) {
    $r = [ordered]@{ url = $url; reachable = $false; status = $null; error = $null }
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
        $r.reachable = $true
        $r.status = [int]$resp.StatusCode
    }
    catch {
        $ex = $_.Exception
        if ($ex.Response) {
            # 4xx/5xx 응답이 왔다는 것은 네트워크 도달은 가능하다는 뜻
            $r.reachable = $true
            try { $r.status = [int]$ex.Response.StatusCode } catch { }
        }
        else {
            $m = [string]$ex.Message
            if ($m.Length -gt 100) { $m = $m.Substring(0, 100) }
            $r.error = Protect-Text $m
        }
    }
    return $r
}
$net = @((Test-Url 'https://github.com'), (Test-Url 'https://registry.npmjs.org'))
$diag.internet = $net

# ---------- 경고 판정 ----------
if ($build -gt 0 -and $build -lt 17763) { Add-Warn 'action' 'OS_TOO_OLD' "Windows 빌드 $build 는 winget 을 지원하지 않을 수 있습니다. Windows 업데이트가 필요합니다." }
if ($null -ne $ramGB) {
    if ($ramGB -lt 4) { Add-Warn 'action' 'RAM_LOW' "메모리 ${ramGB}GB: AI 도구 실행에 부족합니다(권장 8GB 이상)." }
    elseif ($ramGB -lt 8) { Add-Warn 'caution' 'RAM_LIMITED' "메모리 ${ramGB}GB: 동작은 하나 여유가 적습니다(권장 8GB 이상)." }
}
if ($null -ne $diskFreeGB) {
    if ($diskFreeGB -lt 5) { Add-Warn 'action' 'DISK_LOW' "시스템 드라이브 여유 ${diskFreeGB}GB: 설치 공간이 부족합니다(최소 10GB 권장)." }
    elseif ($diskFreeGB -lt 10) { Add-Warn 'caution' 'DISK_LIMITED' "시스템 드라이브 여유 ${diskFreeGB}GB: 여유가 적습니다(10GB 이상 권장)." }
}
if ($diag.user.usernameHasNonAscii -or $diag.user.profilePathHasNonAscii) { Add-Warn 'caution' 'USERNAME_NON_ASCII' 'Windows 사용자 폴더 경로에 한글/비ASCII 문자가 있습니다. 일부 CLI·빌드 도구가 경로 문제를 일으킬 수 있어 작업 폴더는 C:\work 같은 영문 경로를 권장합니다.' }
if ($diag.user.usernameHasSpace -or $diag.user.profilePathHasSpace) { Add-Warn 'caution' 'USERNAME_SPACE' 'Windows 사용자 폴더 경로에 공백이 있습니다. 일부 스크립트에서 따옴표 처리 문제가 생길 수 있습니다.' }
if ($effPolicy -in @('Restricted', 'AllSigned')) { Add-Warn 'caution' 'EXEC_POLICY' "PowerShell 실행 정책이 $effPolicy 입니다. npm/claude 등의 .ps1 실행이 막힐 수 있습니다(해결은 별도 동의 후 현재 사용자 범위 RemoteSigned 권장)." }
if (-not $wingetInfo.installed) { Add-Warn 'action' 'WINGET_MISSING' 'winget(앱 설치 관리자)이 없습니다. Microsoft Store 의 "앱 설치 관리자" 업데이트가 필요합니다.' }
$nodeMajor = $null
if ($tools.node.installed -and $tools.node.version) { $nodeMajor = Get-Major $tools.node.version }
if ($null -ne $nodeMajor -and $nodeMajor -lt 18) { Add-Warn 'caution' 'NODE_OLD' "Node.js $($tools.node.version) 는 오래되었습니다. Claude Code/Codex 는 최신 LTS 를 권장합니다." }
if ($tools.node.installed -and -not $tools.npm.installed) { Add-Warn 'caution' 'NPM_MISSING' 'node 는 있으나 npm 을 찾지 못했습니다. PATH 또는 설치 상태를 확인해야 합니다.' }
if ($diag.path.duplicateCount -gt 0) { Add-Warn 'caution' 'PATH_DUP' "PATH 에 중복 항목이 $($diag.path.duplicateCount)개 있습니다." }
if ($diag.path.missingCount -gt 5) { Add-Warn 'caution' 'PATH_MISSING' "PATH 에 존재하지 않는 폴더가 $($diag.path.missingCount)개 있습니다." }
if ($diag.path.length -gt 2000) { Add-Warn 'caution' 'PATH_LONG' "PATH 길이가 $($diag.path.length)자입니다(2047자 근처에서 잘릴 수 있음)." }
if ($envProxy -or $ieProxy) { Add-Warn 'caution' 'PROXY' '프록시 설정이 감지되었습니다. npm/winget 다운로드가 실패하면 프록시 설정이 필요할 수 있습니다.' }
if ($defender.realTimeProtection -eq 'off') { Add-Warn 'caution' 'DEFENDER_OFF' 'Windows Defender 실시간 보호가 꺼져 있습니다(다른 보안 프로그램 사용 여부 확인).' }
$reachCount = @($net | Where-Object { $_.reachable }).Count
if ($reachCount -eq 0) { Add-Warn 'action' 'NO_INTERNET' 'github.com / registry.npmjs.org 에 모두 연결하지 못했습니다. 설치가 불가능합니다(네트워크·방화벽 확인).' }
elseif ($reachCount -lt $net.Count) { Add-Warn 'caution' 'PARTIAL_INTERNET' '일부 사이트에만 연결됩니다. 방화벽/프록시를 확인하세요.' }

# ---------- 3. 설치 계획 ----------
Write-Host '[2/4] 설치 계획 작성...' -ForegroundColor Cyan

$wingetBasic = @(
    @{ id = 'Git.Git'; tool = 'git' },
    @{ id = 'OpenJS.NodeJS.LTS'; tool = 'node' },
    @{ id = 'Microsoft.VisualStudioCode'; tool = 'code' },
    @{ id = 'voidtools.Everything'; tool = 'everything' }
)
$wingetList = @($wingetBasic)
if ($Profile -eq 'creator' -or $Profile -eq 'dev') { $wingetList += @{ id = 'Python.Python.3.12'; tool = 'python' } }
if ($Profile -eq 'dev') { $wingetList += @{ id = 'GitHub.cli'; tool = 'gh' } }

$plan = New-Object System.Collections.ArrayList
$order = 0
foreach ($w in $wingetList) {
    $order++
    $t = $tools[$w.tool]
    $action = 'install'
    $reason = '미설치'
    if ($t.installed) { $action = 'skip'; $reason = '이미 설치됨' }
    $cmdText = "winget install --id $($w.id) -e --source winget --accept-package-agreements --accept-source-agreements"
    $null = $plan.Add([ordered]@{ order = $order; kind = 'winget'; target = $w.id; tool = $w.tool; action = $action; reason = $reason; command = $cmdText })
}
$npmList = @(
    @{ pkg = '@anthropic-ai/claude-code'; tool = 'claude' },
    @{ pkg = '@openai/codex'; tool = 'codex' }
)
$nodeWillInstall = (-not $tools.node.installed)
foreach ($n in $npmList) {
    $order++
    $t = $tools[$n.tool]
    $action = 'install'
    $reason = '미설치'
    if ($t.installed) { $action = 'skip'; $reason = '이미 설치됨' }
    elseif ($nodeWillInstall) { $reason = '미설치 (Node.js 설치 직후 새 터미널에서 실행 필요할 수 있음)' }
    $null = $plan.Add([ordered]@{ order = $order; kind = 'npm'; target = $n.pkg; tool = $n.tool; action = $action; reason = $reason; command = ('npm i -g ' + $n.pkg) })
}

$toInstall = @($plan | Where-Object { $_.action -eq 'install' })
if ($toInstall.Count -gt 0 -and -not $wingetInfo.installed) {
    # winget 단계는 실행 불가 표시
    foreach ($p in $plan) { if ($p.kind -eq 'winget' -and $p.action -eq 'install') { $p.reason = $p.reason + ' / winget 없음: 실행 불가' } }
}

Write-Host ("  프로필: {0} / 설치 대상 {1}개 / 건너뜀 {2}개" -f $Profile, $toInstall.Count, ($plan.Count - $toInstall.Count))

# ---------- 4. 실행 ----------
Write-Host '[3/4] 실행 단계...' -ForegroundColor Cyan
$execution = New-Object System.Collections.ArrayList

function Update-ProcessPath {
    # 현재 프로세스 PATH 만 갱신 (영구 환경변수는 건드리지 않음)
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($m, $u) | Where-Object { $_ }) -join ';'
}

foreach ($step in $plan) {
    if ($step.action -eq 'skip') {
        $null = $execution.Add([ordered]@{ order = $step.order; target = $step.target; status = 'skipped'; exitCode = $null })
        continue
    }
    if ($IsDry) {
        Write-Host ("  [DryRun] " + $step.command)
        $null = $execution.Add([ordered]@{ order = $step.order; target = $step.target; status = 'dryrun'; exitCode = $null })
        continue
    }
    # ----- 실제 모드 (이 키트의 테스트에서는 실행하지 않음) -----
    Write-Host ("  실행: " + $step.command) -ForegroundColor Yellow
    $code = $null
    $status = 'failed'
    try {
        if ($step.kind -eq 'winget') {
            if (-not $wingetInfo.installed) { $status = 'blocked-no-winget' }
            else {
                & winget install --id $step.target -e --source winget --accept-package-agreements --accept-source-agreements
                $code = $LASTEXITCODE
                # -1978335189 = 이미 설치되어 있고 업그레이드할 것이 없음
                if ($code -eq 0 -or $code -eq -1978335189) { $status = 'ok' }
            }
        }
        else {
            Update-ProcessPath
            $npmCmd = Get-Command npm -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $npmCmd) { $status = 'blocked-npm-not-found-open-new-terminal' }
            else {
                & $npmCmd.Source i -g $step.target
                $code = $LASTEXITCODE
                if ($code -eq 0) { $status = 'ok' }
            }
        }
    }
    catch {
        $status = 'failed'
    }
    $null = $execution.Add([ordered]@{ order = $step.order; target = $step.target; status = $status; exitCode = $code })
}

$execFailed = @($execution | Where-Object { $_.status -notin @('ok', 'skipped', 'dryrun') })
if (-not $IsDry -and $execFailed.Count -gt 0) {
    Add-Warn 'action' 'INSTALL_FAILED' ("설치 단계 $($execFailed.Count)개가 실패/보류되었습니다. report.json 의 execution 을 확인하세요.")
}
if (-not $IsDry -and $toInstall.Count -gt 0) {
    Add-Warn 'caution' 'NEW_TERMINAL' '설치 직후에는 PATH 반영을 위해 새 터미널을 열어 한 번 더 실행해 결과를 확인하세요.'
}

# ---------- 5. 리포트 ----------
Write-Host '[4/4] 리포트 작성...' -ForegroundColor Cyan

$actionCount = @($script:Warnings | Where-Object { $_.level -eq 'action' }).Count
$cautionCount = @($script:Warnings | Where-Object { $_.level -eq 'caution' }).Count
$overall = 'ok'
if ($cautionCount -gt 0) { $overall = 'caution' }
if ($actionCount -gt 0) { $overall = 'action' }
$overallKo = '정상'
if ($overall -eq 'caution') { $overallKo = '주의' }
if ($overall -eq 'action') { $overallKo = '조치 필요' }

$report = [ordered]@{
    schema = $SchemaVersion
    generatedAt = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
    mode = $(if ($IsDry) { 'dryrun' } else { 'apply' })
    profile = $Profile
    overall = $overall
    overallLabel = $overallKo
    diagnostics = $diag
    plan = @($plan)
    execution = @($execution)
    warnings = @($script:Warnings)
    privacy = [ordered]@{
        note = '사용자명·전체 경로·토큰·환경변수 전체는 수집하지 않음. 경로는 %USERPROFILE%/<user> 로 마스킹.'
    }
}

$dir = $ReportDir
if (-not [IO.Path]::IsPathRooted($dir)) { $dir = Join-Path $PWD.Path $dir }
if (-not (Test-Path -LiteralPath $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
$jsonPath = Join-Path $dir 'report.json'
$mdPath = Join-Path $dir 'report.md'

$json = ConvertTo-Json -InputObject $report -Depth 8
[IO.File]::WriteAllText($jsonPath, $json, (New-Object Text.UTF8Encoding $false))

# --- report.md ---
function YN($b) { if ($b) { return '있음' } else { return '없음' } }
$sb = New-Object System.Text.StringBuilder
function L([string]$s) { $null = $sb.AppendLine($s) }

L '# AI 작업 환경 진단 리포트'
L ''
L ("- 스키마: ``{0}`` / 모드: **{1}** / 프로필: **{2}**" -f $SchemaVersion, $report.mode, $Profile)
L ("- 생성 시각: {0}" -f $report.generatedAt)
L ("- 종합 판정: **{0}** (조치 필요 {1}건 / 주의 {2}건)" -f $overallKo, $actionCount, $cautionCount)
L ''
L '## 1. 시스템 요약'
L ''
L '| 항목 | 값 | 판정 |'
L '|---|---|---|'
L ("| Windows | {0} (빌드 {1}, {2}) | {3} |" -f $osCaption, $build, $osArch, $(if ($build -ge 17763) { '정상' } else { '조치 필요' }))
L ("| CPU | {0} ({1}스레드) | - |" -f $cpuName, $cpuCores)
L ("| 메모리 | {0} GB | {1} |" -f $ramGB, $(if ($null -eq $ramGB) { '확인 불가' } elseif ($ramGB -ge 8) { '정상' } elseif ($ramGB -ge 4) { '주의' } else { '조치 필요' }))
L ("| 시스템 디스크 여유 | {0} GB / {1} GB | {2} |" -f $diskFreeGB, $diskTotalGB, $(if ($null -eq $diskFreeGB) { '확인 불가' } elseif ($diskFreeGB -ge 10) { '정상' } elseif ($diskFreeGB -ge 5) { '주의' } else { '조치 필요' }))
L ("| 사용자명 한글/비ASCII | {0} | {1} |" -f $(YN $diag.user.usernameHasNonAscii), $(if ($diag.user.usernameHasNonAscii) { '주의' } else { '정상' }))
L ("| 사용자명 공백 | {0} | {1} |" -f $(YN $diag.user.usernameHasSpace), $(if ($diag.user.usernameHasSpace) { '주의' } else { '정상' }))
L ("| 실행 정책 | {0} | {1} |" -f $effPolicy, $(if ($effPolicy -in @('Restricted', 'AllSigned')) { '주의' } else { '정상' }))
L ("| 관리자 권한 | {0} | 참고 |" -f $(if ($isAdmin) { '예' } else { '아니오' }))
L ("| winget | {0} | {1} |" -f $(if ($wingetInfo.installed) { $wingetInfo.version } else { '없음' }), $(if ($wingetInfo.installed) { '정상' } else { '조치 필요' }))
L ("| 프록시 | 환경변수 {0} / 시스템 {1} | {2} |" -f $(YN $envProxy), $(YN $ieProxy), $(if ($envProxy -or $ieProxy) { '주의' } else { '정상' }))
L ("| Defender 실시간 보호 | {0} | {1} |" -f $defender.realTimeProtection, $(if ($defender.realTimeProtection -eq 'off') { '주의' } else { '정상/확인불가' }))
L ("| PATH | {0}개 항목, {1}자, 중복 {2}, 없는 폴더 {3} | {4} |" -f $diag.path.itemCount, $diag.path.length, $diag.path.duplicateCount, $diag.path.missingCount, $(if ($diag.path.duplicateCount -gt 0 -or $diag.path.missingCount -gt 5 -or $diag.path.length -gt 2000) { '주의' } else { '정상' }))
L ("| 셸 | Windows PowerShell {0}, pwsh {1} | 참고 |" -f $diag.shell.psVersion, $(YN $diag.shell.pwshInstalled))
foreach ($n in $net) {
    $ok = '연결 실패'
    if ($n.reachable) { $ok = '연결됨 (' + $n.status + ')' }
    L ("| 인터넷 {0} | {1} | {2} |" -f $n.url, $ok, $(if ($n.reachable) { '정상' } else { '주의' }))
}
L ''
L '## 2. 도구 설치 현황'
L ''
L '| 도구 | 설치 | 버전 |'
L '|---|---|---|'
foreach ($k in $tools.Keys) {
    $t = $tools[$k]
    $ver = ''
    if ($t.version) { $ver = $t.version } elseif ($t.note) { $ver = $t.note }
    L ("| {0} | {1} | {2} |" -f $k, $(if ($t.installed) { '설치됨' } else { '없음' }), $ver)
}
L ''
L '## 3. 경고'
L ''
if ($script:Warnings.Count -eq 0) {
    L '경고 없음 (정상).'
}
else {
    L '| 단계 | 코드 | 내용 |'
    L '|---|---|---|'
    foreach ($w in @($script:Warnings | Sort-Object { if ($_.level -eq 'action') { 0 } else { 1 } })) {
        $lv = '주의'
        if ($w.level -eq 'action') { $lv = '조치 필요' }
        L ("| {0} | {1} | {2} |" -f $lv, $w.code, $w.message)
    }
}
L ''
L '## 4. 설치 계획'
L ''
L '| # | 종류 | 대상 | 처리 | 사유 |'
L '|---|---|---|---|---|'
foreach ($p in $plan) {
    $act = '설치'
    if ($p.action -eq 'skip') { $act = '건너뜀' }
    L ("| {0} | {1} | {2} | {3} | {4} |" -f $p.order, $p.kind, $p.target, $act, $p.reason)
}
L ''
if ($IsDry) {
    L '> DryRun 이므로 실제로 설치된 것은 없습니다. 위 계획대로 설치하려면 운영자 안내에 따라 `-Apply` 로 다시 실행하세요.'
}
else {
    L '## 5. 실행 결과'
    L ''
    L '| # | 대상 | 상태 | 종료 코드 |'
    L '|---|---|---|---|'
    foreach ($e in $execution) { L ("| {0} | {1} | {2} | {3} |" -f $e.order, $e.target, $e.status, $e.exitCode) }
}
L ''
L '---'
L '이 리포트에는 비밀번호·토큰·환경변수 전체·사용자명이 포함되지 않습니다. 운영자에게는 `report.json` 만 보내면 됩니다.'

[IO.File]::WriteAllText($mdPath, $sb.ToString(), (New-Object Text.UTF8Encoding $true))

Write-Host ''
Write-Host ("완료: 종합 판정 = {0} (조치 필요 {1} / 주의 {2})" -f $overallKo, $actionCount, $cautionCount) -ForegroundColor Green
Write-Host ("리포트: " + (Protect-Text $jsonPath))
Write-Host ("        " + (Protect-Text $mdPath))
if ($IsDry) { Write-Host 'DryRun 이었으므로 이 PC 에는 아무것도 설치/변경되지 않았습니다.' }

if (-not $IsDry -and $execFailed.Count -gt 0) { exit 1 }
exit 0
