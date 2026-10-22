[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Html, [Parameter(Mandatory=$true)][string]$Pdf)
. "$PSScriptRoot/common.ps1"
$tempDir = $null
$server = $null
try {
    $inputPath = [IO.Path]::GetFullPath($Html); $outputPath = [IO.Path]::GetFullPath($Pdf)
    Assert-EkNewOutput $outputPath
    if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf) -or [IO.Path]::GetExtension($inputPath) -notin @('.html','.htm') -or [IO.Path]::GetExtension($outputPath) -ne '.pdf') { Throw-EkInput 'HTML 입력과 새 PDF 파일 이름을 확인하세요.' }
    $htmlFolder = [IO.Path]::GetDirectoryName($inputPath)
    $workspace = $htmlFolder
    while ($workspace -and -not (Test-Path -LiteralPath (Join-Path $workspace '.ek-workroom/protected-paths.json') -PathType Leaf)) {
        $workspace = [IO.Path]::GetDirectoryName($workspace)
    }
    if (-not $workspace) { Write-Output '작업실 안 HTML만 PDF로 만들 수 있습니다'; exit 2 }
    $workReal = Get-EkFinalPath $workspace
    $rootReal = Get-EkFinalPath $htmlFolder
    $htmlReal = Get-EkFinalPath $inputPath
    $metadata = Join-Path $workspace '.ek-workroom/protected-paths.json'
    if (-not (Test-EkWithin $htmlReal $workReal) -or -not (Test-EkWithin $rootReal $workReal) -or -not (Test-EkWithin $htmlReal $rootReal) -or -not (Test-EkWithin (Get-EkFinalPath $metadata) $workReal)) { Throw-EkInput 'PDF 입력의 실제 경로가 작업실 범위를 벗어났습니다.' }
    $protection = Read-EkObject $metadata
    if ($protection.schemaVersion -ne 1 -or $protection.paths -isnot [array] -or $protection.paths.Count -lt 1) { Throw-EkInput '작업실 보호 경로 목록을 확인하세요.' }
    foreach ($private in $protection.paths) {
        if ($private -isnot [string] -or $private -notmatch '^[A-Za-z]:[\\/]') { Throw-EkInput '작업실 보호 경로 목록을 확인하세요.' }
        $privateReal = Get-EkProjectedPath $private
        if ((Test-EkWithin $htmlReal $privateReal) -or (Test-EkWithin $rootReal $privateReal) -or (Test-EkWithin $privateReal $rootReal)) { Throw-EkInput '학생정보 보호 폴더와 겹치는 위치에서는 PDF를 만들 수 없습니다.' }
    }
    $inputStream = [IO.File]::Open($htmlReal,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try { if ((Get-EkHandleInfo $inputStream).Links -ge 2) { Throw-EkInput '하드링크 파일은 PDF 입력으로 사용할 수 없습니다.' } }
    finally { $inputStream.Dispose() }
    $candidates = @()
    if ($null -ne $env:EK_PDF_BROWSER) { $candidates = @($env:EK_PDF_BROWSER) }
    else {
        foreach ($base in @(${env:ProgramFiles(x86)},$env:ProgramFiles,$env:LOCALAPPDATA)) { if ($base) { $candidates += Join-Path $base 'Microsoft/Edge/Application/msedge.exe' } }
        foreach ($base in @($env:ProgramFiles,${env:ProgramFiles(x86)},$env:LOCALAPPDATA)) { if ($base) { $candidates += Join-Path $base 'Google/Chrome/Application/chrome.exe' } }
    }
    $browser = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (-not $browser) { Write-Output '브라우저가 없습니다. 브라우저에서 열어 인쇄→PDF로 저장하세요.'; exit 2 }
    $tempDir = Join-Path ([IO.Path]::GetTempPath()) ('ek-pdf-'+[guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($tempDir)
    $rendered = Join-Path $tempDir 'output.pdf'
    $state = Join-Path $tempDir 'server'
    $null = [IO.Directory]::CreateDirectory($state)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = Join-Path $PSHOME 'powershell.exe'
    $info.Arguments = (@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'pdf-server.ps1')) | ForEach-Object { ConvertTo-EkArgument $_ }) -join ' '
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $token = [guid]::NewGuid().ToString('N')
    $info.EnvironmentVariables['EK_PDF_ROOT'] = $rootReal
    $info.EnvironmentVariables['EK_PDF_STATE_DIR'] = $state
    $info.EnvironmentVariables['EK_PDF_TOKEN'] = $token
    $server = New-Object Diagnostics.Process
    $server.StartInfo = $info
    $null = $server.Start()
    $serverOut = $server.StandardOutput.ReadToEndAsync(); $serverError = $server.StandardError.ReadToEndAsync()
    $ready = Join-Path $state 'port.txt'
    $started = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $ready)) {
        if ($server.HasExited -or $started.Elapsed.TotalSeconds -gt 15) { Throw-EkInput 'PDF 임시 서버를 시작하지 못했습니다. 다시 실행하세요.' }
        Start-Sleep -Milliseconds 30
    }
    $port = [int][IO.File]::ReadAllText($ready)
    $url = 'http://127.0.0.1:'+ $port + '/' + $token + '/' + [Uri]::EscapeDataString([IO.Path]::GetFileName($inputPath))
    $result = Start-EkProcess $browser @('--headless','--disable-gpu','--no-first-run','--no-pdf-header-footer','--proxy-server=127.0.0.1:9',('--proxy-bypass-list=<-loopback>;127.0.0.1:'+$port),'--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1','--disable-background-networking','--disable-extensions',('--user-data-dir='+$tempDir),('--print-to-pdf='+$rendered),$url)
    if ($result.Code -ne 0 -or -not (Test-Path -LiteralPath $rendered -PathType Leaf)) { Throw-EkInput 'PDF를 만들지 못했습니다. HTML을 브라우저에서 열어 확인하세요.' }
    $bytes = [IO.File]::ReadAllBytes($rendered)
    $raw = [Text.Encoding]::GetEncoding(28591).GetString($bytes)
    $pages = [regex]::Matches($raw,'/Type\s*/Page\b').Count
    if (-not $raw.StartsWith('%PDF-') -or $pages -lt 1) { Throw-EkInput 'PDF 페이지를 확인하지 못했습니다. 브라우저에서 인쇄해 확인하세요.' }
    $stream = [IO.File]::Open($outputPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    Write-Output ('PDF '+$pages+'쪽: '+[IO.Path]::GetFileName($outputPath))
} catch { Write-Output (Get-EkSafeError $_ 'PDF 생성 실패: 입력 파일과 저장 위치를 확인하세요.'); exit 1 }
finally {
    if ($server) { if (-not $server.HasExited) { $server.Kill(); $server.WaitForExit() }; $server.Dispose() }
    if ($tempDir -and $env:EK_PDF_AUDIT_LOG -and (Test-Path -LiteralPath (Join-Path $tempDir 'server/access.jsonl'))) {
        try { [IO.File]::Copy((Join-Path $tempDir 'server/access.jsonl'),$env:EK_PDF_AUDIT_LOG,$false) } catch { }
    }
    if ($tempDir -and [IO.Path]::GetFullPath($tempDir).StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($tempDir) -match '^ek-pdf-[a-f0-9]{32}$') { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
}
