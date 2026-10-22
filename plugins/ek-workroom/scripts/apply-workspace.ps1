[CmdletBinding()]
param([string]$TargetHome = $env:USERPROFILE, [Parameter(Mandatory=$true)][string]$ProfilePath, [switch]$DryRun, [switch]$Apply)
. "$PSScriptRoot/common.ps1"
try {
    $profile = Get-EkProfile $ProfilePath
    $workspace = if ($profile.workspacePath) { [string]$profile.workspacePath } else { Join-Path $TargetHome 'AI작업실' }
    foreach ($path in @($TargetHome,$workspace)) {
        if ($path -notmatch '^[A-Za-z]:[\\/]' -or $path -match '[\r\n*?]' -or $path -match '(^|[\\/])\.\.([\\/]|$)') { Throw-EkInput '작업실과 홈은 로컬 절대 경로로 지정하세요.' }
    }
    $workspace = [IO.Path]::GetFullPath($workspace).TrimEnd('\','/')
    $real = (Get-EkProjectedPath $workspace).TrimEnd('\','/')
    $homeFull = [IO.Path]::GetFullPath($TargetHome).TrimEnd('\','/')
    $homeReal = (Get-EkFinalPath $TargetHome).TrimEnd('\','/')
    if ($workspace -eq [IO.Path]::GetPathRoot($workspace).TrimEnd('\','/') -or $real -eq [IO.Path]::GetPathRoot($real).TrimEnd('\','/') -or $workspace -eq $homeFull -or $real -eq $homeReal) { Throw-EkInput '드라이브 루트나 홈 전체는 작업실로 지정할 수 없습니다.' }
    $protectedPaths = @()
    foreach ($student in $profile.studentDataPaths) {
        if ($student -isnot [string]) { Throw-EkInput '학생 폴더 경로는 문자열이어야 합니다.' }
        foreach ($studentPath in @(Get-EkStudentPaths $student $TargetHome)) {
            if ($protectedPaths -notcontains $studentPath) { $protectedPaths += $studentPath }
            foreach ($workPath in @($workspace,$real)) {
                if ((Test-EkWithin $studentPath $workPath) -or (Test-EkWithin $workPath $studentPath)) { Throw-EkInput '작업실과 학생정보 폴더는 서로 포함할 수 없습니다.' }
            }
        }
    }
    $code = [string]$profile.workflow.code
    if ($code -notmatch '^[A-E]$') { Throw-EkInput '업무 코드는 A부터 E 중 하나를 지정하세요.' }
    $templates = Join-Path (Split-Path -Parent $PSScriptRoot) 'templates'
    $files = [ordered]@{
        'CLAUDE.md' = "@AGENTS.md`n이 폴더 규칙은 AGENTS.md에 있습니다`n"
        'AGENTS.md' = [IO.File]::ReadAllText((Join-Path $templates 'AGENTS.md'))
        '검토/검토요청-양식.md' = [IO.File]::ReadAllText((Join-Path $templates 'review-brief.md'))
        '내-업무-실행법.md' = [IO.File]::ReadAllText((Join-Path $templates ('flows/'+$code+'.md')))
        '.ek-workroom/protected-paths.json' = ConvertTo-Json -InputObject ([ordered]@{ schemaVersion=1; paths=@($protectedPaths) }) -Depth 4
    }
    # 기존 하위 연결이 작업실 밖을 가리키면 쓰기 전에 거부합니다.
    foreach ($name in @('입력','결과','원본','검토','.ek-workroom') + @($files.Keys)) {
        if (-not (Test-EkWithin (Get-EkProjectedPath (Join-Path $workspace $name)) $real)) { Throw-EkInput '작업실 밖으로 연결된 하위 경로에는 쓰지 않습니다.' }
    }
    $protectedName = '.ek-workroom/protected-paths.json'
    $protectedFile = Join-Path $workspace $protectedName
    $mergeProtection = $false
    if (Test-Path -LiteralPath $protectedFile) {
        $existing = Read-EkObject $protectedFile
        if ($existing.schemaVersion -ne 1 -or $existing.paths -isnot [array] -or $existing.paths.Count -lt 1) { Throw-EkInput '기존 보호 경로 목록을 확인하세요. 목록을 유지합니다.' }
        $combined = @()
        foreach ($path in $existing.paths) {
            if ($path -isnot [string] -or $path -notmatch '^[A-Za-z]:[\\/]') { Throw-EkInput '기존 보호 경로 목록을 확인하세요. 목록을 유지합니다.' }
            $combined += $path
        }
        foreach ($path in $protectedPaths) {
            if ($combined -notcontains $path) { $combined += $path; $mergeProtection = $true }
        }
        if ($mergeProtection) {
            $existing.paths = @($combined)
            $files[$protectedName] = ConvertTo-Json -InputObject $existing -Depth 8
        }
    }
    foreach ($name in @('입력','결과','원본','검토','.ek-workroom')) {
        $dest = Join-Path $workspace $name
        if (Test-Path -LiteralPath $dest) {
            if (-not (Test-Path -LiteralPath $dest -PathType Container)) { Throw-EkInput '작업실 하위 폴더 위치에 파일이 있습니다.' }
        } elseif ($DryRun) { Write-Output ('만들 폴더: '+$name+'/') }
        else { $null = [IO.Directory]::CreateDirectory($dest); Write-Output ('폴더 생성: '+$name+'/') }
    }
    foreach ($name in $files.Keys) {
        $dest = Join-Path $workspace $name
        if ($name -eq $protectedName -and $mergeProtection) {
            if ($DryRun) { Write-Output ('보호 경로 병합 예정: '+$name); continue }
            $backup = $dest + '.bak-' + (Get-Date -Format 'yyyyMMddTHHmmssfffffff')
            [IO.File]::Copy($dest,$backup,$false)
            $temp = $dest + '.write-' + [guid]::NewGuid().ToString('N')
            try {
                [IO.File]::WriteAllText($temp,$files[$name],(New-Object Text.UTF8Encoding $false))
                [IO.File]::Replace($temp,$dest,[NullString]::Value)
            } finally { if (Test-Path -LiteralPath $temp) { [IO.File]::Delete($temp) } }
            Write-Output ('보호 경로 병합: '+$name+' (기존 목록 보존·백업 완료)')
            continue
        }
        if (Test-Path -LiteralPath $dest) { if (-not $DryRun) { Write-Output ('기존 파일 유지: '+$name) }; continue }
        if ($DryRun) { Write-Output ('만들 파일: '+$name); continue }
        $stream = [IO.File]::Open($dest,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $bytes = (New-Object Text.UTF8Encoding $false).GetBytes($files[$name]); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
        Write-Output ('파일 생성: '+$name)
    }
} catch { Write-Output (Get-EkSafeError $_ '작업실 생성 실패: 프로필과 저장 위치를 확인하세요.'); exit 1 }
