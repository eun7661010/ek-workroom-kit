[CmdletBinding()]
param([string]$TargetHome = $env:USERPROFILE, [switch]$Apply, [switch]$DryRun)
. "$PSScriptRoot/common.ps1"
try {
    $s = Get-EkSettings $TargetHome
    $source = Join-Path $PSScriptRoot 'statusline.ps1'
    $dest = Join-Path $TargetHome '.claude/ek-workroom/statusline.ps1'
    Assert-EkSafePath $dest $TargetHome
    $commandPath = $dest.Replace('\','/')
    # 양쪽 셸에서 해석되는 명령 경로에 확장 문자가 섞이면 실행하지 않습니다.
    if ($commandPath -match '["$`\r\n]') { Throw-EkInput '홈 경로의 특수문자를 확인하세요.' }
    $line = [ordered]@{}
    if ($s.Value.Contains('statusLine')) {
        if ($s.Value.statusLine -isnot [System.Collections.IDictionary]) { Throw-EkInput 'statusLine 객체를 확인하세요.' }
        $line = $s.Value.statusLine
    }
    $line.type = 'command'
    $line.command = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' + $commandPath + '"'
    $s.Value.statusLine = $line
    if ($Apply -and -not $DryRun) {
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest)
        if (-not (Test-Path -LiteralPath $dest) -or (Get-FileHash $source).Hash -ne (Get-FileHash $dest).Hash) {
            if (Test-Path -LiteralPath $dest) { [IO.File]::Copy($dest, ($dest + '.ek-backup-' + (Get-Date -Format 'yyyyMMddTHHmmssfffffff')), $false) }
            [IO.File]::Copy($source, $dest, $true)
        }
    } else { Write-Output '미리보기: 상태줄 스크립트 1개를 고객 홈의 .claude/ek-workroom에 복사합니다.' }
    Save-EkSettings $s ($Apply -and -not $DryRun)
} catch { Write-Output (Get-EkSafeError $_ '상태줄 설정 실패: 저장 위치·실행 권한을 판매자와 확인하세요. 원본 오류는 공유하지 마세요.'); exit 1 }
