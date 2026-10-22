[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace, [Parameter(Mandatory=$true)][string]$Brief, [Parameter(Mandatory=$true)][string]$Out)
. "$PSScriptRoot/common.ps1"
$tempDir = $null
try {
    $work = [IO.Path]::GetFullPath($Workspace)
    if (-not (Test-Path -LiteralPath $work -PathType Container)) { Throw-EkInput '작업실 폴더를 확인하세요.' }
    $review = Join-Path $work '검토'
    if (-not (Test-Path -LiteralPath $review -PathType Container)) { Throw-EkInput '작업실의 검토 폴더가 필요합니다.' }
    $workReal = Get-EkFinalPath $work; $reviewReal = Get-EkFinalPath $review
    if (-not (Test-EkWithin $reviewReal $workReal) -or $reviewReal -eq $workReal) { Throw-EkInput '검토 폴더가 작업실 밖으로 연결되어 있습니다.' }
    $briefPath = [IO.Path]::GetFullPath($Brief); $outPath = [IO.Path]::GetFullPath($Out)
    Assert-EkNewOutput $outPath
    if (-not (Test-Path -LiteralPath $briefPath -PathType Leaf)) { Throw-EkInput '검토 브리프 파일을 확인하세요.' }
    foreach ($path in @($briefPath,$outPath)) {
        if (-not (Test-EkWithin $path $review) -or -not (Test-EkWithin (Get-EkProjectedPath $path) $reviewReal)) { Throw-EkInput '브리프와 결과는 작업실의 검토 폴더 안에 지정하세요.' }
    }
    $codex = Get-Command codex -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $codex) { Write-Output 'Codex 설치·로그인 먼저 확인하세요.'; exit 2 }
    $utf8 = New-Object Text.UTF8Encoding($false,$true)
    $prompt = [IO.File]::ReadAllText($briefPath,$utf8)
    # CLI가 결과를 쓰는 동안 다른 실행이 최종 이름을 만들더라도 덮어쓰지 않습니다.
    $tempDir = Join-Path $review ('.ek-review-'+[guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($tempDir)
    $stageOut = Join-Path $tempDir 'result.md'
    $arguments = @('exec','--sandbox','read-only','--skip-git-repo-check','--ephemeral','--color','never','-C',$work,'-o',$stageOut,'-')
    # .cmd/.ps1도 셸 문자열 보간 없이 PowerShell 배열로 호출합니다.
    $quoted = @($arguments | ForEach-Object { "'"+$_.Replace("'","''")+"'" }) -join ','
    # 브리프는 파이프로, 인자는 변수 splatting으로 넘깁니다. npm의 codex.ps1 실행기는 배열 리터럴을 인자 하나로 받고
    # 파이프 입력만 stdin으로 전달해서, 그냥 호출하면 exec 없이 대화형으로 열려 실패합니다(2026-10-22 실측).
    $child = '$OutputEncoding=New-Object Text.UTF8Encoding $false; [Console]::InputEncoding=$OutputEncoding; [Console]::OutputEncoding=$OutputEncoding; $ekArgs=@('+$quoted+'); [Console]::In.ReadToEnd() | & ' + "'"+$codex.Source.Replace("'","''")+"'" + ' @ekArgs; exit $LASTEXITCODE'
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
    $result = Start-EkProcess (Join-Path $PSHOME 'powershell.exe') @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',$encoded) $prompt 0
    if ($result.Code -ne 0) { Write-Output 'Codex 검토 실패: 설치·로그인과 검토 요청을 확인하세요.'; exit $result.Code }
    if (-not (Test-Path -LiteralPath $stageOut -PathType Leaf)) { Throw-EkInput 'Codex 결과 파일이 없습니다. 검토를 완료하지 못했습니다.' }
    if (-not (Test-EkWithin (Get-EkProjectedPath $outPath) $reviewReal)) { Throw-EkInput '검토 결과의 실제 저장 경로가 바뀌어 중단합니다.' }
    Assert-EkNewOutput $outPath
    $source = [IO.File]::OpenRead($stageOut)
    try {
        $dest = [IO.File]::Open($outPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $source.CopyTo($dest) } finally { $dest.Dispose() }
    } finally { $source.Dispose() }
    Write-Output ('검토 결과: '+$outPath)
} catch { Write-Output (Get-EkSafeError $_ 'Codex 검토 실패: 경로와 실행 권한을 확인하세요.'); exit 1 }
finally {
    if ($tempDir -and [IO.Path]::GetDirectoryName($tempDir) -eq $review -and [IO.Path]::GetFileName($tempDir) -match '^\.ek-review-[a-f0-9]{32}$') { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
}
