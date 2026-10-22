[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RunDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not [IO.Path]::GetFullPath($RunDirectory).StartsWith((Join-Path $root '.tmp')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '테스트 폴더는 저장소 .tmp 안으로 지정하세요.' }
$work=Join-Path $RunDirectory 'v011'
$null=New-Item -ItemType Directory -Force -Path $work
# 단독 실행 때에도 메신저 블록이 실제 홈에 파일을 만들 수 없게 격리합니다.
$env:USERPROFILE=Join-Path $work 'isolated-home'
$env:HOME=$env:USERPROFILE
$env:CLAUDE_CONFIG_DIR=Join-Path $work 'claude-config'
$env:CODEX_HOME=Join-Path $work 'codex-config'
$env:TEMP=Join-Path $work 'temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
foreach($dir in @($env:USERPROFILE,$env:CLAUDE_CONFIG_DIR,$env:CODEX_HOME,$env:TEMP)) { $null=New-Item -ItemType Directory -Path $dir -Force }
function Assert([bool]$Condition,[string]$Name) { if(-not $Condition) { throw ('FAIL '+$Name) }; Write-Host ('PASS '+$Name) }
function Call-PS([string]$Script,[array]$Arguments) {
    $output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>&1 | Out-String
    return @{Code=$LASTEXITCODE;Output=$output}
}
function Save-Json([string]$Path,$Value,[Text.Encoding]$Encoding=(New-Object Text.UTF8Encoding $false)) {
    $null=New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)
    [IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 64),$Encoding)
}
try {
    $scripts=Join-Path $root 'plugins/ek-workroom/scripts'
    $homePath=Join-Path $work 'encoding-home'
    $student=Join-Path $homePath '학생정보(2026)'
    $null=New-Item -ItemType Directory -Force -Path $student
    $profile=Join-Path $homePath 'profile.json'
    $settings=Join-Path $homePath '.claude/settings.json'
    Save-Json $profile @{studentDataPaths=@($student);accountLabel='업무용'}
    foreach($action in @('apply-safety','apply-statusline')) {
        Save-Json $settings @{custom='한글 보존';permissions=@{allow=@('Read(README.md)')}} ([Text.Encoding]::GetEncoding(949))
        $before=(Get-FileHash $settings).Hash
        $bad=Call-PS "$scripts/$action.ps1" @('-TargetHome',$homePath,'-ProfilePath',$profile,'-Apply')
        Assert ($bad.Code -ne 0 -and (Get-FileHash $settings).Hash -eq $before -and $bad.Output -match 'UTF-8') "$action CP949 설정 거부·원본 보존·안전 오류"
        Save-Json $settings @{custom='한글 보존';permissions=@{allow=@('Read(README.md)')}} (New-Object Text.UTF8Encoding $true)
        $good=Call-PS "$scripts/$action.ps1" @('-TargetHome',$homePath,'-ProfilePath',$profile,'-Apply')
        Assert ($good.Code -eq 0 -and (Get-Content -Raw -Encoding UTF8 $settings|ConvertFrom-Json).custom -eq '한글 보존') "$action UTF-8 BOM 설정 병합"
    }
    Save-Json $profile @{studentDataPaths=@($student);accountLabel='업무용'} ([Text.Encoding]::GetEncoding(949))
    $badProfile=Call-PS "$scripts/apply-safety.ps1" @('-TargetHome',$homePath,'-ProfilePath',$profile)
    Assert ($badProfile.Code -ne 0 -and $badProfile.Output -match 'UTF-8') 'CP949 프로필 거부'
    Save-Json $profile @{studentDataPaths=@($student);accountLabel='업무용'} (New-Object Text.UTF8Encoding $true)
    . "$scripts/common.ps1"
    $secret='은광 원장 010.1234.5678 02-123-4567 0507-1234-5678 10.20.30.40 2001:db8::1234'
    $masked=Sanitize-EkText -Text $secret -TargetHome $homePath -UserName '은광' -ComputerName '원장'
    foreach($token in @('은광','원장','010.1234.5678','02-123-4567','0507-1234-5678','10.20.30.40','2001:db8::1234')) { Assert (-not $masked.Contains($token)) '두 글자 이름·전화·IPv4/IPv6 마스킹' }
    foreach($badFolder in @((Join-Path $homePath 'missing'),$homePath,[IO.Path]::GetPathRoot($homePath))) {
        $rejected=$false;try { $null=Get-EkStudentPaths $badFolder $homePath } catch { $rejected=$true }
        Assert $rejected '없는 폴더·홈 전체·드라이브 루트 거부'
    }
    $actual=Join-Path $homePath 'RealStudentFolder'
    $link=Join-Path $homePath 'StudentAlias'
    $null=New-Item -ItemType Directory -Path $actual
    $null=New-Item -ItemType Junction -Path $link -Target $actual
    Save-Json $profile @{studentDataPaths=@($link.ToLowerInvariant());accountLabel='업무용'}
    $safety=Call-PS "$scripts/apply-safety.ps1" @('-TargetHome',$homePath,'-ProfilePath',$profile,'-Apply')
    Assert ($safety.Code -eq 0) '학생 연결 폴더 허용'
    $denies=(Get-Content -Raw -Encoding UTF8 $settings|ConvertFrom-Json).permissions.deny
    foreach($path in @($link.ToLowerInvariant(),$actual)) {
        $anchor=$path.Replace('\','/');$anchor='//'+$anchor.Substring(0,1).ToLowerInvariant()+$anchor.Substring(2)
        Assert (@($denies|Where-Object { [string]::Equals($_,('Read('+$anchor+'/**)'),[StringComparison]::Ordinal) }).Count -gt 0) '입력 경로와 실제 대소문자 경로 모두 deny'
    }
    $safeOutput=Sanitize-EkText -Text ($homePath.Replace('\','/')+' '+$homePath) -TargetHome $homePath
    Assert (-not $safeOutput.Contains($homePath) -and -not $safeOutput.Contains($homePath.Replace('\','/'))) '홈 경로 구분자 변형 마스킹'

    # 라이브러리 API의 준비는 파일 배치만 하며 설치를 호출하지 않습니다.
    . "$root/bootstrap/bootstrap.ps1" -Library -TargetHome $homePath
    $mockOk=Join-Path $work 'installer-ok.ps1'
    $mockBad=Join-Path $work 'installer-fail.ps1'
    [IO.File]::WriteAllText($mockOk,"exit 0`r`n",(New-Object Text.UTF8Encoding $true))
    [IO.File]::WriteAllText($mockBad,"exit 7`r`n",(New-Object Text.UTF8Encoding $true))
    $null=Invoke-EkInstallerFile -InstallerPath $mockOk
    Assert $true '가짜 공식 설치 exit 0 뒤 부모 실행 계속'
    $badExit=$false;try {$null=Invoke-EkInstallerFile -InstallerPath $mockBad} catch {$badExit=$true}
    Assert $badExit '가짜 공식 설치 비0 종료 전달'
    $savedPath=$env:PATH
    Update-EkProcessPath -TargetHome $homePath
    Assert ($env:PATH.Contains((Join-Path $homePath '.local/bin'))) '설치 후 현재 프로세스 PATH 보강'
    $env:PATH=$savedPath

    $fixture=Join-Path $work 'fixture'
    Save-Json "$fixture/.claude-plugin/marketplace.json" @{name='ek-workroom';owner=@{name='Test'};plugins=@()}
    Save-Json "$fixture/plugins/ek-workroom/.claude-plugin/plugin.json" @{name='ek-workroom';version='0.1.1'}
    $null=New-Item -ItemType Directory -Force "$fixture/plugins/ek-workroom/scripts"
    [IO.File]::WriteAllText("$fixture/plugins/ek-workroom/scripts/ek-diag.ps1","Write-Output 'FAKE_DIAG'`r`n")
    $zip=Join-Path $work 'fixture.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($fixture,$zip)
    $hash=(Get-FileHash $zip).Hash
    $prepareHome=Join-Path $work 'prepare-home';$null=New-Item -ItemType Directory $prepareHome
    $prepared=Initialize-EkKit -Source $zip -ExpectedSha256 $hash -TargetHome $prepareHome -Version '0.1.1' -Prepare
    $expected=Join-Path $prepareHome 'ek-workroom/kit-0.1.1'
    Assert ($prepared -eq $expected -and (Test-Path "$expected/plugins/ek-workroom/scripts/ek-diag.ps1")) '고정 설치 위치에 검증한 키트만 준비'
    $already=$false;try { $null=Initialize-EkKit -Source $zip -ExpectedSha256 $hash -TargetHome $prepareHome -Version '0.1.1' -Prepare } catch {$already=$true}
    Assert $already '같은 고정 위치 재실행 거부'

    $release=Join-Path $work 'release'
    $built=Call-PS "$root/bootstrap/make-release.ps1" @('-OutputDirectory',$release,'-ReleaseBaseUrl','https://release.example.test/kit','-Version','0.1.1')
    Assert ($built.Code -eq 0) 'v0.1.1 릴리스 생성'
    foreach($name in @('paste-block-windows.txt','paste-block-mac.txt')) {
        $block=[IO.File]::ReadAllText((Join-Path $release $name))
        Assert ($block -match '0.1.1' -and $block -match 'https://release.example.test/kit/0.1.1' -and $block -notmatch '__[A-Z_]+__' -and $block -match '[a-f0-9]{64}') "$name 버전·HTTPS·해시 채움"
    }
    $checks=& python "$PSScriptRoot/test_v011.py" $work $release 2>&1 | Out-String
    Assert ($LASTEXITCODE -eq 0) 'UTF-8 상태줄·Mac 경로·붙여넣기 블록·ZIP 개행·제어문자 회귀'
    Write-Host $checks
} catch { Write-Host $_.Exception.Message; exit 1 }
exit 0
