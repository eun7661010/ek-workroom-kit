# Windows PowerShell 5.1 이상. 설정 파일만 읽고 쓰며 학생 폴더는 열지 않습니다.
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding $false
[Console]::InputEncoding = $OutputEncoding
[Console]::OutputEncoding = $OutputEncoding
function ConvertTo-EkMap($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $map = [ordered]@{}
        foreach ($p in $Value.PSObject.Properties) { $map[$p.Name] = ConvertTo-EkMap $p.Value }
        return $map
    }
    if ($Value -is [array]) { return ,@($Value | ForEach-Object { ConvertTo-EkMap $_ }) }
    return $Value
}
function Read-EkObject([string]$Path) {
    try {
        $utf8 = New-Object Text.UTF8Encoding($false, $true)
        $raw = [IO.File]::ReadAllText($Path, $utf8)
        if ($raw.Contains([char]0xFFFD)) { Throw-EkInput '인코딩 오류입니다. UTF-8로 저장한 뒤 다시 실행하세요. 원본을 유지합니다.' }
    } catch {
        Throw-EkInput '인코딩 오류입니다. UTF-8로 저장한 뒤 다시 실행하세요. 원본을 유지합니다.'
    }
    if (-not $raw.TrimStart().StartsWith('{')) { Throw-EkInput 'JSON 객체 형식이 아닙니다. 원본을 유지합니다.' }
    try { $value = ConvertTo-EkMap (ConvertFrom-Json -InputObject $raw) }
    catch { Throw-EkInput 'JSON을 읽을 수 없습니다. 원본을 유지합니다. 판매자와 확인하세요.' }
    return $value
}
function Throw-EkInput([string]$Message) {
    $errorValue = New-Object System.ArgumentException($Message)
    $errorValue.Data['EkSafe'] = $true
    throw $errorValue
}
function Get-EkSafeError($Record, [string]$Fallback) {
    if ($Record.Exception.Data['EkSafe']) { return $Record.Exception.Message }
    return $Fallback
}
function Get-EkFinalPath([string]$Path) {
    if (-not ('EkNativePath' -as [type])) {
        # Reflection.Emit는 메모리에서만 P/Invoke를 정의합니다. 외부 임시
        # 컴파일 파일이나 패키지 설치 없이 폴더 핸들의 최종 경로를 읽습니다.
        $assemblyName = New-Object Reflection.AssemblyName('EkPathInterop')
        $assembly = [Reflection.Emit.AssemblyBuilder]::DefineDynamicAssembly($assemblyName,[Reflection.Emit.AssemblyBuilderAccess]::Run)
        $module = $assembly.DefineDynamicModule('EkPathInterop')
        $builder = $module.DefineType('EkNativePath',[Reflection.TypeAttributes]::Public)
        $attrs = [Reflection.MethodAttributes]::Public -bor [Reflection.MethodAttributes]::Static -bor [Reflection.MethodAttributes]::PinvokeImpl
        $create = $builder.DefinePInvokeMethod('CreateFile','kernel32.dll','CreateFileW',$attrs,[Reflection.CallingConventions]::Standard,[Microsoft.Win32.SafeHandles.SafeFileHandle],[type[]]@([string],[uint32],[uint32],[IntPtr],[uint32],[uint32],[IntPtr]),[Runtime.InteropServices.CallingConvention]::Winapi,[Runtime.InteropServices.CharSet]::Unicode)
        $create.SetImplementationFlags([Reflection.MethodImplAttributes]::PreserveSig)
        $resolve = $builder.DefinePInvokeMethod('GetFinalPathNameByHandle','kernel32.dll','GetFinalPathNameByHandleW',$attrs,[Reflection.CallingConventions]::Standard,[uint32],[type[]]@([Microsoft.Win32.SafeHandles.SafeFileHandle],[Text.StringBuilder],[uint32],[uint32]),[Runtime.InteropServices.CallingConvention]::Winapi,[Runtime.InteropServices.CharSet]::Unicode)
        $resolve.SetImplementationFlags([Reflection.MethodImplAttributes]::PreserveSig)
        $details = $builder.DefinePInvokeMethod('GetFileInformationByHandle','kernel32.dll','GetFileInformationByHandle',$attrs,[Reflection.CallingConventions]::Standard,[bool],[type[]]@([Microsoft.Win32.SafeHandles.SafeFileHandle],[IntPtr]),[Runtime.InteropServices.CallingConvention]::Winapi,[Runtime.InteropServices.CharSet]::Unicode)
        $details.SetImplementationFlags([Reflection.MethodImplAttributes]::PreserveSig)
        $null = $builder.CreateType()
    }
    $handle = [EkNativePath]::CreateFile([IO.Path]::GetFullPath($Path),0,7,[IntPtr]::Zero,3,0x02000000,[IntPtr]::Zero)
    try {
        if ($handle.IsInvalid) { Throw-EkInput '경로를 확인할 수 없습니다. 폴더 존재 여부와 실행 권한을 확인하세요.' }
        $buffer = New-Object Text.StringBuilder 32768
        $length = [EkNativePath]::GetFinalPathNameByHandle($handle,$buffer,[uint32]$buffer.Capacity,0)
        if (-not $length -or $length -ge $buffer.Capacity) { Throw-EkInput '실제 경로를 확인할 수 없습니다. 판매자와 확인하세요.' }
        $value = $buffer.ToString()
    } finally { if ($handle) { $handle.Dispose() } }
    if ($value.StartsWith('\\?\UNC\')) { Throw-EkInput '네트워크 연결 경로는 사용할 수 없습니다. 로컬 폴더를 선택하세요.' }
    if ($value.StartsWith('\\?\')) { $value = $value.Substring(4) }
    return $value
}
# BY_HANDLE_FILE_INFORMATION is 52 bytes; DWORD attributes offset 0, link count offset 40.
function Get-EkHandleInfo([IO.FileStream]$Stream) {
    if (-not ('EkNativePath' -as [type])) { $null = Get-EkFinalPath $Stream.Name }
    $buffer = New-Object Text.StringBuilder 32768
    $length = [EkNativePath]::GetFinalPathNameByHandle($Stream.SafeFileHandle,$buffer,[uint32]$buffer.Capacity,0)
    if (-not $length -or $length -ge $buffer.Capacity) { Throw-EkInput '열린 파일의 실제 경로를 확인할 수 없습니다.' }
    $path = $buffer.ToString()
    if ($path.StartsWith('\\?\UNC\')) { Throw-EkInput '네트워크 연결 경로는 사용할 수 없습니다.' }
    if ($path.StartsWith('\\?\')) { $path = $path.Substring(4) }
    $memory = [Runtime.InteropServices.Marshal]::AllocHGlobal(52)
    try {
        if (-not [EkNativePath]::GetFileInformationByHandle($Stream.SafeFileHandle,$memory)) { Throw-EkInput '열린 파일 정보를 확인할 수 없습니다.' }
        return @{ Path=$path; Links=[uint32][Runtime.InteropServices.Marshal]::ReadInt32($memory,40); Attributes=[uint32][Runtime.InteropServices.Marshal]::ReadInt32($memory,0) }
    } finally { [Runtime.InteropServices.Marshal]::FreeHGlobal($memory) }
}
function Assert-EkSafePath([string]$Path, [string]$TargetHome) {
    if (-not $TargetHome) { Throw-EkInput '저장 경로의 홈 기준이 필요합니다.' }
    $full = [IO.Path]::GetFullPath($Path)
    $homeFull = [IO.Path]::GetFullPath($TargetHome).TrimEnd('\','/')
    if (-not $full.StartsWith($homeFull + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { Throw-EkInput '저장은 지정한 홈 안에서만 가능합니다.' }
    $homeReal = (Get-EkFinalPath $homeFull).TrimEnd('\','/')
    $cursor = $full
    while (-not (Test-Path -LiteralPath $cursor)) { $cursor = Split-Path -Parent $cursor }
    $real = Get-EkFinalPath $cursor
    if ($real -ne $homeReal -and -not $real.StartsWith($homeReal + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { Throw-EkInput '홈 밖으로 연결된 저장 경로에는 쓰지 않습니다.' }
}
function Get-EkStudentPaths([string]$Folder, [string]$TargetHome) {
    $entered = $Folder.Trim()
    if (-not $entered -or $entered -match '[\r\n*?\[\]{}!]' -or $entered -match '(^|[\\/])\.\.([\\/]|$)' -or $entered -notmatch '^[A-Za-z]:[\\/]') { Throw-EkInput '학생 폴더는 와일드카드 없는 로컬 절대 경로로 입력하세요.' }
    $full = [IO.Path]::GetFullPath($entered).TrimEnd('\','/')
    if ($full -eq [IO.Path]::GetPathRoot($full).TrimEnd('\','/')) { Throw-EkInput '드라이브 루트 전체는 학생 폴더로 지정할 수 없습니다.' }
    if (-not (Test-Path -LiteralPath $full -PathType Container)) { Throw-EkInput '학생정보 폴더가 없습니다. 프로필의 경로를 확인하세요.' }
    $real = (Get-EkFinalPath $full).TrimEnd('\','/')
    $homeReal = (Get-EkFinalPath $TargetHome).TrimEnd('\','/')
    if ($full -eq [IO.Path]::GetFullPath($TargetHome).TrimEnd('\','/') -or $real -eq $homeReal -or $real -eq [IO.Path]::GetPathRoot($real).TrimEnd('\','/')) { Throw-EkInput '홈 전체나 드라이브 루트는 학생 폴더로 지정할 수 없습니다.' }
    return @($full, $real) | Select-Object -Unique
}
function Get-EkSettings([string]$TargetHome) {
    if (-not [IO.Path]::IsPathRooted($TargetHome)) { Throw-EkInput '홈 경로는 절대 경로로 입력하세요.' }
    $path = Join-Path $TargetHome '.claude/settings.json'
    Assert-EkSafePath $path $TargetHome
    $value = [ordered]@{}
    if (Test-Path -LiteralPath $path) { $value = Read-EkObject $path }
    return @{ Path = $path; Value = $value; Home = $TargetHome }
}
function Set-EkField($Map, [string]$Key, $Value) { $Map[$Key] = $Value }
function Save-EkSettings($State, [bool]$DoApply) {
    $json = ConvertTo-Json -InputObject $State.Value -Depth 64
    $before = ''
    if (Test-Path -LiteralPath $State.Path) { $before = [IO.File]::ReadAllText($State.Path) }
    if ($before -eq $json) { Write-Output '이미 같은 설정입니다. 변경과 새 백업이 없습니다.'; return }
    if (-not $DoApply) { Write-Output '미리보기(DryRun): 아래 설정을 병합합니다. 아직 저장하지 않았습니다.'; Write-Output $json; return }
    Assert-EkSafePath $State.Path $State.Home
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $State.Path)
    if (Test-Path -LiteralPath $State.Path) {
        $backup = $State.Path + '.ek-backup-' + (Get-Date -Format 'yyyyMMddTHHmmssfffffff')
        [IO.File]::Copy($State.Path, $backup, $false)
    }
    $temp = $State.Path + '.ek-write-' + [guid]::NewGuid().ToString('N')
    [IO.File]::WriteAllText($temp, $json, (New-Object Text.UTF8Encoding $false))
    if (Test-Path -LiteralPath $State.Path) { [IO.File]::Replace($temp, $State.Path, [NullString]::Value) }
    else { [IO.File]::Move($temp, $State.Path) }
    Write-Output '설정을 저장했습니다. 기존 설정이 있었다면 수정 전 백업도 보관했습니다.'
}
function Merge-EkRules($Permissions, [string]$Key, [string[]]$Rules) {
    if ($Permissions.Contains($Key) -and $Permissions[$Key] -isnot [array]) { Throw-EkInput '권한 목록은 배열이어야 합니다. 원본을 유지합니다.' }
    $merged = New-Object 'System.Collections.Generic.List[string]'
    foreach ($rule in @($Permissions[$Key]) + $Rules) {
        if ($null -ne $rule -and $rule -isnot [string]) { Throw-EkInput '권한 항목은 문자열이어야 합니다.' }
        if ($rule -and -not $merged.Contains($rule)) { $merged.Add($rule) }
    }
    $Permissions[$Key] = @($merged.ToArray())
}
function Get-EkProfile([string]$ProfilePath) {
    if (-not $ProfilePath) { Throw-EkInput '고객 프로필 파일을 지정하세요.' }
    $p = Read-EkObject $ProfilePath
    if (-not $p.Contains('studentDataPaths') -or $p.studentDataPaths -isnot [array] -or $p.studentDataPaths.Count -lt 1) { Throw-EkInput '프로필에 학생정보 폴더를 1개 이상 입력하세요. 없으면 판매자와 범위를 다시 확인하세요.' }
    return $p
}

# 아직 없는 출력 경로도 가장 가까운 기존 상위 폴더의 최종 경로로 투영합니다.
function Get-EkProjectedPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $cursor = $full
    $tail = New-Object 'System.Collections.Generic.Stack[string]'
    while (-not (Test-Path -LiteralPath $cursor)) {
        $tail.Push([IO.Path]::GetFileName($cursor))
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if (-not $parent -or $parent -eq $cursor) { Throw-EkInput '실제 저장 경로를 확인할 수 없습니다.' }
        $cursor = $parent
    }
    $real = Get-EkFinalPath $cursor
    while ($tail.Count) { $real = Join-Path $real $tail.Pop() }
    return [IO.Path]::GetFullPath($real)
}
function Test-EkWithin([string]$Child, [string]$Parent) {
    $c = $Child.TrimEnd('\','/'); $p = $Parent.TrimEnd('\','/')
    return $c.Equals($p,[StringComparison]::OrdinalIgnoreCase) -or $c.StartsWith($p+'\',[StringComparison]::OrdinalIgnoreCase)
}
function Assert-EkNewOutput([string]$Path) {
    if (Test-Path -LiteralPath $Path) { Throw-EkInput '출력 파일이 이미 있습니다. 새 파일 이름을 지정하세요.' }
    if (-not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path))) -PathType Container)) { Throw-EkInput '출력 폴더를 먼저 만들고 다시 실행하세요.' }
}
# Windows 인자 escaping은 셸 문법을 거치지 않고 CreateProcess 인자 규칙을 따릅니다.
function ConvertTo-EkArgument([string]$Value) {
    return '"' + [regex]::Replace([regex]::Replace($Value,'(\\*)"','$1$1\"'),'(\\+)$','$1$1') + '"'
}
function Get-EkCodexReviewTimeout {
    $seconds = 0
    if ($env:EK_CODEX_REVIEW_TIMEOUT -cmatch '^[0-9]+\z' -and [int]::TryParse($env:EK_CODEX_REVIEW_TIMEOUT, [ref]$seconds) -and $seconds -ge 1 -and $seconds -le 600) { return $seconds }
    return 600
}
function Start-EkProcess([string]$Executable, [string[]]$Arguments, [string]$InputText = '', [int]$TimeoutSeconds = 120, [hashtable]$EnvironmentVariables = @{}, [string]$TimeoutMessage = '실행 시간이 초과되었습니다. 다시 시도하세요.') {
    [Console]::InputEncoding = New-Object Text.UTF8Encoding $false
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (@($Arguments | ForEach-Object { ConvertTo-EkArgument $_ }) -join ' ')
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true; $info.RedirectStandardInput = $true
    $info.StandardOutputEncoding = New-Object Text.UTF8Encoding $false
    foreach ($name in $EnvironmentVariables.Keys) { $info.EnvironmentVariables[$name] = [string]$EnvironmentVariables[$name] }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Write($InputText); $process.StandardInput.Close()
        if ($TimeoutSeconds -gt 0) { $ended = $process.WaitForExit($TimeoutSeconds * 1000) }
        else { $process.WaitForExit(); $ended = $true }
        if (-not $ended) { $null = & taskkill.exe /T /F /PID $process.Id 2>$null; $process.WaitForExit(); Throw-EkInput $TimeoutMessage }
        $process.WaitForExit()
        # 자식이 상속한 파이프를 계속 열고 있어도 완료된 부모를 붙잡지 않습니다.
        $capturedOut = if ($stdout.IsCompleted -and -not $stdout.IsFaulted) { $stdout.Result } else { '' }
        $capturedError = if ($stderr.IsCompleted -and -not $stderr.IsFaulted) { $stderr.Result } else { '' }
        return @{ Code=$process.ExitCode; Output=$capturedOut; Error=$capturedError }
    } finally { $process.Dispose() }
}

function Sanitize-EkText([string]$Text, [string]$TargetHome, [string]$UserName = $env:USERNAME, [string]$ComputerName = $env:COMPUTERNAME) {
    $pairs = @(@($env:USERPROFILE,'<HOME>'),@($TargetHome,'<HOME>'),@($UserName,'<USER>'),@($ComputerName,'<COMPUTER>'),@((Split-Path $TargetHome -Leaf),'<USER>'))
    foreach ($pair in $pairs) {
        if ($pair[0]) {
            foreach ($raw in @($pair[0],$pair[0].Replace('\','/'),$pair[0].Replace('/','\')) | Select-Object -Unique) {
                $token = $pair[1]
                $Text = [regex]::Replace($Text,[regex]::Escape($raw),[Text.RegularExpressions.MatchEvaluator]{ param($m) $token },'IgnoreCase')
            }
        }
    }
    $Text = $Text -replace '[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','<EMAIL>'
    $Text = $Text -replace '(?<!\d)0(?:1[016789]|2|[3-6]\d|70|50\d?)[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)','<PHONE>'
    foreach ($pattern in @('(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])','(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:.]*(?:%[\w.-]+)?(?![\w:])')) {
        $Text = [regex]::Replace($Text,$pattern,{
            param($match)
            $ipValue = $null
            if ([Net.IPAddress]::TryParse(($match.Value -split '%')[0],[ref]$ipValue)) { return '<IP>' }
            return $match.Value
        })
    }
    return $Text
}
