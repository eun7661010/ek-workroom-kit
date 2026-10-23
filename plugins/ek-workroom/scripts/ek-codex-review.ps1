# -Target 반복 인자는 이름/값 쌍으로 읽습니다. 값은 코드로 평가하지 않습니다.
. "$PSScriptRoot/common.ps1"
$disabledFeatures = @('shell_tool','unified_exec','browser_use','browser_use_external','browser_use_full_cdp_access','in_app_browser','computer_use','apps','plugins','remote_plugin','multi_agent','view_image','code_mode_host','memories','hooks','workspace_dependencies','skill_mcp_dependency_install')
$codexConfig = @('mcp_servers={}','web_search="disabled"')
$tempDir = $null
$emptyWork = $null
try {
    $options = @{}; $targets = @()
    for ($index = 0; $index -lt $args.Count; $index += 2) {
        $name = [string]$args[$index]
        if ($name -notin @('-Workspace','-Brief','-Out','-Target') -or $index+1 -ge $args.Count) { Throw-EkInput '작업실·브리프·대상 파일·새 결과 옵션을 확인하세요.' }
        $value = $args[$index+1]
        if ($name -eq '-Target') {
            foreach ($item in @($value)) {
                if ($item -isnot [string] -or -not $item.Trim()) { Throw-EkInput '검토 대상 파일을 1개 이상 지정하세요.' }
                $targets += $item
            }
        } else {
            if ($options.ContainsKey($name) -or $value -isnot [string] -or -not $value.Trim()) { Throw-EkInput '검토 실행 옵션을 확인하세요.' }
            $options[$name] = $value
        }
    }
    if ($options.Count -ne 3 -or $targets.Count -lt 1) { Throw-EkInput '작업실·브리프·새 결과와 검토 대상 파일을 1개 이상 지정하세요.' }
    $Workspace = $options['-Workspace']; $Brief = $options['-Brief']; $Out = $options['-Out']
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
    $protectedFile = Join-Path $work '.ek-workroom/protected-paths.json'
    if (-not (Test-Path -LiteralPath $protectedFile -PathType Leaf)) { Write-Output '작업실 만들기(ek-mode)를 먼저 하세요'; exit 2 }
    if (-not (Test-EkWithin (Get-EkFinalPath $protectedFile) $workReal)) { Throw-EkInput '작업실 보호 경로 목록의 위치를 확인하세요.' }
    $protected = Read-EkObject $protectedFile
    if ($protected.schemaVersion -ne 1 -or $protected.paths -isnot [array] -or $protected.paths.Count -lt 1) { Throw-EkInput '작업실 보호 경로 목록을 확인하세요.' }
    $utf8 = New-Object Text.UTF8Encoding($false,$true)
    $normalize = { param([string]$Text) [regex]::Replace($Text.Normalize([Text.NormalizationForm]::FormKC),'[\p{Cf}\u034f\u180b-\u180d\ufe00-\ufe0f]','').Replace('\','/') }
    $protectedReal = @()
    foreach ($path in $protected.paths) {
        if ($path -isnot [string] -or $path -notmatch '^[A-Za-z]:[\\/]' -or -not $path.TrimEnd('\','/')) { Throw-EkInput '작업실 보호 경로 목록을 확인하세요.' }
        $normalizedPath = (& $normalize $path).TrimEnd('/')
        $folder = ($normalizedPath -split '/')[-1]
        if (-not $folder) { Throw-EkInput '작업실 보호 경로 목록을 확인하세요.' }
        $protectedReal += Get-EkProjectedPath $path
    }
    function Assert-EkReviewVisible([string]$Path) {
        $cursor = $Path
        while ($cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ([IO.Path]::GetFileName($cursor).StartsWith('.') -or ($item.Attributes -band [IO.FileAttributes]::Hidden)) { Throw-EkInput '숨김 파일이나 숨김 폴더 안의 파일은 검토할 수 없습니다.' }
            if ($cursor.Equals($work,[StringComparison]::OrdinalIgnoreCase) -or $cursor.Equals($workReal,[StringComparison]::OrdinalIgnoreCase)) { break }
            $parent = [IO.Path]::GetDirectoryName($cursor)
            if (-not $parent -or $parent -eq $cursor) { break }
            $cursor = $parent
        }
    }
    function Read-EkReviewInput([string]$Path, [string]$RequiredRoot) {
        $entered = [IO.Path]::GetFullPath($Path)
        if (-not (Test-Path -LiteralPath $entered -PathType Leaf)) { Throw-EkInput '검토 입력 파일을 확인하세요.' }
        $real = Get-EkFinalPath $entered
        if (-not (Test-EkWithin $real $RequiredRoot) -or -not (Test-EkWithin $real $workReal)) { Throw-EkInput '검토 입력은 지정한 작업실 폴더 안의 파일만 허용합니다.' }
        foreach ($private in $protectedReal) {
            if (Test-EkWithin $real $private) { Throw-EkInput '보호 대상 파일은 검토할 수 없습니다.' }
        }
        Assert-EkReviewVisible $real
        Assert-EkReviewVisible $entered
        if ([IO.Path]::GetExtension($real).ToLowerInvariant() -notin @('.md','.txt','.html','.htm','.csv')) { Throw-EkInput '검토 입력은 MD·TXT·HTML·HTM·CSV 파일만 허용합니다.' }
        $stream = [IO.File]::Open($real,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        try {
            $opened = Get-EkHandleInfo $stream
            if (-not $opened.Path.Equals($real,[StringComparison]::OrdinalIgnoreCase)) { Throw-EkInput '검토 대상의 실제 경로가 바뀌어 중단합니다.' }
            if ($opened.Links -ge 2) { Throw-EkInput '하드링크 파일은 검토할 수 없습니다.' }
            if ($opened.Attributes -band [uint32][IO.FileAttributes]::Hidden) { Throw-EkInput '숨김 파일은 검토할 수 없습니다.' }
            if ($stream.Length -gt 200KB) { Throw-EkInput '검토 입력은 파일당 200KB 이하로 지정하세요.' }
            $buffer = New-Object byte[] ([int]$stream.Length)
            $offset = 0
            while ($offset -lt $buffer.Length) {
                $read = $stream.Read($buffer,$offset,$buffer.Length-$offset)
                if ($read -eq 0) { Throw-EkInput '검토 입력 파일을 읽지 못했습니다.' }
                $offset += $read
            }
        } finally { $stream.Dispose() }
        try { $content = $utf8.GetString($buffer).TrimStart([char]0xfeff) }
        catch { Throw-EkInput '검토 입력 파일은 UTF-8로 저장해 주세요.' }
        return @{ Content=$content; Bytes=$buffer.Length; Path=$real }
    }
    $briefInput = Read-EkReviewInput $briefPath $reviewReal
    $normalizedBrief = & $normalize $briefInput.Content
    foreach ($path in $protected.paths) {
        $normalizedPath = (& $normalize $path).TrimEnd('/')
        $folder = ($normalizedPath -split '/')[-1]
        if ($normalizedBrief.IndexOf($normalizedPath,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or $normalizedBrief.IndexOf($folder,[StringComparison]::OrdinalIgnoreCase) -ge 0) { Throw-EkInput '브리프에 보호 대상 폴더가 포함되어 검토를 중단합니다.' }
    }
    $header = "아래 파일 내용만 근거로 검토한다. 도구는 없다. 결과는 답변 텍스트로만.`n`n"
    $prompt = $header + $briefInput.Content
    $totalBytes = 0
    foreach ($target in $targets) {
        $targetInput = Read-EkReviewInput $target $workReal
        $totalBytes += $targetInput.Bytes
        if ($totalBytes -gt 500KB) { Throw-EkInput '검토 대상은 합계 500KB 이하로 지정하세요.' }
        $relative = $targetInput.Path.Substring($workReal.TrimEnd('\','/').Length+1)
        $prompt += "`n`n=== 파일: " + $relative.Replace('\','/') + " ===`n" + $targetInput.Content
    }
    $codex = Get-Command codex -CommandType Application,ExternalScript -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $codex) { Write-Output 'Codex 설치·로그인 먼저 확인하세요.'; exit 2 }
    # CLI가 결과를 쓰는 동안 다른 실행이 최종 이름을 만들더라도 덮어쓰지 않습니다.
    $tempDir = Join-Path $review ('.ek-review-'+[guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($tempDir)
    $stageOut = Join-Path $tempDir 'result.md'
    $emptyWork = Join-Path ([IO.Path]::GetTempPath()) ('ek-codex-empty-'+[guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($emptyWork)
    $arguments = @('exec','--sandbox','read-only','--skip-git-repo-check','--ephemeral','--color','never','-C',$emptyWork)
    foreach ($feature in $disabledFeatures) { $arguments += @('--disable',$feature) }
    foreach ($config in $codexConfig) { $arguments += @('-c',$config) }
    $arguments += @('-o',$stageOut,'-')
    # 경로와 인자는 자식 환경의 JSON 데이터로만 전달합니다. 고정 소스에 외부 값을 넣지 않습니다.
    # 브리프는 파이프로, 인자는 변수 splatting으로 넘깁니다. npm의 codex.ps1 실행기는 배열 리터럴을 인자 하나로 받고
    # 파이프 입력만 stdin으로 전달해서, 그냥 호출하면 exec 없이 대화형으로 열려 실패합니다(2026-10-22 실측).
    $childEnv = @{ EK_CODEX_ARGS_JSON=(ConvertTo-Json -InputObject $arguments -Compress); EK_CODEX_EXE=$codex.Source }
    Write-Output '검토 중·최대 10분·중복 실행하지 마세요.'
    $result = Start-EkProcess (Join-Path $PSHOME 'powershell.exe') @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'codex-child.ps1')) $prompt (Get-EkCodexReviewTimeout) $childEnv 'Codex 검토가 10분 안에 끝나지 않아 멈췄습니다. 새 터미널에서 codex --version과 로그인을 확인하세요.'
    if ($result.Code -ne 0) { Write-Output 'Codex 검토 실패: 설치·로그인·검토 요청과 보안 프로그램 차단 기록을 확인하세요.'; exit $result.Code }
    if (-not (Test-Path -LiteralPath $stageOut -PathType Leaf)) { Throw-EkInput 'Codex 결과 파일이 없습니다. 검토를 완료하지 못했습니다.' }
    if (-not (Test-EkWithin (Get-EkProjectedPath $outPath) $reviewReal)) { Throw-EkInput '검토 결과의 실제 저장 경로가 바뀌어 중단합니다.' }
    Assert-EkNewOutput $outPath
    $source = [IO.File]::OpenRead($stageOut)
    try {
        $dest = [IO.File]::Open($outPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $source.CopyTo($dest) } finally { $dest.Dispose() }
    } finally { $source.Dispose() }
    Write-Output ('검토 결과: '+$outPath)
} catch { Write-Output (Get-EkSafeError $_ 'Codex 검토 실패: 경로·실행 권한과 보안 프로그램 차단 기록을 확인하세요.'); exit 1 }
finally {
    if ($emptyWork -and [IO.Path]::GetFullPath($emptyWork).StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($emptyWork) -match '^ek-codex-empty-[a-f0-9]{32}$') { Remove-Item -LiteralPath $emptyWork -Recurse -Force -ErrorAction SilentlyContinue }
    if ($tempDir -and [IO.Path]::GetDirectoryName($tempDir) -eq $review -and [IO.Path]::GetFileName($tempDir) -match '^\.ek-review-[a-f0-9]{32}$') { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
}
