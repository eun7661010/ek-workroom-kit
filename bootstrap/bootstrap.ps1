# D-1 고객 실행. 먼저 파일 자체의 SHA256을 별도 전달값과 비교하세요.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSha256,
    [string]$TargetHome=$env:USERPROFILE,
    [switch]$DryRun,
    [switch]$Apply
)
$ErrorActionPreference='Stop'
$kitRoot=Split-Path -Parent $PSScriptRoot
function File-Sha([string]$path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Folder-Sha([string]$path) {
    $base=[IO.Path]::GetFullPath($path).TrimEnd('\','/')
    if ((Get-Item -LiteralPath $base -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 폴더는 사용할 수 없습니다.' }
    $pending=New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($base)
    $names=New-Object 'System.Collections.Generic.List[string]'
    $paths=@{}
    while($pending.Count) {
        foreach($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 파일·폴더가 있어 중단합니다.' }
            if($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            else {
                $relative=$entry.FullName.Substring($base.Length+1).Replace('\','/')
                if($relative -match '[\r\n:]') { throw '지원하지 않는 파일 이름입니다.' }
                if($paths.ContainsKey($relative)) { throw '대소문자가 겹치는 파일 이름입니다.' }
                $names.Add($relative); $paths[$relative]=$entry.FullName
            }
        }
    }
    $names.Sort([StringComparer]::Ordinal)
    $manifest=New-Object Text.StringBuilder
    foreach($relative in $names) { $null=$manifest.Append((File-Sha $paths[$relative])+'  '+$relative+"`n") }
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($manifest.ToString())))).Replace('-','').ToLowerInvariant() } finally {$sha.Dispose()}
}
function Check-Zip([string]$path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=[IO.Compression.ZipFile]::OpenRead($path)
    try {
        if($zip.Entries.Count -gt 10000) { throw '압축 파일의 항목 수가 너무 많습니다.' }
        $seen=@{}; [long]$total=0
        foreach($entry in $zip.Entries) {
            $name=$entry.FullName.Replace('\','/')
            if(-not $name -or $name.StartsWith('/') -or $name -match '[:\r\n]' -or @($name.Split('/') | Where-Object {$_ -in @('.','..')}).Count) { throw '안전하지 않은 압축 경로입니다.' }
            $key=$name.TrimEnd('/')
            if($seen.ContainsKey($key)) { throw '중복 압축 경로입니다.' }; $seen[$key]=$true
            $mode=($entry.ExternalAttributes -shr 16) -band 0xF000
            if($mode -eq 0xA000 -or ($entry.ExternalAttributes -band 0x400)) { throw '연결 파일이 들어 있어 중단합니다.' }
            $total+=$entry.Length
            if($total -gt 100MB) { throw '키트의 압축 해제 크기가 100MB를 넘습니다.' }
        }
    } finally {$zip.Dispose()}
}
try {
    if(-not $TargetHome) { throw '홈 경로를 확인할 수 없습니다. -TargetHome을 지정하세요.' }
    $sourcePath=$Source
    $staging=$null
    if($Source -match '^https://') {
        $staging=Join-Path $kitRoot ('.tmp/bootstrap-'+[guid]::NewGuid().ToString('N'))
        $null=New-Item -ItemType Directory -Path $staging -Force
        $sourcePath=Join-Path $staging 'kit.zip'
        Invoke-WebRequest -Uri $Source -OutFile $sourcePath -UseBasicParsing -TimeoutSec 60
    } elseif($Source -match '^\w+://') { throw '다운로드 주소는 https만 사용할 수 있습니다.' }
    if(-not(Test-Path -LiteralPath $sourcePath)) { throw '받은 키트 파일이나 폴더가 없습니다.' }
    if((Get-Item -LiteralPath $sourcePath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 파일·폴더는 사용할 수 없습니다.' }
    $isFolder=Test-Path -LiteralPath $sourcePath -PathType Container
    if($isFolder) {$actual=Folder-Sha $sourcePath} else {$actual=File-Sha $sourcePath}
    if($actual -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.' }
    if(-not $isFolder) { Check-Zip $sourcePath }
    Write-Host 'SHA256 일치: 받은 키트를 확인했습니다.'
    Write-Host '[계획 1/3] Claude Code가 없을 때만 공식 네이티브 설치: irm https://claude.ai/install.ps1 | iex'
    Write-Host '[계획 2/3] 고객 본인의 유료 계정으로 claude를 열어 직접 로그인합니다. 비밀번호·인증 코드를 전달하지 마세요.'
    Write-Host '[계획 3/3] 읽기 전용 진단으로 ek-diag.txt를 만듭니다. 보내기 전에 직접 읽어 보세요.'
    Write-Host 'Node·Python 설치와 업그레이드, 사용자 settings 변경은 하지 않습니다.'
    if(-not $Apply -or $DryRun) { Write-Host '[DryRun] 검증과 계획만 마쳤습니다. 설치·압축 해제·설정 변경 없음.'; exit 0 }
    $verifiedRoot=$sourcePath
    if(-not $isFolder) {
        if(-not $staging) {
            $staging=Join-Path $kitRoot ('.tmp/bootstrap-'+[guid]::NewGuid().ToString('N'))
            $null=New-Item -ItemType Directory -Path $staging -Force
        }
        $verifiedRoot=Join-Path $staging 'kit'
        # 검사한 zip을 새 폴더에만 풀어 기존 파일을 덮어쓰지 않습니다.
        [IO.Compression.ZipFile]::ExtractToDirectory($sourcePath,$verifiedRoot)
    }
    $diag=Join-Path $verifiedRoot 'plugins/ek-workroom/scripts/ek-diag.ps1'
    if(-not(Test-Path -LiteralPath $diag -PathType Leaf)) { throw '키트 구조가 맞지 않습니다. 판매자에게 다시 요청하세요.' }
    if(-not(Get-Command claude -CommandType Application -ErrorAction SilentlyContinue)) {
        $installer=Invoke-RestMethod -Uri 'https://claude.ai/install.ps1'
        & ([scriptblock]::Create([string]$installer))
        if(-not $?) { throw 'Claude Code 설치를 마치지 못했습니다.' }
    } else { Write-Host 'Claude Code가 이미 있어 그대로 사용합니다.' }
    Write-Host '새 터미널에서 claude를 열고 고객 본인이 로그인하세요. 판매자는 자리를 비우거나 화면 공유를 잠시 멈춥니다.'
    & $diag -TargetHome $TargetHome -OutputPath (Join-Path $TargetHome 'ek-diag.txt')
    if(-not $?) { throw '진단을 마치지 못했습니다.' }
    Write-Host '진단 파일을 직접 읽고 필요한 마스킹을 확인한 뒤 전달하세요. 자동 전송하지 않습니다.'
} catch {
    # 오류 원문에는 경로나 서버 응답이 있을 수 있어 출력하지 않습니다.
    $safe=[string]$_.Exception.Message
    if($safe -match '^(SHA256|다운로드 주소|받은 키트|안전하지 않은|연결 파일|연결 폴더|중복 압축|압축 파일|키트의 압축|키트 구조|Claude Code 설치|진단을 마치지|홈 경로|지원하지 않는|대소문자)') { Write-Host $safe }
    else { Write-Host '검증 또는 준비를 마치지 못했습니다. 설치하지 말고 판매자와 확인하세요.' }
    exit 1
}
exit 0
