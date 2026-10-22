# ek-setup v0.2. Windows PowerShell 5.1. 기본은 DryRun.
[CmdletBinding()]
param(
    [switch]$DryRun, [switch]$Apply,
    [ValidateSet('basic','creator','dev')][string]$Profile = 'basic',
    [string]$ReportDir = '.\report',
    [string]$TargetHome = $env:USERPROFILE,
    [ValidateSet('native','winget')][string]$ClaudeInstaller = 'native',
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
$isDry = -not ($Apply -and -not $DryRun)
function Tool([string]$name) {
    $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $installed = [bool]$cmd
    if ($name -eq 'python' -and $cmd -and $cmd.Source -like '*\WindowsApps\*') { $installed = $false }
    $version = $null
    if ($installed) {
        try {
            $raw = (& $cmd.Source --version 2>$null | Out-String)
            # 도구의 원래 출력은 버리고 버전 번호만 허용합니다.
            if ($raw -match '\b\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?') { $version = $Matches[0] }
        } catch { }
    }
    return [ordered]@{ name=$name; installed=$installed; version=$version; pathHint=$null; note=$null }
}
Write-Host 'ek-setup v0.2 — 원장님 AI 작업실 사전 점검'
Write-Host '기본은 미리보기입니다. 비밀번호·인증 코드·파일 내용·폴더 목록은 수집하지 않습니다.'
Write-Host 'Node와 Python은 현재 상태만 확인하고 설치·업그레이드하지 않습니다.'
Write-Host 'Claude Code는 기본 네이티브 설치, Codex는 공식 설치 스크립트를 사용합니다.'
Write-Host '로그인은 고객 본인이 유료 구독 계정으로 직접 진행합니다. API 키는 받지 않습니다.'
if ($isDry) { Write-Host '[DryRun] 실제 설치 없이 계획과 로컬 리포트를 만듭니다.' }
elseif (-not $Yes) {
    if ((Read-Host '미리보기 계획을 확인했고 실제 설치에 동의하시나요? (Y/N)') -notmatch '^[Yy]$') {
        Write-Host '중단했습니다. 설치한 것은 없습니다.'; exit 0
    }
}
$tools = [ordered]@{}
foreach ($name in @('git','node','python','code','claude','codex','gh','es','winget')) { $tools[$name] = Tool $name }
$warnings = New-Object System.Collections.ArrayList
foreach ($name in @('node','python')) {
    if (-not $tools[$name].installed) { $null=$warnings.Add([ordered]@{level='caution';code=($name.ToUpper()+'_MISSING');message=($name+' 없음: 이번 세팅에서는 설치하지 않습니다. 필요한 업무가 생기면 별도 안내를 받으세요.')}) }
}
$freeGB = $null
try { $freeGB = [math]::Round((Get-PSDrive -Name ([IO.Path]::GetPathRoot($TargetHome).TrimEnd(':','\')) -ErrorAction Stop).Free / 1GB,1) } catch { }
$diag = [ordered]@{
    os=[ordered]@{version=[Environment]::OSVersion.Version.ToString();platform=[Environment]::OSVersion.Platform.ToString()}
    tools=$tools
    path=[ordered]@{itemCount=@(([string]$env:PATH).Split(';') | Where-Object {$_}).Count}
    diskFreeGB=$freeGB
    executionPolicy=[string](Get-ExecutionPolicy)
    powershell=$PSVersionTable.PSVersion.ToString()
}
$plan=New-Object System.Collections.ArrayList
function Step([string]$kind,[string]$target,[string]$tool,[string]$command,[bool]$notice=$false) {
    $action='install'; $reason='설치되지 않음'
    if ($notice) { $action='notice'; $reason='확인과 안내만 합니다. 설치·업그레이드하지 않습니다.' }
    elseif ($tools[$tool].installed) { $action='skip'; $reason='이미 설치되어 그대로 사용합니다.' }
    $null=$plan.Add([ordered]@{order=$plan.Count+1;kind=$kind;target=$target;tool=$tool;action=$action;reason=$reason;command=$command})
}
Step 'winget' 'Git.Git' 'git' 'winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements'
Step 'notice' 'Node.js' 'node' 'Node.js 상태만 확인합니다. 설치·업그레이드하지 않습니다.' $true
Step 'winget' 'Microsoft.VisualStudioCode' 'code' 'winget install --id Microsoft.VisualStudioCode -e --source winget --accept-package-agreements --accept-source-agreements'
Step 'winget' 'voidtools.Everything' 'es' 'winget install --id voidtools.Everything -e --source winget --accept-package-agreements --accept-source-agreements'
if ($Profile -in @('creator','dev')) { Step 'notice' 'Python' 'python' 'Python 상태만 확인합니다. 설치·업그레이드하지 않습니다.' $true }
if ($Profile -eq 'dev') { Step 'winget' 'GitHub.cli' 'gh' 'winget install --id GitHub.cli -e --source winget --accept-package-agreements --accept-source-agreements' }
if ($ClaudeInstaller -eq 'winget') {
    Step 'winget' 'Anthropic.ClaudeCode' 'claude' 'winget install --id Anthropic.ClaudeCode -e --source winget --accept-package-agreements --accept-source-agreements'
} else { Step 'native' 'Claude Code' 'claude' 'irm https://claude.ai/install.ps1 | iex' }
Step 'official' 'Codex' 'codex' 'irm https://chatgpt.com/codex/install.ps1 | iex'
$execution=New-Object System.Collections.ArrayList
foreach ($step in $plan) {
    Write-Host ('['+$(if($isDry){'DryRun'}else{$step.action})+'] '+$step.command)
    $status='skipped'; $code=$null
    if ($step.action -eq 'install') {
        if ($isDry) { $status='dryrun' }
        else {
            try {
                if ($step.kind -eq 'winget') {
                    if (-not $tools.winget.installed) { throw 'winget이 없습니다. 앱 설치 관리자를 확인하세요.' }
                    & winget install --id $step.target -e --source winget --accept-package-agreements --accept-source-agreements
                    $code=$LASTEXITCODE
                    if ($code -ne 0 -and $code -ne -1978335189) { throw '설치 실패' }
                } else {
                    $url='https://claude.ai/install.ps1'
                    if ($step.tool -eq 'codex') { $url='https://chatgpt.com/codex/install.ps1' }
                    # 설치 URL은 고객 입력을 받지 않는 고정된 공식 주소입니다.
                    $installer=Invoke-RestMethod -Uri $url
                    & ([scriptblock]::Create([string]$installer))
                    if (-not $?) { throw '설치 실패' }
                    $code=0
                }
                $status='ok'
            } catch { $status='failed'; $code=1; Write-Host '설치하지 못했습니다. 판매자와 오류 화면을 확인하세요.' }
        }
    }
    $null=$execution.Add([ordered]@{order=$step.order;target=$step.target;status=$status;exitCode=$code})
}
$failed=@($execution | Where-Object {$_.status -eq 'failed'})
if ($failed.Count) { $null=$warnings.Add([ordered]@{level='action';code='INSTALL_FAILED';message='설치에 실패한 항목이 있습니다. 새 터미널에서 상태를 확인하세요.'}) }
$overall='ok'; if($warnings.Count){$overall='caution'}; if($failed.Count){$overall='action'}
$report=[ordered]@{
    schema='ek-setup/0.1'; kitVersion='0.2'; generatedAt=(Get-Date).ToString('o')
    mode=$(if($isDry){'dryrun'}else{'apply'}); profile=$Profile; overall=$overall
    overallLabel=$(if($overall -eq 'ok'){'정상'}elseif($overall -eq 'action'){'확인 필요'}else{'참고 사항 있음'})
    diagnostics=$diag; plan=@($plan); execution=@($execution); warnings=@($warnings)
    privacy=[ordered]@{note='파일 내용·파일 목록·사용자명·컴퓨터명·연락처·IP·홈 경로를 수집하지 않습니다. 리포트는 자동 전송하지 않습니다.'}
}
$null=New-Item -ItemType Directory -Path $ReportDir -Force
$utf8=New-Object Text.UTF8Encoding $true
[IO.File]::WriteAllText((Join-Path $ReportDir 'report.json'),($report | ConvertTo-Json -Depth 10),$utf8)
$lines=@('# AI 작업실 사전 점검','', '보내기 전에 직접 읽어 보세요.','',('모드: '+$report.mode),('프로필: '+$Profile),'','Node·Python 설치 및 업그레이드 없음.','')
foreach ($step in $plan) { $lines += ('- '+$step.target+': '+$step.reason+' / '+$step.command) }
$lines += @('','비밀번호와 인증 코드는 본인이 직접 입력하세요. 로그인은 고객 본인의 유료 계정만 사용하세요.','판매자에게는 먼저 마스킹된 ek-diag.txt만 전달하세요. report.json은 고객 PC의 로컬 점검용입니다.')
[IO.File]::WriteAllLines((Join-Path $ReportDir 'report.md'),$lines,$utf8)
Write-Host '로컬 report.json / report.md를 만들었습니다. 설치 후에는 새 터미널에서 고객 본인이 로그인하세요.'
if ($failed.Count) { exit 1 }; exit 0
