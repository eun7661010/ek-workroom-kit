# 로컬 릴리스 산출물만 만듭니다. 업로드·게시·설치는 하지 않습니다.
[CmdletBinding()]
param(
    [Alias('OutputDir')][string]$OutputDirectory,
    [string]$SourceDirectory,
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Version='0.2.2',
    [ValidatePattern('^https://[A-Za-z0-9][^\s''"`]*$')][string]$ReleaseBaseUrl='https://github.com/eun7661010/ek-workroom-kit/releases/download'
)
$ErrorActionPreference='Stop'
try {
    if(-not $SourceDirectory) { $SourceDirectory=Split-Path -Parent $PSScriptRoot }
    $sourceRoot=[IO.Path]::GetFullPath($SourceDirectory).TrimEnd('\','/')
    if(-not $OutputDirectory) { $OutputDirectory=Join-Path $sourceRoot ('.tmp/release-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)) }
    $outRoot=[IO.Path]::GetFullPath($OutputDirectory)
    foreach($included in @('.claude-plugin','plugins','bootstrap','console','docs','tests')) {
        $includedRoot=(Join-Path $sourceRoot $included).TrimEnd('\','/')
        if($outRoot -eq $includedRoot -or $outRoot.StartsWith($includedRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '출력 폴더는 키트 원본 폴더 밖이나 .tmp 안으로 지정하세요.' }
    }
    if(Test-Path -LiteralPath $outRoot) {
        if(@(Get-ChildItem -LiteralPath $outRoot -Force).Count) { throw '출력 폴더에 파일이 있습니다. 새 빈 폴더를 지정하세요.' }
    } else { $null=New-Item -ItemType Directory -Path $outRoot -Force }
    if((Get-Item -LiteralPath $sourceRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 폴더는 릴리스 원본으로 사용할 수 없습니다.' }
    $stage=Join-Path $outRoot 'staging'
    $null=New-Item -ItemType Directory -Path $stage
    $items=@('.claude-plugin','plugins','bootstrap','console','docs','tests','README.md','.gitattributes')
    $manifestPaths=New-Object 'System.Collections.Generic.List[string]'
    $fileMap=@{}
    function Copy-Safe([string]$src,[string]$dst) {
        $item=Get-Item -LiteralPath $src -Force
        if($item.Name -eq '__pycache__' -or $item.Name -like '*.pyc') { return }
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 파일·폴더가 있어 릴리스를 중단합니다.' }
        if($item.PSIsContainer) {
            $null=New-Item -ItemType Directory -Path $dst -Force
            foreach($child in Get-ChildItem -LiteralPath $src -Force) { Copy-Safe $child.FullName (Join-Path $dst $child.Name) }
        } else {
            if($item.Extension -in @('.sh','.py') -and [Array]::IndexOf([IO.File]::ReadAllBytes($src),[byte]13) -ge 0) { throw 'Mac 실행 파일에 CR 바이트가 있습니다. LF로 저장하고 다시 만드세요.' }
            Copy-Item -LiteralPath $src -Destination $dst
            $relative=$dst.Substring($stage.Length+1).Replace('\','/')
            if($relative -match '[\r\n:]') { throw '지원하지 않는 파일 이름입니다.' }
            if($fileMap.ContainsKey($relative)) { throw '대소문자가 겹치는 파일 이름입니다.' }
            $manifestPaths.Add($relative); $fileMap[$relative]=$dst
        }
    }
    foreach($name in $items) {
        $src=Join-Path $sourceRoot $name
        if(Test-Path -LiteralPath $src) { Copy-Safe $src (Join-Path $stage $name) }
    }
    if(-not(Test-Path -LiteralPath (Join-Path $stage '.claude-plugin/marketplace.json'))) { throw 'marketplace.json이 없는 원본입니다.' }
    $manifestPaths.Sort([StringComparer]::Ordinal)
    $manifest=New-Object Text.StringBuilder
    foreach($name in $manifestPaths) {
        $hash=(Get-FileHash -LiteralPath $fileMap[$name] -Algorithm SHA256).Hash.ToLowerInvariant()
        $null=$manifest.Append($hash+'  '+$name+"`n")
    }
    $utf8=New-Object Text.UTF8Encoding $false
    [IO.File]::WriteAllText((Join-Path $outRoot 'FOLDER-MANIFEST.txt'),$manifest.ToString(),$utf8)
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $folderHash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($manifest.ToString())))).Replace('-','').ToLowerInvariant() } finally {$sha.Dispose()}
    [IO.File]::WriteAllText((Join-Path $outRoot 'FOLDER-SHA256.txt'),$folderHash+"`n",$utf8)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipName='ek-workroom-'+$Version+'.zip'
    $zipPath=Join-Path $outRoot $zipName
    [IO.Compression.ZipFile]::CreateFromDirectory($stage,$zipPath,[IO.Compression.CompressionLevel]::Optimal,$false)
    $sums=New-Object Text.StringBuilder
    $zipHash=(Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $null=$sums.Append($zipHash+'  '+$zipName+"`n")
    foreach($name in @('bootstrap.ps1','bootstrap.sh')) {
        $src=Join-Path $stage ('bootstrap/'+$name)
        if(Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $outRoot $name)
            $hash=(Get-FileHash -LiteralPath (Join-Path $outRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
            $null=$sums.Append($hash+'  '+$name+"`n")
        }
    }
    [IO.File]::WriteAllText((Join-Path $outRoot 'SHA256SUMS.txt'),$sums.ToString(),$utf8)
    $baseUrl=$ReleaseBaseUrl.TrimEnd('/')+'/'+$Version
    $psHash=(Get-FileHash -LiteralPath (Join-Path $outRoot 'bootstrap.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
    $shHash=(Get-FileHash -LiteralPath (Join-Path $outRoot 'bootstrap.sh') -Algorithm SHA256).Hash.ToLowerInvariant()
    # 블록은 메신저로, 실행 파일·ZIP은 HTTPS로 따로 전달합니다.
    $windows=@'
& {
    $ErrorActionPreference = 'Stop'
    $ekVersion = '__VERSION__'
    $ekExpected = '__BOOTSTRAP_HASH__'
    $ekFolder = Join-Path $env:USERPROFILE 'ek-workroom'
    $null = New-Item -ItemType Directory -Path $ekFolder -Force
    $ekFile = Join-Path $ekFolder ('bootstrap-' + $ekVersion + '-' + [guid]::NewGuid().ToString('N') + '.ps1')
    Invoke-WebRequest -UseBasicParsing -Uri '__BASE_URL__/bootstrap.ps1' -OutFile $ekFile
    if ((Get-FileHash -LiteralPath $ekFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ekExpected) { throw '파일 확인값이 다릅니다. 실행하지 말고 판매자에게 알려 주세요.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ekFile -Source '__BASE_URL__/__ZIP_NAME__' -ExpectedSha256 '__ZIP_HASH__' -Version $ekVersion -DryRun
    if ($LASTEXITCODE -ne 0) { throw '미리보기를 마치지 못했습니다. 판매자와 확인하세요.' }
}
'@
    $mac=@'
(
set -eu
ek_version='__VERSION__'
ek_expected='__BOOTSTRAP_HASH__'
mkdir -p "$HOME/ek-workroom"
ek_file=$(mktemp "$HOME/ek-workroom/bootstrap-${ek_version}-XXXXXXXX")
curl --proto '=https' --proto-redir '=https' -fsSL '__BASE_URL__/bootstrap.sh' -o "$ek_file"
ek_actual=$(shasum -a 256 "$ek_file" | cut -d ' ' -f 1)
if [ "$ek_actual" != "$ek_expected" ]; then printf '%s\n' '파일 확인값이 다릅니다. 실행하지 말고 판매자에게 알려 주세요.'; exit 1; fi
bash "$ek_file" --source '__BASE_URL__/__ZIP_NAME__' --expected-sha256 '__ZIP_HASH__' --version "$ek_version" --dry-run
)
'@
    $windows=$windows.Replace('__VERSION__',$Version).Replace('__BOOTSTRAP_HASH__',$psHash).Replace('__BASE_URL__',$baseUrl).Replace('__ZIP_NAME__',$zipName).Replace('__ZIP_HASH__',$zipHash)
    $mac=$mac.Replace('__VERSION__',$Version).Replace('__BOOTSTRAP_HASH__',$shHash).Replace('__BASE_URL__',$baseUrl).Replace('__ZIP_NAME__',$zipName).Replace('__ZIP_HASH__',$zipHash)
    [IO.File]::WriteAllText((Join-Path $outRoot 'paste-block-windows.txt'),$windows.Replace("`r`n","`n").Replace("`n","`r`n")+"`r`n",(New-Object Text.UTF8Encoding $true))
    [IO.File]::WriteAllText((Join-Path $outRoot 'paste-block-mac.txt'),$mac.Replace("`r`n","`n")+"`n",$utf8)
    Write-Host ('릴리스 ZIP 생성: '+$zipName)
    Write-Host ('ZIP SHA256: '+$zipHash)
    Write-Host ('폴더 SHA256: '+$folderHash)
    Write-Host 'SHA256SUMS.txt에는 ZIP과 별도 전달할 bootstrap 파일의 해시가 있습니다. 업로드하지 않았습니다.'
    Write-Host 'paste-block-windows.txt / paste-block-mac.txt를 만들었습니다. 버전 하위 URL에 파일을 올린 뒤 블록을 메신저로 전달하세요.'
    if(([uri]$ReleaseBaseUrl).Host -eq 'example.invalid') { Write-Host '미배포 예시 주소입니다. 실제 고객에게 보내기 전 -ReleaseBaseUrl에 판매자 HTTPS 주소를 지정해 다시 만드세요.' }
} catch { Write-Host ('릴리스를 만들지 못했습니다: '+$_.Exception.Message); exit 1 }
exit 0
