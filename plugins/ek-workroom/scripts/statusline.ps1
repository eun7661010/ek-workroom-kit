param([string]$TargetHome = $env:USERPROFILE, [ValidateSet('work','personal')][string]$AccountLabel = 'work')
$utf8 = New-Object Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
try {
    # OS 기본 코드 페이지와 무관하게 Claude가 보내는 UTF-8 바이트를 읽습니다.
    $reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), $utf8)
    $session = $reader.ReadToEnd() | ConvertFrom-Json
    $model = [string]$session.model.display_name
    $folder = Split-Path ([string]$session.workspace.current_dir) -Leaf
    if (-not $folder) { $folder = Split-Path ([string]$session.cwd) -Leaf }
    $model = $model -replace '[\x00-\x1f\x7f]',''
    $folder = $folder -replace '[\x00-\x1f\x7f]',''
    $account = if ($AccountLabel -eq 'work') { '업무용' } else { '개인용' }
    Write-Output ("모델 {0} | 폴더 {1} | 설정한 별칭: {2} (수동 고정값, 실제 계정은 /status 확인)" -f $model,$folder,$account)
} catch { Write-Output '상태줄: /status에서 모델과 계정을 확인하세요.' }
