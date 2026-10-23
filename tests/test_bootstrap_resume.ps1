[CmdletBinding()]
param([string]$RunDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not $RunDirectory) { $RunDirectory=Join-Path $root ('.tmp/bootstrap-resume-'+[guid]::NewGuid().ToString('N')) }
if(-not [IO.Path]::GetFullPath($RunDirectory).StartsWith((Join-Path $root '.tmp')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '테스트 폴더는 저장소 .tmp 안으로 지정하세요.' }
$work=Join-Path $RunDirectory 'bootstrap-resume'
$null=New-Item -ItemType Directory -Path $work -Force
$saved=@{}
foreach($key in @('USERPROFILE','HOME','CLAUDE_CONFIG_DIR','CODEX_HOME')) { $saved[$key]=[Environment]::GetEnvironmentVariable($key,'Process') }
function Assert([bool]$Condition,[string]$Name) { if(-not $Condition) { throw ('FAIL '+$Name) }; Write-Host ('PASS '+$Name) }
try {
    $env:USERPROFILE=Join-Path $work 'home'; $env:HOME=$env:USERPROFILE
    $env:CLAUDE_CONFIG_DIR=Join-Path $work 'claude'; $env:CODEX_HOME=Join-Path $work 'codex'
    foreach($dir in @($env:USERPROFILE,$env:CLAUDE_CONFIG_DIR,$env:CODEX_HOME)) { $null=New-Item -ItemType Directory -Path $dir -Force }
    . "$root/bootstrap/bootstrap.ps1" -Library
    $fixture=Join-Path $work 'fixture'
    $null=New-Item -ItemType Directory -Path "$fixture/plugins/ek-workroom/scripts" -Force
    [IO.File]::WriteAllText("$fixture/plugins/ek-workroom/scripts/ek-diag.ps1",'# fixture only')
    [IO.File]::WriteAllText("$fixture/content.txt",'original')
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=Join-Path $work 'kit.zip'; [IO.Compression.ZipFile]::CreateFromDirectory($fixture,$zip)
    $zipHash=File-Sha $zip; $folderHash=Folder-Sha $fixture
    foreach($kind in @('zip','folder')) {
        $homePath=Join-Path $work ($kind+'-home')
        $sourcePath=$zip; $sourceHash=$zipHash
        if($kind -eq 'folder') { $sourcePath=$fixture; $sourceHash=$folderHash }
        $first=Initialize-EkKit -Source $sourcePath -ExpectedSha256 $sourceHash -TargetHome $homePath -Prepare
        $content=Join-Path $first 'content.txt'; $stamp=(Get-Item $content).LastWriteTimeUtc
        $again=Initialize-EkKit -Source $sourcePath -ExpectedSha256 $sourceHash -TargetHome $homePath -Prepare
        Assert ($first -eq $again -and (Folder-Sha $first) -eq $folderHash -and (Get-Item $content).LastWriteTimeUtc -eq $stamp) "$kind 동일 내용 재개·기존 파일 보존"
        $preview=Initialize-EkKit -Source $sourcePath -ExpectedSha256 $sourceHash -TargetHome $homePath
        Assert ($preview -eq $first -and (Folder-Sha $first) -eq $folderHash) "$kind 기존 키트 미리보기 허용"
        [IO.File]::WriteAllText($content,'modified')
        $rejected=$false
        try { $null=Initialize-EkKit -Source $sourcePath -ExpectedSha256 $sourceHash -TargetHome $homePath -Prepare } catch { $rejected=$_.Exception.Message -match '내용 확인값이 다릅니다' }
        Assert ($rejected -and [IO.File]::ReadAllText($content) -eq 'modified') "$kind 다른 내용 거부·덮어쓰기 없음"
        Assert (@(Get-ChildItem -LiteralPath (Join-Path $homePath 'ek-workroom') -Filter '.staging-*' -Force).Count -eq 0) "$kind 임시 검증 경로 정리"
    }
    $previewHome=Join-Path $work 'preview-home'
    $output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$root/bootstrap/bootstrap.ps1" -Source $zip -ExpectedSha256 $zipHash -TargetHome $previewHome -DryRun | Out-String
    Assert ($LASTEXITCODE -eq 0 -and $output.IndexOf('[계획 4/4]') -lt $output.IndexOf('계획에 동의하면') -and $output -match '설치 예정 위치' -and $output -match '현재 창') '미리보기 계획 후 Apply·예정 위치·현재 창 안내'
    Assert (-not(Test-Path (Join-Path $previewHome 'ek-workroom/kit-0.2.3'))) '미리보기 키트 배치·설치 없음'
    function Invoke-WebRequest { throw (New-Object Net.WebException('fixture TLS',$null,[Net.WebExceptionStatus]::SecureChannelFailure,$null)) }
    $tls=$false; try { Invoke-EkDownload -Uri 'https://example.invalid' -OutFile (Join-Path $work 'never') } catch { $tls=$_.Exception.Message -match '다운로드 실패: HTTPS/TLS' }
    Assert $tls 'TLS 협상 실패 별도 안내'
    function Invoke-WebRequest { throw (New-Object Net.WebException('fixture network')) }
    $download=$false; try { Invoke-EkDownload -Uri 'https://example.invalid' -OutFile (Join-Path $work 'never') } catch { $download=$_.Exception.Message -match '다운로드 실패: 설치 파일' -and $_.Exception.Message -match '보안 프로그램 차단 기록' }
    Assert $download '일반 다운로드 실패·보안 기록 안내'
    Assert (([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12) -ne 0) 'TLS 1.2 활성화'
    Write-Host 'BOOTSTRAP RESUME PASSED'
} catch { Write-Host $_.Exception.Message; exit 1 }
finally { foreach($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') } }
exit 0
