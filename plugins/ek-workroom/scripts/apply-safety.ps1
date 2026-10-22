[CmdletBinding()]
param([string]$TargetHome = $env:USERPROFILE, [Parameter(Mandatory=$true)][string]$ProfilePath, [switch]$Apply, [switch]$DryRun)
. "$PSScriptRoot/common.ps1"
try {
    $p = Get-EkProfile $ProfilePath
    $s = Get-EkSettings $TargetHome
    if (-not $s.Value.Contains('permissions')) { $s.Value.permissions = [ordered]@{} }
    $perm = $s.Value.permissions
    if ($perm -isnot [System.Collections.IDictionary]) { Throw-EkInput 'permissions 객체를 확인하세요. 원본을 유지합니다.' }
    $denies = @()
    foreach ($path in $p.studentDataPaths) {
        if ($path -isnot [string]) { Throw-EkInput '학생 폴더 경로는 문자열이어야 합니다.' }
        foreach ($safeFolder in @(Get-EkStudentPaths $path $TargetHome)) {
            $norm = $safeFolder.Replace('\','/').TrimEnd('/')
            $norm = '/' + $norm.Substring(0,1).ToLowerInvariant() + $norm.Substring(2)
            $anchor = '/' + $norm
            $denies += @("Read($anchor)", "Read($anchor/**)", "Edit($anchor)", "Edit($anchor/**)")
        }
    }
    Merge-EkRules $perm 'deny' $denies
    # 전체 셸 승인: 기존 allow가 있어도 위험 명령/간접 파일 읽기를 승인 없이 실행하지 않습니다.
    Merge-EkRules $perm 'ask' @('Bash','PowerShell','WebFetch','WebSearch','mcp__*')
    $perm.defaultMode = 'default'
    $perm.disableBypassPermissionsMode = 'disable'
    Save-EkSettings $s ($Apply -and -not $DryRun)
    Write-Output '학생 폴더 차단은 Claude 도구 규칙입니다. 임의 프로그램까지 막는 OS 격리는 아닙니다. 셸 승인 시 학생 폴더를 읽는 명령은 거절하세요.'
} catch { Write-Output (Get-EkSafeError $_ '설정 실패: 저장 위치·실행 권한을 판매자와 확인하세요. 원본 오류는 공유하지 마세요.'); exit 1 }
