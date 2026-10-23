# 전용 자식 프로세스: 루트와 상태 경로는 환경변수로만 전달합니다.
. "$PSScriptRoot/common.ps1"
$listener = $null
try {
    $root = (Get-EkFinalPath $env:EK_PDF_ROOT).TrimEnd('\','/')
    $state = $env:EK_PDF_STATE_DIR
    $token = $env:EK_PDF_TOKEN
    if (-not (Test-Path -LiteralPath $state -PathType Container) -or $token -cnotmatch '^[a-f0-9]{32}$') { exit 1 }
    $utf8 = New-Object Text.UTF8Encoding $false
    $mime = @{ '.html'='text/html; charset=utf-8'; '.htm'='text/html; charset=utf-8'; '.css'='text/css; charset=utf-8'; '.png'='image/png'; '.jpg'='image/jpeg'; '.jpeg'='image/jpeg'; '.gif'='image/gif'; '.webp'='image/webp'; '.svg'='image/svg+xml'; '.woff'='font/woff'; '.woff2'='font/woff2'; '.ttf'='font/ttf'; '.otf'='font/otf' }
    $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)
    $listener.Start()
    [IO.File]::WriteAllText((Join-Path $state 'port.tmp'),[string]$listener.LocalEndpoint.Port,$utf8)
    [IO.File]::Move((Join-Path $state 'port.tmp'),(Join-Path $state 'port.txt'))
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (-not $listener.Pending()) { Start-Sleep -Milliseconds 15; continue }
        $client = $listener.AcceptTcpClient()
        try {
            $client.ReceiveTimeout = 2000; $client.SendTimeout = 2000
            $net = $client.GetStream()
            $header = New-Object Text.StringBuilder
            while ($header.Length -lt 32768) {
                $b = $net.ReadByte()
                if ($b -lt 0) { break }
                $null = $header.Append([char]$b)
                if ($header.ToString().EndsWith("`r`n`r`n")) { break }
            }
            $status = '404 Not Found'; $body = [byte[]]@(); $contentType = 'text/plain'; $outside = $false; $served = $null
            try {
                $first = ($header.ToString() -split "`r`n")[0]
                if ($first -notmatch '^GET (/[^ ]*) HTTP/1\.[01]$') { throw 'request' }
                $requestPath = ($Matches[1] -split '\?',2)[0]
                $decoded = [Uri]::UnescapeDataString($requestPath)
                if (-not $decoded.StartsWith('/') -or $decoded.StartsWith('//') -or $decoded.Contains('\') -or $decoded.Contains([char]0)) { $outside = $true; throw 'path' }
                if ($decoded.Contains(':')) { throw 'path' }
                $prefix = '/'+$token+'/'
                if (-not $decoded.StartsWith($prefix,[StringComparison]::Ordinal)) { throw 'token' }
                $relative = $decoded.Substring($prefix.Length)
                if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or $relative.Contains(':')) { $outside = $true; throw 'path' }
                $segments = $relative -split '/'
                if ($segments -contains '..') { $outside = $true; throw 'path' }
                if (@($segments | Where-Object { -not $_ -or $_.StartsWith('.') -or $_.TrimEnd(' ','.') -ne $_ }).Count) { throw 'path' }
                $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
                if (-not (Test-EkWithin $path $root) -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'path' }
                $real = Get-EkFinalPath $path
                if (-not (Test-EkWithin $real $root) -or $real -eq $root) { $outside = $true; throw 'path' }
                $realRelative = $real.Substring($root.Length+1)
                if ([IO.Path]::GetFileName($root).StartsWith('.') -or (([IO.File]::GetAttributes($root) -band [IO.FileAttributes]::Hidden) -ne 0)) { throw 'hidden' }
                $cursor = $root
                foreach ($part in ($realRelative -split '[\\/]')) {
                    if ($part.StartsWith('.')) { throw 'hidden' }
                    $cursor = Join-Path $cursor $part
                    if (([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::Hidden) -ne 0) { throw 'hidden' }
                }
                # 입력 별칭과 중간 junction 자체의 숨김 속성도 검사합니다.
                $cursor = $root
                foreach ($part in $segments) {
                    $cursor = Join-Path $cursor $part
                    if (([IO.File]::GetAttributes($cursor) -band [IO.FileAttributes]::Hidden) -ne 0) { throw 'hidden' }
                }
                $ext = [IO.Path]::GetExtension($real).ToLowerInvariant()
                if (-not $mime.ContainsKey($ext) -or -not $mime.ContainsKey([IO.Path]::GetExtension($path).ToLowerInvariant())) { throw 'extension' }
                $file = [IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
                try {
                    # 같은 열린 핸들의 최종 경로를 재확인한 뒤 읽어 링크 교체 경합도 막습니다.
                    $opened = Get-EkHandleInfo $file
                    if (-not $opened.Path.Equals($real,[StringComparison]::OrdinalIgnoreCase)) { throw 'path' }
                    if ($opened.Links -ge 2 -or ($opened.Attributes -band [uint32][IO.FileAttributes]::Hidden)) { throw 'hidden-or-hardlink' }
                    $memory = New-Object IO.MemoryStream
                    try { $file.CopyTo($memory); $body = $memory.ToArray() } finally { $memory.Dispose() }
                } finally { $file.Dispose() }
                $status = '200 OK'; $contentType = $mime[$ext]; $served = $realRelative.Replace('\','/')
            } catch { }
            $response = [Text.Encoding]::ASCII.GetBytes("HTTP/1.1 $status`r`nContent-Type: $contentType`r`nContent-Length: $($body.Length)`r`nConnection: close`r`nX-Content-Type-Options: nosniff`r`nContent-Security-Policy: default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline' data:; font-src 'self' data:; script-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`r`n`r`n")
            $net.Write($response,0,$response.Length)
            if ($body.Length) { $net.Write($body,0,$body.Length) }
            $net.Flush()
            [IO.File]::AppendAllText((Join-Path $state 'access.jsonl'),((@{ status=[int]$status.Substring(0,3); path=$served; outside=$outside } | ConvertTo-Json -Compress)+"`n"),$utf8)
        } catch { } finally { $client.Close() }
    }
} catch { exit 1 }
finally { if ($listener) { $listener.Stop() } }
