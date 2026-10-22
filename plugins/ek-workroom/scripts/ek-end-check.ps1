[CmdletBinding()]
param([string]$TargetHome = $env:USERPROFILE, [switch]$Apply, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$found = $false; $unknown = $false
Write-Output '종료 점검 (읽기 전용). 프로그램을 끄거나 서비스를 변경하지 않습니다.'
try {
    $service = Get-Service -Name sshd -ErrorAction SilentlyContinue
    if ($service) { Write-Output 'OpenSSH 서버: 설치되어 있음. 원장님이 상태를 확인하세요.'; $found = $true }
    else { Write-Output 'OpenSSH 서버: 서비스 없음' }
} catch { Write-Output 'OpenSSH 서버: 확인 불가'; $unknown = $true }
try {
    $tailscale = Get-Command tailscale -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tailscale) {
        $raw = & $tailscale.Source status --json 2>$null | Out-String
        if ($LASTEXITCODE -ne 0) { throw '상태 확인 실패' }
        $state = ($raw | ConvertFrom-Json).BackendState
        if ($state -eq 'Running') { Write-Output 'Tailscale: 연결 켜짐'; $found = $true }
        elseif ($state -in @('Stopped','NeedsLogin','NoState')) { Write-Output 'Tailscale: 연결 꺼짐' }
        else { throw '미확인 상태' }
    } else { Write-Output 'Tailscale: 명령 없음 (서비스는 별도 확인)' }
    $tsService = Get-Service -Name Tailscale -ErrorAction SilentlyContinue
    if ($tsService -and $tsService.Status -eq 'Running' -and -not $tailscale) { $found = $true; Write-Output 'Tailscale 서비스: 켜짐' }
} catch { Write-Output 'Tailscale: 확인 불가'; $unknown = $true }
try {
    $processNames = @(Get-Process -ErrorAction Stop | Select-Object -ExpandProperty ProcessName)
    foreach ($tool in @('AnyDesk','TeamViewer','RustDesk','remoting_host')) {
        $on = @($processNames | Where-Object { $_ -like ($tool + '*') }).Count -gt 0
        Write-Output ($tool + ': ' + $(if ($on) { '실행 중'; $found = $true } else { '실행 흔적 없음' }))
    }
} catch { Write-Output '원격 호스트 프로세스: 확인 불가'; $unknown = $true }
try {
    $tasks = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskName -like 'EK-Workroom-*' })
    Write-Output ('이번 세션 예약 작업(EK-Workroom-*): ' + $tasks.Count + '개 / 이 키트는 예약 작업을 만들지 않습니다.')
    if ($tasks.Count) { $found = $true }
} catch { Write-Output '이번 세션 예약 작업: 확인 불가'; $unknown = $true }
if ($found) { Write-Output '남은 원격 접속 있음: 접속 가능한 구성요소가 발견되었습니다. 기존 사용 목적을 확인하고 원장님이 종료하세요.' }
elseif ($unknown) { Write-Output '남은 원격 접속 여부 확인 불가: 원장님 화면에서 추가 확인이 필요합니다.' }
else { Write-Output '남은 원격 접속 없음 (점검한 구성요소 기준)' }
Write-Output 'Zoom 공유 중지·원격 제어 해제·브라우저 지원 세션 종료는 원장님이 화면에서 직접 확인하세요. 이 검사만으로 접속 부재가 보장되지는 않습니다.'
