# Seller-only guidebook renderer. Does not invoke or modify customer kit tools.
[CmdletBinding()]
param(
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$browser = $null
try {
    if (-not $OutputPath) { $OutputPath = Join-Path $PSScriptRoot 'ek-workroom-guidebook-0.2.1.pdf' }
    $output = [IO.Path]::GetFullPath($OutputPath)
    if (Test-Path -LiteralPath $output) { throw 'Output already exists; choose a new PDF name.' }
    if ([IO.Path]::GetExtension($output) -ne '.pdf') { throw 'Output must be a .pdf file.' }
    if (-not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($output)) -PathType Container)) { throw 'Output folder does not exist.' }
    $html = Join-Path $PSScriptRoot 'guidebook.html'
    if (-not (Test-Path -LiteralPath $html -PathType Leaf)) { throw 'guidebook.html is missing.' }
    $candidates = foreach ($base in @(${env:ProgramFiles(x86)},$env:ProgramFiles,$env:LOCALAPPDATA)) {
        if ($base) { Join-Path $base 'Microsoft/Edge/Application/msedge.exe' }
    }
    $edge = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $edge) { throw 'Microsoft Edge was not found.' }

    # Keep all temporary files in the repo, including when called with a fake home.
    # No deletion: inspect/clean these using the seller's own retention procedure.
    $repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $run = Join-Path $repo ('.tmp/guidebook-' + [guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($run)
    $rendered = Join-Path $run 'rendered.pdf'
    $arguments = @(
        '--headless','--no-first-run','--no-default-browser-check',
        '--no-pdf-header-footer','--disable-background-networking','--disable-extensions',
        '--proxy-server=127.0.0.1:9','--host-resolver-rules=MAP * ~NOTFOUND',
        ('--user-data-dir=' + (Join-Path $run 'edge-profile')),
        ('--print-to-pdf=' + $rendered), ([Uri]$html).AbsoluteUri
    )
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $edge
    $info.Arguments = ($arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $browser = New-Object Diagnostics.Process
    $browser.StartInfo = $info
    $null = $browser.Start()
    $stdout = $browser.StandardOutput.ReadToEndAsync()
    $stderr = $browser.StandardError.ReadToEndAsync()
    if (-not $browser.WaitForExit(60000)) { $browser.Kill(); throw 'Edge render timed out.' }
    [IO.File]::WriteAllText((Join-Path $run 'edge.stdout.log'),$stdout.GetAwaiter().GetResult())
    [IO.File]::WriteAllText((Join-Path $run 'edge.stderr.log'),$stderr.GetAwaiter().GetResult())
    if ($browser.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $rendered -PathType Leaf)) { throw 'Edge PDF render failed; inspect .tmp/guidebook-* logs.' }
    $bytes = [IO.File]::ReadAllBytes($rendered)
    $raw = [Text.Encoding]::GetEncoding(28591).GetString($bytes)
    $pages = [regex]::Matches($raw,'/Type\s*/Page\b').Count
    if (-not $raw.StartsWith('%PDF-') -or $pages -lt 1) { throw 'Rendered file is not a PDF with pages.' }
    # Atomic no-overwrite check also covers a file created during rendering.
    $stream = [IO.File]::Open($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    Write-Output ('PDF pages: ' + $pages)
    Write-Output ('PDF: ' + $output)
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($browser) { $browser.Dispose() }
}
