$utf8 = New-Object Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
try {
    $reader = New-Object IO.StreamReader([Console]::OpenStandardInput(),$utf8)
    $session = $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop
    $parts = New-Object 'System.Collections.Generic.List[string]'
    $model = ([string]$session.model.display_name) -replace '[\x00-\x1f\x7f]',''
    $folder = (([string]$session.workspace.current_dir).TrimEnd('/','\') -split '[\\/]')[-1] -replace '[\x00-\x1f\x7f]',''
    if ($model) { $parts.Add($model) }
    if ($folder) { $parts.Add($folder) }
    foreach ($field in @(@('대화',$session.context_window.used_percentage),@('5시간',$session.rate_limits.five_hour.used_percentage))) {
        $number = 0.0
        if ($null -ne $field[1] -and [double]::TryParse([string]$field[1],[ref]$number) -and $number -ge 0 -and $number -le 100) { $parts.Add($field[0]+' '+$field[1]+'%') }
    }
    if ($parts.Count) { Write-Output ($parts -join ' · ') } else { Write-Output 'AI 작업실' }
} catch { Write-Output 'AI 작업실' }
exit 0
