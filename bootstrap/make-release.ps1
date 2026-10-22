# 로컬 릴리스 산출물만 만듭니다. 업로드·게시·설치는 하지 않습니다.
[CmdletBinding()]
param(
    [Alias('OutputDir')][string]$OutputDirectory,
    [string]$SourceDirectory,
    [ValidatePattern('^[A-Za-z0-9._-]+$')][string]$Version='0.1.0'
)
$ErrorActionPreference='Stop'
try {
    if(-not $SourceDirectory) { $SourceDirectory=Split-Path -Parent $PSScriptRoot }
    $sourceRoot=[IO.Path]::GetFullPath($SourceDirectory).TrimEnd('\','/')
    if(-not $OutputDirectory) { $OutputDirectory=Join-Path $sourceRoot ('.tmp/release-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)) }
    $outRoot=[IO.Path]::GetFullPath($OutputDirectory)
    foreach($included in @('.claude-plugin','plugins','bootstrap','kit','console','docs','tests')) {
        $includedRoot=(Join-Path $sourceRoot $included).TrimEnd('\','/')
        if($outRoot -eq $includedRoot -or $outRoot.StartsWith($includedRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw '출력 폴더는 키트 원본 폴더 밖이나 .tmp 안으로 지정하세요.' }
    }
    if(Test-Path -LiteralPath $outRoot) {
        if(@(Get-ChildItem -LiteralPath $outRoot -Force).Count) { throw '출력 폴더에 파일이 있습니다. 새 빈 폴더를 지정하세요.' }
    } else { $null=New-Item -ItemType Directory -Path $outRoot -Force }
    if((Get-Item -LiteralPath $sourceRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 폴더는 릴리스 원본으로 사용할 수 없습니다.' }
    $stage=Join-Path $outRoot 'staging'
    $null=New-Item -ItemType Directory -Path $stage
    $items=@('.claude-plugin','plugins','bootstrap','kit','console','docs','tests','README.md')
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
    Write-Host ('릴리스 ZIP 생성: '+$zipName)
    Write-Host ('ZIP SHA256: '+$zipHash)
    Write-Host ('폴더 SHA256: '+$folderHash)
    Write-Host 'SHA256SUMS.txt에는 ZIP과 별도 전달할 bootstrap 파일의 해시가 있습니다. 업로드하지 않았습니다.'
} catch { Write-Host ('릴리스를 만들지 못했습니다: '+$_.Exception.Message); exit 1 }
exit 0
