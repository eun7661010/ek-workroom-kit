param([string]$TargetHome = $env:USERPROFILE, [ValidateSet('work','personal')][string]$AccountLabel = 'work')
try {
    $session = ($input | Out-String) | ConvertFrom-Json
    $model = [string]$session.model.display_name
    $folder = Split-Path ([string]$session.workspace.current_dir) -Leaf
    if (-not $folder) { $folder = Split-Path ([string]$session.cwd) -Leaf }
    $model = $model -replace '[\x00-\x1f\x7f]',''
    $folder = $folder -replace '[\x00-\x1f\x7f]',''
    $account = if ($AccountLabel -eq 'work') { '업무용' } else { '개인용' }
    Write-Output ("모델 {0} | 폴더 {1} | 계정 별칭 {2} (/status 확인)" -f $model,$folder,$account)
} catch { Write-Output '상태줄: /status에서 모델과 계정을 확인하세요.' }
