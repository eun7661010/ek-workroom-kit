[CmdletBinding()]
param([string]$TargetHome = $env:USERPROFILE, [string]$OutputPath, [switch]$Apply, [switch]$DryRun)
. "$PSScriptRoot/common.ps1"
function Get-EkVersion([string]$Name) {
    $cmd = Get-Command $Name -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { return '없음' }
    if ($Name -eq 'python' -and $cmd.Source -like '*\WindowsApps\*') { return '없음 (실행 별칭)' }
    try {
        $raw = (& $cmd.Source --version 2>$null | Out-String)
        if ($raw -match '(?<![\d.])\d+(?:\.\d+){1,4}(?![\d.])') { return $Matches[0] }
    } catch { }
    return '설치됨 / 버전 확인 불가'
}
function Test-EkNetwork([string]$Domain) {
    try {
        $request = [Net.HttpWebRequest]::Create('https://' + $Domain)
        $request.Method = 'HEAD'; $request.Timeout = 4000; $request.AllowAutoRedirect = $false
        $response = $request.GetResponse(); $response.Close(); return '도달함'
    } catch [Net.WebException] {
        if ($_.Exception.Response) { $_.Exception.Response.Close(); return '도달함 (접근 제한 응답)' }
        return '확인 불가'
    } catch { return '확인 불가' }
}
try {
    $lines = New-Object 'System.Collections.Generic.List[string]'
    $lines.Add('보내기 전에 직접 읽어 보세요')
    $lines.Add('AI 작업실 진단: 파일 내용·폴더 목록·계정 정보는 수집하지 않습니다.')
    $lines.Add('사용자 <USER> / 컴퓨터 <COMPUTER> / 홈 <HOME>')
    $lines.Add('OS: Windows ' + [Environment]::OSVersion.Version.ToString())
    foreach ($name in @('claude','codex','git','node','python','winget')) { $lines.Add($name + ': ' + (Get-EkVersion $name)) }
    $lines.Add('PowerShell: ' + $PSVersionTable.PSVersion.ToString())
    $lines.Add('PATH 항목 수: ' + @($env:PATH.Split(';') | Where-Object { $_ }).Count)
    try {
        $drive = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($TargetHome)))
        $lines.Add('디스크 여유 GB: ' + [Math]::Round($drive.AvailableFreeSpace / 1GB, 1))
    } catch { $lines.Add('디스크 여유: 확인 불가') }
    $lines.Add('실행 정책: ' + (Get-ExecutionPolicy))
    try {
        $av = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop)
        $known = @('Defender','AhnLab','V3','ALYac','Kaspersky','Norton','McAfee','Avast','ESET','Bitdefender','CrowdStrike','SentinelOne')
        $names = @($known | Where-Object { $needle = $_; @($av | Where-Object { $_.displayName -match [regex]::Escape($needle) }).Count -gt 0 })
        $lines.Add('보안 SW: ' + $(if ($names.Count) { $names -join ', ' } elseif ($av.Count) { '기타 보안 SW (이름 비공개)' } else { '등록 정보 없음' }))
    } catch { $lines.Add('보안 SW: 확인 불가') }
    foreach ($domain in @('claude.ai','chatgpt.com')) { $lines.Add($domain + ': ' + (Test-EkNetwork $domain)) }
    $result = $lines -join [Environment]::NewLine
    # 숫자 버전과 고정 라벨만 출력. 추가 방어로 식별정보도 치환합니다.
    foreach ($pair in @(@($env:USERPROFILE,'<HOME>'),@($TargetHome,'<HOME>'),@($env:USERNAME,'<USER>'),@($env:COMPUTERNAME,'<COMPUTER>'))) {
        if ($pair[0] -and $pair[0].Length -gt 2) { $result = [regex]::Replace($result,[regex]::Escape($pair[0]),$pair[1],'IgnoreCase') }
    }
    $result = $result -replace '[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','<EMAIL>' -replace '01[016789][- ]?\d{3,4}[- ]?\d{4}','<PHONE>'
    $result = [regex]::Replace($result, '(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', {
        param($match)
        if (@($match.Value.Split('.') | Where-Object { [int]$_ -gt 255 }).Count -eq 0) { return '<IP>' }
        return $match.Value
    })
    if (-not $OutputPath) { $OutputPath = Join-Path $TargetHome 'ek-diag.txt' }
    $fullOutput = [IO.Path]::GetFullPath($OutputPath)
    $homePrefix = [IO.Path]::GetFullPath($TargetHome).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $fullOutput.StartsWith($homePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw '진단 저장은 지정한 홈 안에서만 가능합니다.' }
    Assert-EkSafePath $fullOutput
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $fullOutput)
    [IO.File]::WriteAllText($fullOutput,$result,(New-Object Text.UTF8Encoding $true))
    Write-Output $result
} catch { Write-Output '진단 실패: 저장 위치 또는 실행 권한을 확인하세요. 원본 파일은 읽지 않았습니다.'; exit 1 }
