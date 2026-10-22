# 모든 변경 테스트는 저장소 .tmp 아래에서만 실행합니다. 설치 Apply는 호출하지 않습니다.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root ('.tmp/test-' + (Get-Date -Format 'yyyyMMddTHHmmssffff'))
$null = New-Item -ItemType Directory -Path $run -Force
$realHome = $env:USERPROFILE
$savedEnv = @{}
foreach ($key in @('USERPROFILE','HOME','CLAUDE_CONFIG_DIR','CODEX_HOME','TEMP','TMP','PYTHONDONTWRITEBYTECODE')) { $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key,'Process') }
$failures = New-Object 'System.Collections.Generic.List[string]'
function Check([bool]$Condition,[string]$Name) {
    if ($Condition) { Write-Host ('PASS ' + $Name) }
    else { Write-Host ('FAIL ' + $Name); $failures.Add($Name) }
}
function Write-Json([string]$Path,$Object) {
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Object -Depth 64), (New-Object Text.UTF8Encoding $false))
}
function Run-PS([string]$Script,[array]$Arguments) {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>&1 | Out-String
    return @{ Code=$LASTEXITCODE; Output=$output }
}
function Run-Python([string]$Script,[array]$Arguments) {
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & python $Script @Arguments 2>&1 | Out-String
        return @{ Code=$LASTEXITCODE; Output=$output }
    } finally { $ErrorActionPreference = $savedPreference }
}
try {
    Write-Host '보호 대상 실제 홈 해시 기록 중 (읽기 전용)'
    & python "$PSScriptRoot/home_snapshot.py" $realHome "$run/before.json"
    if ($LASTEXITCODE -ne 0) { throw '실제 홈 시작 해시 확인 실패' }
    $env:USERPROFILE = Join-Path $run 'home'
    $env:HOME = $env:USERPROFILE
    $env:CLAUDE_CONFIG_DIR = Join-Path $run 'claude-config'
    $env:CODEX_HOME = Join-Path $run 'codex-config'
    $env:TEMP = Join-Path $run 'os-temp'
    $env:TMP = $env:TEMP
    $env:PYTHONDONTWRITEBYTECODE = '1'
    foreach ($dir in @($env:USERPROFILE,$env:CLAUDE_CONFIG_DIR,$env:CODEX_HOME,$env:TEMP)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    $scripts = Join-Path $root 'plugins/ek-workroom/scripts'

    foreach ($file in @(Get-ChildItem -LiteralPath $root -Filter '*.ps1' -File -Recurse | Where-Object { $_.FullName -notlike "$root\.tmp\*" })) {
        $tokens = $null; $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
        Check ($errors.Count -eq 0) ('PowerShell 문법: ' + $file.Name)
        if ($errors.Count) { Write-Host ($errors | Out-String) }
    }
    $bash = Get-Command bash -CommandType Application -ErrorAction Stop | Select-Object -First 1
    foreach ($file in @(Get-ChildItem -LiteralPath $root -Filter '*.sh' -File -Recurse | Where-Object { $_.FullName -notlike "$root\.tmp\*" })) {
        & $bash.Source -n $file.FullName
        Check ($LASTEXITCODE -eq 0) ('Bash 문법: ' + $file.Name)
    }

    foreach ($name in @('apply-safety','apply-statusline')) {
        foreach ($case in @('absent','existing','invalid')) {
            $homePath = Join-Path $run ($name + '-' + $case)
            $settings = Join-Path $homePath '.claude/settings.json'
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $settings) -Force
            $profilePath = Join-Path $homePath 'profile.json'
            $studentPath = Join-Path $homePath 'StudentRecords'
            $null = New-Item -ItemType Directory -Path $studentPath -Force
            Write-Json $profilePath @{ studentDataPaths=@($studentPath) }
            if ($case -eq 'existing') {
                Write-Json $settings @{ custom=@{keep=$true}; permissions=@{allow=@('Read(README.md)');deny=@('Read(//private/**)');ask=@('Bash(git push *)')}; statusLine=@{padding=2;type='command';command='old-command'} }
            }
            if ($case -eq 'invalid') { [IO.File]::WriteAllText($settings,'{"broken":') }
            $before = if (Test-Path -LiteralPath $settings) { (Get-FileHash $settings).Hash } else { 'ABSENT' }
            $callArgs = @('-TargetHome',$homePath); if ($name -eq 'apply-safety') { $callArgs += @('-ProfilePath',$profilePath) }; $preview = Run-PS "$scripts/$name.ps1" $callArgs
            $afterPreview = if (Test-Path -LiteralPath $settings) { (Get-FileHash $settings).Hash } else { 'ABSENT' }
            Check ($before -eq $afterPreview) "$name $case 미리보기 원본 보존"
            $result = Run-PS "$scripts/$name.ps1" ($callArgs + @('-Apply'))
            if ($case -eq 'invalid') {
                Check ($result.Code -ne 0 -and (Get-FileHash $settings).Hash -eq $before) "$name 잘못된 JSON 거부 및 원본 보존"
                Check (@(Get-ChildItem (Split-Path $settings) -Filter '*.ek-backup-*').Count -eq 0) "$name 잘못된 JSON 백업/쓰기 없음"
                continue
            }
            Check ($preview.Code -eq 0 -and $result.Code -eq 0) "$name $case 실행 성공"
            if ($result.Code -ne 0) { Write-Host $result.Output; continue }
            $value = Get-Content -LiteralPath $settings -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($case -eq 'existing') {
                Check ($value.custom.keep -and $value.permissions.allow -contains 'Read(README.md)' -and $value.permissions.deny -contains 'Read(//private/**)') "$name 기존 설정 보존"
                $backups = @(Get-ChildItem (Split-Path $settings) -Filter 'settings.json.ek-backup-*')
                Check ($backups.Count -eq 1 -and (Get-FileHash $backups[0].FullName).Hash -eq $before) "$name 변경 전 원본 백업"
            }
            if ($name -eq 'apply-safety') {
                $rulePath = $studentPath.Replace('\','/'); $rulePath = '//' + $rulePath.Substring(0,1).ToLowerInvariant() + $rulePath.Substring(2)
                Check ($value.permissions.deny -contains ('Read('+$rulePath+'/**)') -and $value.permissions.deny -contains ('Edit('+$rulePath+'/**)') -and $value.permissions.ask -contains 'Bash' -and $value.permissions.ask -contains 'PowerShell') '안전 규칙 절대 경로·셸 승인'
                Check (@($value.permissions.deny | Select-Object -Unique).Count -eq @($value.permissions.deny).Count) '안전 규칙 중복 없음'
            } else {
                Check ($value.statusLine.type -eq 'command' -and $value.statusLine.command -match 'statusline.ps1' -and (Test-Path "$homePath/.claude/ek-workroom/statusline.ps1")) '상태줄 설정과 실행기 복사'
                if ($case -eq 'existing') { Check ($value.statusLine.padding -eq 2) '상태줄 기존 하위 키 보존' }
            }
            $firstHash = (Get-FileHash $settings).Hash
            $backupCount = @(Get-ChildItem (Split-Path $settings) -Filter 'settings.json.ek-backup-*').Count
            $again = Run-PS "$scripts/$name.ps1" ($callArgs + @('-Apply'))
            Check ($again.Code -eq 0 -and (Get-FileHash $settings).Hash -eq $firstHash -and @(Get-ChildItem (Split-Path $settings) -Filter 'settings.json.ek-backup-*').Count -eq $backupCount) "$name $case 2회 멱등·추가 백업 없음"
        }
    }

    $emptyHome = Join-Path $run 'empty-profile'
    $emptyProfile = Join-Path $emptyHome 'profile.json'
    Write-Json $emptyProfile @{studentDataPaths=@()}
    $emptyResult = Run-PS "$scripts/apply-safety.ps1" @('-TargetHome',$emptyHome,'-ProfilePath',$emptyProfile)
    Check ($emptyResult.Code -ne 0 -and -not (Test-Path "$emptyHome/.claude/settings.json")) '학생정보 보호 경로 누락 거부'

    $private = Join-Path $env:USERPROFILE 'PrivateStudentFolderZZ'
    $null = New-Item -ItemType Directory -Path $private -Force
    [IO.File]::WriteAllText((Join-Path $private 'DummyStudentZZ.txt'),'DummyStudentZZ 010-1234-5678 dummy.student@example.test')
    $diag = Run-PS "$scripts/ek-diag.ps1" @('-TargetHome',$env:USERPROFILE)
    Check ($diag.Code -eq 0) '진단 실행 성공'
    $diagText = $diag.Output + [IO.File]::ReadAllText((Join-Path $env:USERPROFILE 'ek-diag.txt'))
    foreach ($secret in @('PrivateStudentFolderZZ','DummyStudentZZ','010-1234-5678','dummy.student@example.test', (Split-Path $realHome -Leaf),$realHome)) {
        Check (-not $diagText.Contains($secret)) '진단 개인정보·폴더명 누출 0건'
    }
    Check ($diag.Output.TrimStart().StartsWith('보내기 전에 직접 읽어 보세요')) '진단 첫 줄 직접 검토 안내'
    $end = Run-PS "$scripts/ek-end-check.ps1" @('-TargetHome',$env:USERPROFILE)
    Check ($end.Code -eq 0 -and $end.Output -match 'OpenSSH' -and $end.Output -match 'Tailscale' -and $end.Output -match '남은 원격 접속') '종료 점검 읽기 전용 결과'

    $mac = Run-Python "$PSScriptRoot/test_mac_engine.py" @($run)
    Check ($mac.Code -eq 0) 'Mac 공통 엔진 가짜 홈 병합·백업·멱등·진단'
    Write-Host $mac.Output

    $sample = Join-Path $run 'sample'
    $null = New-Item -ItemType Directory -Path $sample -Force
    [IO.File]::WriteAllText((Join-Path $sample 'sample.txt'),'test kit')
    $zip = Join-Path $run 'sample.zip'
    Compress-Archive -LiteralPath (Join-Path $sample 'sample.txt') -DestinationPath $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    $good = Run-PS "$root/bootstrap/bootstrap.ps1" @('-Source',$zip,'-ExpectedSha256',$hash,'-TargetHome',$env:USERPROFILE)
    Check ($good.Code -eq 0 -and $good.Output -match 'DryRun|미리보기') 'bootstrap 해시 일치 DryRun 계획'
    $bad = Run-PS "$root/bootstrap/bootstrap.ps1" @('-Source',$zip,'-ExpectedSha256',('0' * 64),'-TargetHome',$env:USERPROFILE)
    Check ($bad.Code -ne 0) 'bootstrap 해시 불일치 거부'

    $extra = Run-PS "$PSScriptRoot/Test-V011.ps1" @('-RunDirectory',$run)
    Check ($extra.Code -eq 0) 'v0.1.1 인코딩·마스킹·경로·설치격리·릴리스 회귀'
    Write-Host $extra.Output

    $newTests = Run-Python "$PSScriptRoot/test_v020.py" @($run)
    Check ($newTests.Code -eq 0) 'v0.2.1 실행 도구·대상 경계·도구 없는 CLI 시험'
    Write-Host $newTests.Output
    $pdfTests = Run-Python "$PSScriptRoot/test_pdf_isolation.py" @($run)
    Check ($pdfTests.Code -eq 0) 'HTTP 서버 격리·실제 Edge PDF·비밀 이미지 차단'
    Write-Host $pdfTests.Output

    $leaks = @()
    foreach ($file in @(Get-ChildItem "$root/plugins" -File -Recurse)) {
        $raw = [IO.File]::ReadAllText($file.FullName)
        if ($raw -match 'eun76|C:\\Users\\|G:/|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|sk-[A-Za-z0-9_-]{12,}|ANTHROPIC_API_KEY\s*[:=]\s*["''][^"'']+|한도 2배|우회') { $leaks += $file.Name }
        foreach ($line in $raw -split "`n") { if ($line -match 'dangerously-skip-permissions' -and $line -notmatch '금지|사용하지|절대.*않') { $leaks += $file.Name } }
    }
    Check ($leaks.Count -eq 0) '플러그인 개인 경로·비밀·금지 문구 누출 0건'
    if ($leaks.Count) { Write-Host ($leaks -join ', ') }
    $skills = @(Get-ChildItem "$root/plugins/ek-workroom/skills" -Filter SKILL.md -File -Recurse)
    Check ($skills.Count -eq 16) '런북 6개 + 고객 스킬 10개'

    foreach ($path in @($root, "$root/plugins/ek-workroom")) {
        $validation = & claude plugin validate $path 2>&1 | Out-String
        Check ($LASTEXITCODE -eq 0) ('claude plugin validate: ' + $(if ($path -eq $root) { 'marketplace' } else { 'plugin' }))
        Write-Host $validation
    }
    Write-Host 'SKIP 플러그인 설치: 이번 v0.2.1 작업의 설치 금지 지시에 따라 validate와 정적 목록만 확인했습니다.'
} catch {
    $failures.Add('테스트 실행 예외')
    Write-Host ('FAIL 테스트 예외: ' + $_.Exception.Message)
} finally {
    foreach ($key in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($key,$savedEnv[$key],'Process') }
    Write-Host '보호 대상 실제 홈 종료 해시 기록 중 (읽기 전용)'
    & python "$PSScriptRoot/home_snapshot.py" $realHome "$run/after.json"
    Check ($LASTEXITCODE -eq 0 -and (Test-Path "$run/before.json.protected") -and (Get-FileHash "$run/before.json.protected").Hash -eq (Get-FileHash "$run/after.json.protected").Hash) '실제 Claude 설정·Codex 변경 0 (전후 SHA256, OS 잠금 메타데이터, 실행 DB WAL/SHM 분리)'
    if ((Test-Path "$run/before.json.runtime") -and (Test-Path "$run/after.json.runtime") -and (Get-FileHash "$run/before.json.runtime").Hash -ne (Get-FileHash "$run/after.json.runtime").Hash) { Write-Host '참고: 기존 Claude/Codex 실행 상태(.claude.json 또는 DB WAL/SHM)는 자체 갱신되었습니다. 보호 대상 settings.json과 분리한 원본 지문도 .tmp에 보관했습니다.' }
}
if ($failures.Count) { Write-Host ('FAILED: ' + $failures.Count); exit 1 }
Write-Host 'ALL PASSED'; exit 0
