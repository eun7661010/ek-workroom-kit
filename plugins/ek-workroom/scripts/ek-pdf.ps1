[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Html, [Parameter(Mandatory=$true)][string]$Pdf)
. "$PSScriptRoot/common.ps1"
$tempDir = $null
try {
    $inputPath = [IO.Path]::GetFullPath($Html); $outputPath = [IO.Path]::GetFullPath($Pdf)
    Assert-EkNewOutput $outputPath
    if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf) -or [IO.Path]::GetExtension($inputPath) -notin @('.html','.htm') -or [IO.Path]::GetExtension($outputPath) -ne '.pdf') { Throw-EkInput 'HTML 입력과 새 PDF 파일 이름을 확인하세요.' }
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
    $url = (New-Object Uri $inputPath).AbsoluteUri
    $result = Start-EkProcess $browser @('--headless','--disable-gpu','--no-first-run','--no-pdf-header-footer',('--user-data-dir='+$tempDir),('--print-to-pdf='+$rendered),$url)
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
    if ($tempDir -and [IO.Path]::GetFullPath($tempDir).StartsWith([IO.Path]::GetTempPath(),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($tempDir) -match '^ek-pdf-[a-f0-9]{32}$') { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
}
