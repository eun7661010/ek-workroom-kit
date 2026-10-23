# D-1 단독 실행. 메신저 붙여넣기 블록에서 이 파일의 해시를 먼저 확인합니다.
[CmdletBinding()]
param(
    [string]$Source,[ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [string]$TargetHome=$env:USERPROFILE,
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Version='0.2.4',
    [switch]$DryRun,[switch]$Apply,[switch]$Library
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false
$OutputEncoding=[Console]::OutputEncoding
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
function Test-EkLink($Item) { return [bool]($Item.LinkType -in @('SymbolicLink','Junction')) }
function File-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Folder-Sha([string]$Path) {
    $base=[IO.Path]::GetFullPath($Path).TrimEnd('\','/')
    if(Test-EkLink (Get-Item -LiteralPath $base -Force)) { throw '연결 폴더는 키트 원본으로 사용할 수 없습니다.' }
    $pending=New-Object 'System.Collections.Generic.Stack[string]'; $pending.Push($base)
    $names=New-Object 'System.Collections.Generic.List[string]'; $paths=@{}
    while($pending.Count) {
        foreach($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if(Test-EkLink $entry) { throw '연결 파일·폴더가 있어 중단합니다.' }
            if($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            else {
                $relative=$entry.FullName.Substring($base.Length+1).Replace('\','/')
                if($relative -match '[\r\n:]' -or $paths.ContainsKey($relative)) { throw '지원하지 않거나 겹치는 파일 이름입니다.' }
                $names.Add($relative); $paths[$relative]=$entry.FullName
            }
        }
    }
    $names.Sort([StringComparer]::Ordinal); $manifest=New-Object Text.StringBuilder
    foreach($relative in $names) { $null=$manifest.Append((File-Sha $paths[$relative])+'  '+$relative+"`n") }
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($manifest.ToString())))).Replace('-','').ToLowerInvariant() } finally {$sha.Dispose()}
}
function Assert-EkZip($Zip) {
    if($Zip.Entries.Count -gt 10000) { throw '압축 파일의 항목 수가 너무 많습니다.' }
    $seen=@{}; [long]$total=0
    foreach($entry in $Zip.Entries) {
        $name=$entry.FullName.Replace('\','/')
        if(-not $name -or $name.StartsWith('/') -or $name -match '[:\r\n]' -or @($name.Split('/') | Where-Object {$_ -in @('.','..')}).Count) { throw '안전하지 않은 압축 경로입니다.' }
        $key=$name.TrimEnd('/'); if($seen.ContainsKey($key)) { throw '중복 압축 경로입니다.' }; $seen[$key]=$true
        $mode=($entry.ExternalAttributes -shr 16) -band 0xF000
        if($mode -eq 0xA000 -or ($entry.ExternalAttributes -band 0x400)) { throw '연결 파일이 들어 있어 중단합니다.' }
        $total+=$entry.Length; if($total -gt 100MB) { throw '키트의 압축 해제 크기가 100MB를 넘습니다.' }
    }
}
function Initialize-EkKit {
    param([string]$Source,[string]$ExpectedSha256,[string]$TargetHome,[string]$Version='0.2.4',[switch]$Prepare)
    if(-not $TargetHome -or -not $Source -or $ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$' -or $Version -notmatch '^[A-Za-z0-9._-]+$') { throw '키트 위치·SHA256·홈 경로·버전을 확인하세요.' }
    $base=Join-Path ([IO.Path]::GetFullPath($TargetHome)) 'ek-workroom'
    $destination=Join-Path $base ('kit-'+$Version)
    $exists=Test-Path -LiteralPath $destination
    if($exists -and (-not(Test-Path -LiteralPath $destination -PathType Container) -or (Test-EkLink (Get-Item -LiteralPath $destination -Force)))) { throw '같은 버전의 키트 위치가 폴더가 아니거나 연결 경로입니다. 판매자와 확인하세요.' }
    $cursor=$base
    while($cursor) {
        if((Test-Path -LiteralPath $cursor) -and (Test-EkLink (Get-Item -LiteralPath $cursor -Force))) { throw '연결된 설치 경로에는 쓰지 않습니다.' }
        $cursor=Split-Path -Parent $cursor
    }
    $null=New-Item -ItemType Directory -Path $base -Force
    $stage=Join-Path $base ('.staging-'+[guid]::NewGuid().ToString('N')); $null=New-Item -ItemType Directory -Path $stage
    $lock=$null; $zip=$null; $cachedSource=$Source
    try {
        $snapshot=Join-Path $stage 'kit.zip'; $folder=Join-Path $stage 'content'; $isFolder=$false
        if($Source -match '^https://') { Invoke-EkDownload -Uri $Source -OutFile $snapshot }
        elseif($Source -match '^\w+://') { throw '다운로드 주소는 https만 사용할 수 있습니다.' }
        elseif(Test-Path -LiteralPath $Source -PathType Container) {
            $isFolder=$true
            $sourceRoot=[IO.Path]::GetFullPath($Source).TrimEnd('\','/')
            if($base -eq $sourceRoot -or $base.StartsWith($sourceRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '키트 원본 폴더 안에 설치 폴더를 만들 수 없습니다. 받은 키트 폴더만 Source로 지정하세요.' }
            if((Folder-Sha $Source) -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.' }
            Copy-Item -LiteralPath $Source -Destination $folder -Recurse
            if((Folder-Sha $folder) -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA256이 다릅니다. 복사 중 원본이 바뀌었습니다.' }
        } elseif(Test-Path -LiteralPath $Source -PathType Leaf) {
            if(Test-EkLink (Get-Item -LiteralPath $Source -Force)) { throw '연결 파일은 사용할 수 없습니다.' }
            Copy-Item -LiteralPath $Source -Destination $snapshot
        } else { throw '받은 키트 파일이나 폴더가 없습니다.' }
        if(-not $isFolder) {
            # 검증·검사·추출 모두 같은 쓰기 금지 핸들을 사용합니다.
            $lock=[IO.File]::Open($snapshot,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
            $sha=[Security.Cryptography.SHA256]::Create()
            try { $actual=([BitConverter]::ToString($sha.ComputeHash($lock))).Replace('-','').ToLowerInvariant() } finally {$sha.Dispose()}
            if($actual -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.' }
            $lock.Position=0; Add-Type -AssemblyName System.IO.Compression; Add-Type -AssemblyName System.IO.Compression.FileSystem
            $zip=New-Object IO.Compression.ZipArchive($lock,[IO.Compression.ZipArchiveMode]::Read,$true)
            Assert-EkZip $zip
            if(-not $Prepare -and $Source -match '^https://') {
                $cachedSource=Join-Path $base ('download-'+$ExpectedSha256.ToLowerInvariant()+'.zip')
                if(Test-Path -LiteralPath $cachedSource) {
                    if((Test-EkLink (Get-Item -LiteralPath $cachedSource -Force)) -or (File-Sha $cachedSource) -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA256이 다릅니다. 기존 다운로드 파일을 판매자와 확인하세요.' }
                } else {
                    $lock.Position=0; $cache=[IO.File]::Open($cachedSource,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                    try {$lock.CopyTo($cache)} finally {$cache.Dispose()}
                }
            }
            if($Prepare -or $exists) {
                $null=New-Item -ItemType Directory -Path $folder
                foreach($entry in $zip.Entries) {
                    $name=$entry.FullName.Replace('\','/'); $target=Join-Path $folder $name
                    if($name.EndsWith('/')) { $null=New-Item -ItemType Directory -Path $target -Force }
                    else { $null=New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force; [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false) }
                }
            }
        }
        Write-Host 'SHA256 일치: 받은 키트를 확인했습니다.'
        if($exists) {
            if((Folder-Sha $destination) -ne (Folder-Sha $folder)) { throw '같은 버전의 키트 폴더 내용 확인값이 다릅니다. 덮어쓰지 않습니다. 판매자와 확인하세요.' }
            Write-Host '키트 배치 완료: 기존 키트와 내용 확인값이 같아 설치 이어 하기를 허용합니다.'
        }
        Write-Host ('설치 예정 위치: '+$destination)
        Write-Host ('설치 후 사용할 세션 플러그인 경로: /plugin marketplace add "'+$destination+'"')
        Write-Host '[계획 1/4] 받은 키트를 검증하고 버전별 고정 위치에 준비합니다. 기존 폴더는 내용 확인값이 같을 때만 그대로 사용합니다.'
        Write-Host '[계획 2/4] Claude Code가 없을 때만 공식 HTTPS 설치 파일을 별도 PowerShell 프로세스에서 실행합니다.'
        Write-Host '[계획 3/4] Codex CLI가 없을 때만 공식 HTTPS 설치 파일을 별도 PowerShell 프로세스에서 실행하고 버전을 확인합니다.'
        Write-Host '[계획 4/4] 고객 본인이 직접 로그인하고 읽기 전용 진단 파일을 확인합니다. 비밀번호·인증 코드를 전달하지 마세요.'
        Write-Host '설치 진행 내용은 현재 창에 표시됩니다. 완료 안내까지 창을 닫지 마세요.'
        Write-Host 'Node·Python 설치와 업그레이드, 사용자 settings 변경은 하지 않습니다.'
        if(-not $Prepare) {
            $safeSource=$cachedSource.Replace("'","''"); $safeHome=$TargetHome.Replace("'","''"); $safeScript=$PSCommandPath.Replace("'","''")
            Write-Host '계획에 동의하면 다음 한 줄 전체를 복사해 실행하세요. 실패 후에도 같은 명령으로 이어 할 수 있으며, 이미 설치된 CLI는 그대로 사용합니다.'
            Write-Host ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File '"+$safeScript+"' -Source '"+$safeSource+"' -ExpectedSha256 "+$ExpectedSha256+" -TargetHome '"+$safeHome+"' -Version "+$Version+' -Apply')
        }
        if($Prepare) {
            if(-not(Test-Path -LiteralPath (Join-Path $folder 'plugins/ek-workroom/scripts/ek-diag.ps1') -PathType Leaf)) { throw '키트 구조가 맞지 않습니다. 판매자에게 다시 요청하세요.' }
            if(-not $exists) { Move-Item -LiteralPath $folder -Destination $destination }
            Write-Host ('키트 배치 완료: '+$destination)
        }
        return $destination
    } finally {
        if($zip) {$zip.Dispose()}; if($lock) {$lock.Dispose()}
        # 검증한 이번 호출의 임시 경로만 정리합니다.
        if([IO.Path]::GetFullPath($stage).StartsWith($base+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
}
function Invoke-EkDownload {
    param([Parameter(Mandatory=$true)][string]$Uri,[Parameter(Mandatory=$true)][string]$OutFile)
    try { Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 60 }
    catch {
        $errorItem=$_.Exception; $tlsFailure=$false
        while($errorItem) {
            if($errorItem -is [Net.WebException] -and $errorItem.Status -in @([Net.WebExceptionStatus]::SecureChannelFailure,[Net.WebExceptionStatus]::TrustFailure)) { $tlsFailure=$true }
            $errorItem=$errorItem.InnerException
        }
        if($tlsFailure) { throw '다운로드 실패: HTTPS/TLS 연결을 확인하지 못했습니다. Windows 날짜·업데이트와 보안 프로그램 차단 기록을 판매자와 확인하세요.' }
        throw '다운로드 실패: 설치 파일을 받지 못했습니다. 인터넷 연결과 보안 프로그램 차단 기록을 판매자와 확인하세요.'
    }
}
function Invoke-EkInstallerFile {
    param([Parameter(Mandatory=$true)][string]$InstallerPath)
    try { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $InstallerPath | ForEach-Object {Write-Host $_} }
    catch { throw '공식 설치 파일 실행 차단 또는 시작 실패: 보안 프로그램 차단 기록·Windows 정책을 판매자와 확인하세요.' }
    $installerExit=$LASTEXITCODE
    if($installerExit -ne 0) { throw ('공식 설치 파일 실행 실패. 종료 코드: '+$installerExit+'. 다운로드는 완료됐습니다. 보안 프로그램 차단 기록과 설치 창의 안내를 판매자와 확인하세요.') }
    return $installerExit
}
function Update-EkProcessPath([string]$TargetHome) {
    $values=@((Join-Path $TargetHome '.local/bin'),$env:PATH,[Environment]::GetEnvironmentVariable('PATH','User'),[Environment]::GetEnvironmentVariable('PATH','Machine'))
    $env:PATH=(@($values -split ';' | Where-Object {$_} | Select-Object -Unique) -join ';')
}
function Invoke-EkCodexInstall {
    param([Parameter(Mandatory=$true)][string]$TargetHome,[Parameter(Mandatory=$true)][string]$KitRoot)
    try {
        Update-EkProcessPath -TargetHome $TargetHome
        if(-not(Get-Command codex -CommandType Application -ErrorAction SilentlyContinue)) {
            $installer=Join-Path $KitRoot ('.codex-install-'+[guid]::NewGuid().ToString('N')+'.ps1')
            try {
                Invoke-EkDownload -Uri 'https://chatgpt.com/codex/install.ps1' -OutFile $installer
                $null=Invoke-EkInstallerFile -InstallerPath $installer
            } finally { if(Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force } }
            Update-EkProcessPath -TargetHome $TargetHome
        } else { Write-Host 'Codex CLI가 이미 있어 그대로 사용합니다.' }
        $command=Get-Command codex -CommandType Application -ErrorAction Stop | Select-Object -First 1
        & $command.Source --version | ForEach-Object { Write-Host $_ }
        if($LASTEXITCODE -ne 0) { throw '버전 확인 실패' }
        Write-Host 'Codex CLI 설치 확인 완료. 고객 본인 계정으로 로그인하세요.'
        return $true
    } catch {
        if($_.Exception.Message -match '^(다운로드 실패|공식 설치)') { Write-Host $_.Exception.Message }
        Write-Host 'Codex 설치 미완료: Claude Code는 유지합니다. 판매자와 설치·로그인을 확인하세요.'
        return $false
    }
}
if($Library) { return }
try {
    $verifiedRoot=Initialize-EkKit -Source $Source -ExpectedSha256 $ExpectedSha256 -TargetHome $TargetHome -Version $Version -Prepare:($Apply -and -not $DryRun)
    if(-not $Apply -or $DryRun) { Write-Host '[DryRun] 검증과 계획만 마쳤습니다. 설치·압축 해제·설정 변경 없음.'; exit 0 }
    Update-EkProcessPath -TargetHome $TargetHome
    if(-not(Get-Command claude -CommandType Application -ErrorAction SilentlyContinue)) {
        $installer=Join-Path $verifiedRoot ('.claude-install-'+[guid]::NewGuid().ToString('N')+'.ps1')
        try {
            Invoke-EkDownload -Uri 'https://claude.ai/install.ps1' -OutFile $installer
            $null=Invoke-EkInstallerFile -InstallerPath $installer
        } finally { if(Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force } }
        Update-EkProcessPath -TargetHome $TargetHome
        $command=Get-Command claude -CommandType Application -ErrorAction Stop | Select-Object -First 1
        if((Get-AuthenticodeSignature -LiteralPath $command.Source).Status -ne 'Valid') { throw 'Claude Code 서명을 확인하지 못했습니다. 실행하지 말고 판매자와 확인하세요.' }
    } else { Write-Host 'Claude Code가 이미 있어 그대로 사용합니다.' }
    Write-Host 'Claude Code 설치 확인 완료.'
    $claudeReady=$true
    $null=Invoke-EkCodexInstall -TargetHome $TargetHome -KitRoot $verifiedRoot
    Write-Host '새 터미널에서 claude를 열고 고객 본인이 로그인하세요. 브라우저가 안 열리면 표시된 URL을 직접 열고, 나온 코드는 본인 Claude 터미널에 붙여 넣으세요. 판매자는 화면 공유를 잠시 멈춥니다.'
    & (Join-Path $verifiedRoot 'plugins/ek-workroom/scripts/ek-diag.ps1') -TargetHome $TargetHome -OutputPath (Join-Path $TargetHome 'ek-diag.txt')
    if(-not $?) { throw '진단을 마치지 못했습니다.' }
    Write-Host ('진단 파일 저장 위치: '+[IO.Path]::GetFullPath((Join-Path $TargetHome 'ek-diag.txt')))
    Write-Host '진단 파일을 직접 읽고 필요한 마스킹을 확인한 뒤 전달하세요. 자동 전송하지 않습니다.'
} catch {
    $safe=[string]$_.Exception.Message
    if($safe -match '^(SHA256|다운로드 실패|다운로드 주소|받은 키트|안전하지 않은|연결|중복 압축|압축 파일|키트의 압축|키트 구조|Claude Code|진단을 마치지|키트 위치|지원하지|같은 버전|공식 설치)') { Write-Host $safe }
    else { Write-Host '검증 또는 준비를 마치지 못했습니다. 설치하지 말고 판매자와 확인하세요.' }
    if($Apply -and -not $DryRun -and $verifiedRoot -and -not $claudeReady) { Write-Host '키트 배치 완료 / Claude 설치 미완료: 원인을 확인한 뒤 앞서 출력한 같은 -Apply 명령으로 설치를 이어 하세요.' }
    exit 1
}
exit 0
