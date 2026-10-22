[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Hwpx, [Parameter(Mandatory=$true)][string]$Out)
. "$PSScriptRoot/common.ps1"
$inputStream = $null; $zip = $null
try {
    $source = [IO.Path]::GetFullPath($Hwpx); $dest = [IO.Path]::GetFullPath($Out)
    Assert-EkNewOutput $dest
    $inputStream = [IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $header = New-Object byte[] 4; $count = $inputStream.Read($header,0,4); $inputStream.Position = 0
    if ([IO.Path]::GetExtension($source) -eq '.hwp' -or ($count -eq 4 -and [BitConverter]::ToString($header) -eq 'D0-CF-11-E0')) { Write-Output '한컴오피스에서 HWPX나 PDF로 다른 이름 저장 후 다시 실행하세요.'; exit 2 }
    if ([IO.Path]::GetExtension($source) -ne '.hwpx') { Throw-EkInput 'HWPX 파일을 지정하세요.' }
    Add-Type -AssemblyName System.IO.Compression
    $zip = New-Object IO.Compression.ZipArchive($inputStream,[IO.Compression.ZipArchiveMode]::Read,$true)
    [long]$size = 0
    foreach ($entry in $zip.Entries) { $size += $entry.Length; if ($size -gt 50MB) { Throw-EkInput '압축 내부 크기 합이 50MB를 넘어 읽지 않습니다.' } }
    $sections = @($zip.Entries | Where-Object { $_.FullName -match '^Contents/section[0-9]+\.xml$' } | Sort-Object { [long]([regex]::Match($_.FullName,'section([0-9]+)').Groups[1].Value) })
    if (-not $sections.Count) { Throw-EkInput 'HWPX 본문을 찾지 못했습니다.' }
    $lines = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entry in $sections) {
        $settings = New-Object Xml.XmlReaderSettings
        $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit; $settings.XmlResolver = $null; $settings.MaxCharactersInDocument = 50MB
        $sectionStream = $entry.Open(); $reader = $null
        try {
            $reader = [Xml.XmlReader]::Create($sectionStream,$settings)
            $document = New-Object Xml.XmlDocument; $document.XmlResolver = $null; $document.Load($reader)
            $ns = New-Object Xml.XmlNamespaceManager($document.NameTable)
            $ns.AddNamespace('hp','http://www.hancom.co.kr/hwpml/2011/paragraph')
            foreach ($paragraph in $document.SelectNodes('//hp:p',$ns)) {
                $texts = @($paragraph.SelectNodes('.//hp:t',$ns) | Where-Object { $_.SelectSingleNode('ancestor::hp:p[1]',$ns) -eq $paragraph } | ForEach-Object { $_.InnerText })
                $lines.Add(($texts -join ''))
            }
        } finally { if ($reader) { $reader.Dispose() }; $sectionStream.Dispose() }
    }
    $bytes = (New-Object Text.UTF8Encoding $false).GetBytes(($lines -join "`n")+"`n")
    $stream = [IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    Write-Output ('텍스트 저장: '+[IO.Path]::GetFileName($dest))
} catch { Write-Output (Get-EkSafeError $_ 'HWPX 읽기 실패: 파일 형식과 저장 위치를 확인하세요.'); exit 1 }
finally { if ($zip) { $zip.Dispose() }; if ($inputStream) { $inputStream.Dispose() } }
