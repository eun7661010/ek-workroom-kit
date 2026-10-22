# Windows PowerShell 5.1 이상. 설정 파일만 읽고 쓰며 학생 폴더는 열지 않습니다.
$ErrorActionPreference = 'Stop'
function ConvertTo-EkMap($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $map = [ordered]@{}
        foreach ($p in $Value.PSObject.Properties) { $map[$p.Name] = ConvertTo-EkMap $p.Value }
        return $map
    }
    if ($Value -is [array]) { return ,@($Value | ForEach-Object { ConvertTo-EkMap $_ }) }
    return $Value
}
function Read-EkObject([string]$Path) {
    $raw = [IO.File]::ReadAllText($Path)
    if (-not $raw.TrimStart().StartsWith('{')) { throw 'JSON 객체 형식이 아닙니다. 원본을 유지합니다.' }
    try { $value = ConvertTo-EkMap (ConvertFrom-Json -InputObject $raw) }
    catch { throw 'JSON을 읽을 수 없습니다. 원본을 유지합니다. 판매자와 확인하세요.' }
    return $value
}
function Assert-EkSafePath([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결된 경로에는 쓰지 않습니다. 일반 폴더를 선택하세요.' }
        }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }; $cursor = $parent
    }
}
function Get-EkSettings([string]$TargetHome) {
    if (-not [IO.Path]::IsPathRooted($TargetHome)) { throw '홈 경로는 절대 경로로 입력하세요.' }
    $path = Join-Path $TargetHome '.claude/settings.json'
    Assert-EkSafePath $path
    $value = [ordered]@{}
    if (Test-Path -LiteralPath $path) { $value = Read-EkObject $path }
    return @{ Path = $path; Value = $value }
}
function Set-EkField($Map, [string]$Key, $Value) { $Map[$Key] = $Value }
function Save-EkSettings($State, [bool]$DoApply) {
    $json = ConvertTo-Json -InputObject $State.Value -Depth 64
    $before = ''
    if (Test-Path -LiteralPath $State.Path) { $before = [IO.File]::ReadAllText($State.Path) }
    if ($before -eq $json) { Write-Output '이미 같은 설정입니다. 변경과 새 백업이 없습니다.'; return }
    if (-not $DoApply) { Write-Output '미리보기(DryRun): 아래 설정을 병합합니다. 아직 저장하지 않았습니다.'; Write-Output $json; return }
    Assert-EkSafePath $State.Path
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $State.Path)
    if (Test-Path -LiteralPath $State.Path) {
        $backup = $State.Path + '.ek-backup-' + (Get-Date -Format 'yyyyMMddTHHmmssfffffff')
        [IO.File]::Copy($State.Path, $backup, $false)
    }
    $temp = $State.Path + '.ek-write-' + [guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temp, $json, (New-Object Text.UTF8Encoding $false))
    if (Test-Path -LiteralPath $State.Path) { [IO.File]::Replace($temp, $State.Path, [NullString]::Value) }
    else { [IO.File]::Move($temp, $State.Path) }
    Write-Output '설정을 저장했습니다. 기존 설정이 있었다면 수정 전 백업도 보관했습니다.'
}
function Merge-EkRules($Permissions, [string]$Key, [string[]]$Rules) {
    if ($Permissions.Contains($Key) -and $Permissions[$Key] -isnot [array]) { throw '권한 목록은 배열이어야 합니다. 원본을 유지합니다.' }
    $merged = New-Object 'System.Collections.Generic.List[string]'
    foreach ($rule in @($Permissions[$Key]) + $Rules) {
        if ($null -ne $rule -and $rule -isnot [string]) { throw '권한 항목은 문자열이어야 합니다.' }
        if ($rule -and -not $merged.Contains($rule)) { $merged.Add($rule) }
    }
    $Permissions[$Key] = @($merged.ToArray())
}
function Get-EkProfile([string]$ProfilePath) {
    if (-not $ProfilePath) { throw '고객 프로필 파일을 지정하세요.' }
    $p = Read-EkObject $ProfilePath
    if (-not $p.Contains('studentDataPaths') -or $p.studentDataPaths -isnot [array] -or $p.studentDataPaths.Count -lt 1) { throw '프로필에 학생정보 폴더를 1개 이상 입력하세요. 없으면 판매자와 범위를 다시 확인하세요.' }
    return $p
}
