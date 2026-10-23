# 고정 자식 실행기. 실행 경로·인자는 환경변수 JSON, 브리프는 stdin 데이터로만 받습니다.
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding $false
[Console]::InputEncoding = $OutputEncoding
[Console]::OutputEncoding = $OutputEncoding
$ekArgs = ConvertFrom-Json -InputObject $env:EK_CODEX_ARGS_JSON
$ekExe = $env:EK_CODEX_EXE
[Console]::In.ReadToEnd() | & $ekExe @ekArgs
exit $LASTEXITCODE
