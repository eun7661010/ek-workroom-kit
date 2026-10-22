"""v0.2.2 실행 도구 시험. 설치/실제 AI 호출 없이 저장소 .tmp에서만 쓴다."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]).resolve() / 'v020'
assert run.is_relative_to(root / '.tmp')
run.mkdir(parents=True)
scripts = root / 'plugins/ek-workroom/scripts'
ps = [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
      '-NoProfile', '-ExecutionPolicy', 'Bypass']
env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
for key, name in [('USERPROFILE', 'home'), ('HOME', 'home'), ('TEMP', 'temp'), ('TMP', 'temp'),
                  ('CLAUDE_CONFIG_DIR', 'claude'), ('CODEX_HOME', 'codex')]:
    folder = run / name
    folder.mkdir(exist_ok=True)
    env[key] = str(folder)


def execute(args, *, input=None, extra=None, timeout=140):
    return subprocess.run(args, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=dict(env, **(extra or {})), timeout=timeout)


def tool(name, *args, **kwargs):
    if name == 'ek-codex-review' and '-Target' not in args:
        args += ('-Target', target)
    return execute(ps + ['-File', str(scripts / (name + '.ps1'))] + [str(a) for a in args], **kwargs)


def check(ok, name, result=None):
    if not ok and result:
        print(result.stdout.decode('utf-8', errors='replace'))
        print(result.stderr.decode('utf-8', errors='replace'))
    assert ok, name
    print('PASS ' + name)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


home = Path(env['HOME'])
student = home / '학생 자료'
student.mkdir()
profile = home / 'profile.json'
workspace = home / 'AI작업실'
data = {'studentDataPaths': [str(student)], 'workflow': {'code': 'E'}}
write_json(profile, data)
preview = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(preview.returncode == 0 and not workspace.exists(), 'workspace DryRun 쓰기 0', preview)
created = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
check(created.returncode == 0 and all((workspace / p).is_dir() for p in ('입력', '결과', '원본', '검토')),
      'workspace 기본 실행 생성', created)
check((workspace / 'CLAUDE.md').read_text(encoding='utf-8-sig').splitlines()[0] == '@AGENTS.md', 'workspace CLAUDE import 첫 줄')
protection = workspace / '.ek-workroom/protected-paths.json'
check(json.loads(protection.read_text(encoding='utf-8')) == {'schemaVersion': 1, 'paths': [str(student)]}, 'workspace 학생 보호 경로 목록 생성')
before = {p.relative_to(workspace): p.read_bytes() for p in workspace.rglob('*') if p.is_file()}
(workspace / '내-업무-실행법.md').write_text('고객 수정 유지', encoding='utf-8')
before[Path('내-업무-실행법.md')] = (workspace / '내-업무-실행법.md').read_bytes()
again = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-Apply')
check(again.returncode == 0 and '기존 파일 유지' in again.stdout.decode('utf-8') and
      all((workspace / p).read_bytes() == raw for p, raw in before.items()), 'workspace 재실행 기존 파일 유지', again)
other_student = home / 'StudentRecords'
other_student.mkdir()
write_json(profile, dict(data, studentDataPaths=[str(other_student)]))
changed_profile = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
backups = list(protection.parent.glob('protected-paths.json.bak-*'))
check(changed_profile.returncode == 0 and set(json.loads(protection.read_text(encoding='utf-8'))['paths']) == {str(student), str(other_student)} and
      len(backups) == 1 and backups[0].read_bytes() == before[Path('.ek-workroom/protected-paths.json')], 'workspace 보호 목록 합집합·기존 원본 백업', changed_profile)
merged = protection.read_bytes()
again = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
check(again.returncode == 0 and protection.read_bytes() == merged and len(list(protection.parent.glob('*.bak-*'))) == 1, 'workspace 같은 보호 목록 재실행 추가 백업 없음', again)


def reject_workspace(path, label):
    write_json(profile, dict(data, workspacePath=str(path)))
    result = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
    check(result.returncode != 0 and str(home).encode() not in result.stdout, label, result)


reject_workspace(student / '작업실', 'workspace 학생 폴더 안 거부')
reject_workspace(home, 'workspace 홈 전체 거부')
reject_workspace(home.anchor, 'workspace 드라이브 루트 거부')
outer = home / '보관함'
nested_student = outer / '학생기록'
nested_student.mkdir(parents=True)
write_json(profile, dict(data, studentDataPaths=[str(nested_student)], workspacePath=str(outer)))
r = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(r.returncode != 0, 'workspace 학생 폴더 포함 거부', r)
reject_workspace(str(student).upper() + '/WORK', 'workspace 대소문자 변형 거부')
alias = home / '연결 폴더'
q = lambda x: "'" + str(x).replace("'", "''") + "'"
r = execute(ps + ['-Command', 'New-Item -ItemType Junction -Path '+q(alias)+' -Target '+q(student)+' | Out-Null'])
check(r.returncode == 0, 'workspace junction 시험 준비', r)
reject_workspace(alias / '새 작업실', 'workspace 실제 junction 학생 경로 거부')
write_json(profile, dict(data, studentDataPaths=[str(alias / '아래')], workspacePath=str(student)))
(student / '아래').mkdir()
r = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(r.returncode != 0, 'workspace 학생 alias 반대 포함관계 거부', r)
alias_workspace = home / 'AliasWork'
write_json(profile, dict(data, studentDataPaths=[str(alias)], workspacePath=str(alias_workspace)))
r = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
check(r.returncode == 0 and set(json.loads((alias_workspace / '.ek-workroom/protected-paths.json').read_text(encoding='utf-8'))['paths']) == {str(alias), str(student)}, 'workspace 학생 입력·실제 junction 경로 함께 보관', r)

# 실제 Edge/HTTP 격리 시험은 test_pdf_isolation.py에서 실행합니다.

hwpx, out = run / '합성.hwpx', run / '합성.txt'
ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
with zipfile.ZipFile(hwpx, 'w', zipfile.ZIP_DEFLATED) as z:
    for n in (10, 1, 0):
        z.writestr(f'Contents/section{n}.xml', f'<root xmlns:hp="{ns}"><hp:p><hp:run><hp:t>본문{n}</hp:t><hp:t> 끝</hp:t></hp:run></hp:p></root>')
result = tool('ek-hwpx-text', '-Hwpx', hwpx, '-Out', out)
check(result.returncode == 0 and out.read_text(encoding='utf-8-sig').splitlines() == ['본문0 끝', '본문1 끝', '본문10 끝'],
      'HWPX section0·1·10 숫자순·문단 텍스트', result)
check(tool('ek-hwpx-text', '-Hwpx', hwpx, '-Out', out).returncode != 0, 'HWPX 기존 결과 덮어쓰기 거부')
ole = run / '구형.hwp'
ole.write_bytes(bytes.fromhex('D0CF11E0') + b'\0' * 12)
result = tool('ek-hwpx-text', '-Hwpx', ole, '-Out', run / 'ole.txt')
check(result.returncode == 2 and not (run / 'ole.txt').exists(), 'HWP OLE 안내 종료 2', result)
oversize = run / '큰.hwpx'
with zipfile.ZipFile(oversize, 'w', zipfile.ZIP_DEFLATED) as z:
    with z.open('Contents/section0.xml', 'w') as f:
        for _ in range(51):
            f.write(b'x' * 1024 * 1024)
check(tool('ek-hwpx-text', '-Hwpx', oversize, '-Out', run / 'oversize.txt').returncode != 0 and
      not (run / 'oversize.txt').exists(), 'HWPX 압축 내부 합 50MB 초과 거부')

# PATH 앞에 가짜 CLI만 놓고 인자·stdin·종료 코드를 확인한다.
fakebin = run / 'fake-bin'
fakebin.mkdir()
record, prompt_record = run / 'codex-args.json', run / 'codex-stdin.txt'
stub = fakebin / 'fake-codex.py'
stub.write_text('''import json, os, sys, time
from pathlib import Path
cwd=Path(sys.argv[sys.argv.index('-C')+1])
assert cwd.is_dir() and not list(cwd.iterdir()), 'CWD_NOT_EMPTY'
assert not Path(sys.argv[sys.argv.index('-o')+1]).is_relative_to(cwd), 'OUTPUT_IN_CWD'
Path(os.environ['EK_FAKE_ARGS']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
Path(os.environ['EK_FAKE_STDIN']).write_bytes(sys.stdin.buffer.read())
code = int(os.environ.get('EK_FAKE_EXIT', '0'))
if code: sys.exit(code)
if os.environ.get('EK_FAKE_BARRIER'):
    barrier=Path(os.environ['EK_FAKE_BARRIER'])
    (barrier / str(os.getpid())).touch()
    deadline=time.monotonic()+10
    while len(list(barrier.iterdir()))<2:
        if time.monotonic()>deadline: sys.exit(9)
        time.sleep(.02)
Path(sys.argv[sys.argv.index('-o')+1]).write_text(os.environ.get('EK_FAKE_TEXT','더미 검토 결과'), encoding='utf-8')
''', encoding='utf-8', newline='\n')
(fakebin / 'codex.cmd').write_text('@"'+sys.executable+'" "%~dp0fake-codex.py" %*\r\n', encoding='utf-8')
fakeenv = {'PATH': str(fakebin)+os.pathsep+env['PATH'], 'EK_FAKE_ARGS': str(record), 'EK_FAKE_STDIN': str(prompt_record)}
brief, review_out = workspace / '검토/검토 요청.md', workspace / '검토/검토 결과.md'
brief.write_text('목표: 더미 문서 검토\n금지: 학생정보·비밀값\n', encoding='utf-8')
target = workspace / '결과/더미 초안.md'
target.write_text('학교 안내문 더미 내용', encoding='utf-8-sig')
header = '아래 파일 내용만 근거로 검토한다. 도구는 없다. 결과는 답변 텍스트로만.\n\n'
def expected_prompt(brief_path=brief):
    return header + brief_path.read_text(encoding='utf-8-sig') + '\n\n=== 파일: 결과/더미 초안.md ===\n학교 안내문 더미 내용'
disabled = 'shell_tool unified_exec browser_use browser_use_external browser_use_full_cdp_access in_app_browser computer_use apps plugins remote_plugin multi_agent view_image code_mode_host memories hooks workspace_dependencies skill_mcp_dependency_install'.split()
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', review_out, extra=fakeenv)
check(result.returncode == 0 and review_out.exists() and record.exists(), 'Codex 가짜 CLI 실행 성공', result)
arguments = json.loads(record.read_text(encoding='utf-8-sig'))
check(arguments[:8] == ['exec', '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral', '--color', 'never', '-C'] and
      not Path(arguments[8]).is_relative_to(workspace) and not Path(arguments[8]).exists() and
      arguments[9:-7] == [item for feature in disabled for item in ('--disable', feature)] and
      arguments[-7:-2] == ['-c', 'mcp_servers={}', '-c', 'web_search=disabled', '-o'] and arguments[-1] == '-' and
      Path(arguments[-2]).parent.parent == workspace / '검토' and
      prompt_record.read_text(encoding='utf-8-sig').strip() == expected_prompt().strip(),
      'Codex 17개 도구 비활성·MCP 비움·웹 검색 끔·빈 임시 CWD·대상 내용 전달·임시 정리')
record_before = record.read_bytes()
for index, protected_text in enumerate((str(student).upper().replace('\\', '/'), student.name,
                                        str(other_student).upper().replace('\\', '/'), other_student.name.upper(),
                                        'ＳｔｕｄｅｎｔＲｅｃｏｒｄｓ', 'Student\u200bRecords')):
    # 대소문자 변형도 실제 검사되도록 영문 보호 경로를 테스트 목록에 추가합니다.
    write_json(protection, {'schemaVersion': 1, 'paths': [str(student), str(other_student)]})
    unsafe_brief = brief.with_name(f'protected-{index}.md')
    unsafe_brief.write_text('검토 대상: ' + protected_text, encoding='utf-8')
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', unsafe_brief, '-Out', brief.with_name(f'blocked-{index}.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before and
          '보호 대상 폴더' in result.stdout.decode('utf-8-sig') and str(home) not in result.stdout.decode('utf-8-sig'),
          f'Codex 보호 경로 변형·폴더명 {index+1} 실행 전 거부', result)
saved_protection = protection.read_bytes()
protection.unlink()
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', brief.with_name('no-protection.md'), extra=fakeenv)
check(result.returncode == 2 and result.stdout.decode('utf-8-sig').strip() == '작업실 만들기(ek-mode)를 먼저 하세요' and record.read_bytes() == record_before, 'Codex 보호 목록 없음 종료 2·실행 없음', result)
protection.write_bytes(saved_protection)
for malformed in ({'schemaVersion': 1, 'paths': []}, {'schemaVersion': 1, 'paths': ['relative']}):
    write_json(protection, malformed)
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', brief.with_name('invalid-protection.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 손상된 보호 목록 거부', result)
protection.write_bytes(saved_protection)
missing_target = execute(ps + ['-File', str(scripts / 'ek-codex-review.ps1'), '-Workspace', str(workspace), '-Brief', str(brief), '-Out', str(brief.with_name('no-target.md'))], extra=fakeenv)
check(missing_target.returncode == 1, 'Codex 대상 최소 1개 필수', missing_target)
outside_target = run / 'outside.txt'
outside_target.write_text('OUTSIDE_SECRET', encoding='utf-8')
inside_protected = workspace / 'PrivateRecords'
inside_protected.mkdir()
private_target = inside_protected / 'secret.txt'
private_target.write_text('PROTECTED_SECRET', encoding='utf-8')
write_json(protection, {'schemaVersion': 1, 'paths': [str(student), str(other_student), str(inside_protected)]})
target_alias = workspace / '입력/별칭'
r = execute(ps + ['-Command', 'New-Item -ItemType Junction -Path '+q(target_alias)+' -Target '+q(inside_protected)+' | Out-Null'])
check(r.returncode == 0, 'Codex 보호 대상 junction 준비', r)
hidden_target = workspace / '.hidden/secret.txt'
hidden_target.parent.mkdir()
hidden_target.write_text('HIDDEN_SECRET', encoding='utf-8')
binary_target = workspace / '결과/disallowed.json'
binary_target.write_text('{}', encoding='utf-8')
oversized_target = workspace / '결과/large.txt'
oversized_target.write_bytes(b'x' * (200 * 1024 + 1))
invalid_utf8 = workspace / '결과/non-utf8.txt'
invalid_utf8.write_bytes(b'\xff\xfeh\0i\0')
cases = [(outside_target, '작업실 밖'), (private_target, '작업실 내부 보호 폴더'),
         (target_alias / 'secret.txt', '보호 폴더 junction'), (hidden_target, '숨김 폴더'),
         (protection, '보호 목록 숨김 경로'), (binary_target, '비허용 확장자'),
         (oversized_target, '파일당 200KB'), (invalid_utf8, 'UTF-16 BOM 거부')]
for index, (candidate, label) in enumerate(cases):
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Target', candidate, '-Out', brief.with_name(f'target-blocked-{index}.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before and str(home) not in result.stdout.decode('utf-8-sig'), 'Codex 대상 '+label+' 거부·CLI 실행 없음', result)
# 열린 핸들의 하드링크 개수와 파일·상위 폴더 숨김 속성을 검사합니다.
import ctypes
hard_target = workspace / '결과/hard-target.txt'
r = execute(ps + ['-Command', 'New-Item -ItemType HardLink -Path '+q(hard_target)+' -Target '+q(outside_target)+' | Out-Null'])
check(r.returncode == 0 and hard_target.stat().st_nlink >= 2, 'Codex 같은 볼륨 하드링크 준비', r)
hidden_parent = workspace / '결과/ordinary-parent'
hidden_parent.mkdir()
parent_target = hidden_parent / 'target.txt'
parent_target.write_text('HIDDEN_PARENT_SECRET', encoding='utf-8')
assert ctypes.windll.kernel32.SetFileAttributesW(str(hidden_parent), 2)
for candidate, label in [(hard_target, '하드링크'), (parent_target, '숨김 속성 상위 폴더')]:
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Target', candidate,
                  '-Out', brief.with_name('blocked-'+label+'.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 대상 '+label+' 거부', result)
brief_hidden_parent = workspace / '검토/ordinary-parent'
brief_hidden_parent.mkdir()
brief_parent = brief_hidden_parent / 'brief.md'
brief_parent.write_text('더미 검토', encoding='utf-8')
assert ctypes.windll.kernel32.SetFileAttributesW(str(brief_hidden_parent), 2)
brief_hard = brief.with_name('hard-brief.md')
os.link(outside_target, brief_hard)
brief_hidden = brief.with_name('hidden-brief.md')
brief_hidden.write_text('더미 검토', encoding='utf-8')
assert ctypes.windll.kernel32.SetFileAttributesW(str(brief_hidden), 2)
brief_large = brief.with_name('large-brief.md')
brief_large.write_bytes(b'x' * (200 * 1024 + 1))
brief_invalid = brief.with_name('utf16-brief.md')
brief_invalid.write_bytes(b'\xff\xfeh\0i\0')
for index, (candidate, label) in enumerate([(brief_hard, '하드링크'), (brief_hidden, '숨김 파일'),
        (brief_parent, '숨김 상위 폴더'), (brief_large, '200KB 초과'), (brief_invalid, 'UTF-16 BOM')]):
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', candidate,
                  '-Out', brief.with_name(f'brief-rejected-{index}.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 브리프 '+label+' 거부·CLI 실행 없음', result)
# 작업실 루트 자체가 숨김이면 정상 이름의 파일도 거부합니다.
assert ctypes.windll.kernel32.SetFileAttributesW(str(workspace), 2)
try:
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Target', target,
                  '-Out', brief.with_name('hidden-workspace.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 숨김 작업실 루트 거부', result)
finally:
    assert ctypes.windll.kernel32.SetFileAttributesW(str(workspace), 16)
brief_bom = brief.with_name('utf8-bom.md')
brief_bom.write_text('더미 UTF-8 BOM 검토', encoding='utf-8-sig')
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief_bom, '-Target', target,
              '-Out', brief.with_name('brief-bom-result.md'), extra=fakeenv)
check(result.returncode == 0 and prompt_record.read_text(encoding='utf-8-sig').startswith(header+'더미 UTF-8 BOM 검토'), 'Codex 브리프 UTF-8 BOM 허용', result)
record_before = record.read_bytes()

# Deterministically replace a previously checked directory just before opening its file.
# The consumer must validate the opened handle, not reopen a trusted path name blindly.
race_dir = workspace / 'read-race'
race_dir.mkdir()
race_target = race_dir / 'secret.txt'
race_target.write_text('SAFE_CONTENT', encoding='utf-8')
race_runner = run / 'read-race.ps1'
race_runner.write_text('''function Get-Item {
    param([string]$LiteralPath, [switch]$Force)
    $item = Microsoft.PowerShell.Management\\Get-Item -LiteralPath $LiteralPath -Force:$Force
    if ($LiteralPath -eq $env:EK_RACE_TARGET -and -not $script:changed) {
        $script:changed = $true
        [IO.Directory]::Move($env:EK_RACE_DIRECTORY, $env:EK_RACE_DIRECTORY + '-saved')
        $null = New-Item -ItemType Junction -Path $env:EK_RACE_DIRECTORY -Target $env:EK_RACE_PRIVATE
    }
    return $item
}
& $env:EK_RACE_SCRIPT -Workspace $env:EK_RACE_WORKSPACE -Brief $env:EK_RACE_BRIEF -Out $env:EK_RACE_OUTPUT -Target $env:EK_RACE_TARGET
exit $LASTEXITCODE
''', encoding='utf-8-sig', newline='\r\n')
race_result = execute(ps + ['-File', str(race_runner)], extra=dict(fakeenv,
    EK_RACE_SCRIPT=str(scripts / 'ek-codex-review.ps1'), EK_RACE_WORKSPACE=str(workspace),
    EK_RACE_BRIEF=str(brief), EK_RACE_OUTPUT=str(brief.with_name('read-race.md')),
    EK_RACE_TARGET=str(race_target), EK_RACE_DIRECTORY=str(race_dir), EK_RACE_PRIVATE=str(inside_protected)))
check(race_result.returncode == 1 and record.read_bytes() == record_before
      and '실제 경로가 바뀌어' in race_result.stdout.decode('utf-8-sig')
      and not brief.with_name('read-race.md').exists(), 'Codex 검사 후 junction 교체도 열린 핸들로 차단', race_result)
import ctypes
short = ctypes.create_unicode_buffer(32768)
if ctypes.windll.kernel32.GetShortPathNameW(str(private_target), short, len(short)) and '~' in short.value:
    result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Target', short.value, '-Out', brief.with_name('short-blocked.md'), extra=fakeenv)
    check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 8.3 실제 경로 보호 거부', result)
else:
    print('SKIP 8.3 별칭: 이 테스트 폴더에 짧은 이름 없음 (최종 경로 검사는 junction으로 검증)')
large_targets = []
for index in range(3):
    item = workspace / f'결과/batch-{index}.txt'
    item.write_bytes(b'x' * (180 * 1024))
    large_targets.extend(('-Target', item))
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, *large_targets, '-Out', brief.with_name('total-too-large.md'), extra=fakeenv)
check(result.returncode == 1 and record.read_bytes() == record_before, 'Codex 대상 합계 500KB 초과 거부', result)
second_target = workspace / '입력/표.csv'
second_target.write_text('항목,값\n수량,2', encoding='utf-8')
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Target', target, '-Target', second_target, '-Out', brief.with_name('multiple.md'), extra=fakeenv)
check(result.returncode == 0 and prompt_record.read_text(encoding='utf-8-sig').strip() == (expected_prompt()+'\n\n=== 파일: 입력/표.csv ===\n항목,값\n수량,2').strip(), 'Codex 반복 Target 파일 내용 블록 전달', result)
protection.write_bytes(saved_protection)
before = review_out.read_bytes()
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', review_out, extra=fakeenv).returncode != 0 and
      review_out.read_bytes() == before, 'Codex 결과 덮어쓰기 거부')
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '결과/밖.md', extra=fakeenv).returncode != 0, 'Codex 검토 밖 출력 거부')
outside_brief = workspace / '입력/밖.md'
outside_brief.write_text('범위 밖', encoding='utf-8')
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', outside_brief, '-Out', workspace / '검토/새.md', extra=fakeenv).returncode != 0, 'Codex 검토 밖 브리프 거부')
linked = workspace / '검토/연결'
r = execute(ps + ['-Command', 'New-Item -ItemType Junction -Path '+q(linked)+' -Target '+q(workspace / '결과')+' | Out-Null'])
check(r.returncode == 0 and tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', linked / '유출.md', extra=fakeenv).returncode != 0, 'Codex 실제 junction 경계 거부')
# npm 설치의 codex.ps1처럼 파이프 입력일 때만 stdin을 넘기는 실행기에서도 브리프가 전달되는지 확인한다.
shimbin = run / 'fake-shim-bin'
shimbin.mkdir()
(shimbin / 'codex.ps1').write_text('if ($args.Count -eq 1 -and $args[0] -is [array]) { exit 9 }\r\nif ($MyInvocation.ExpectingInput) { $input | & '+q(Path(sys.executable))+' '+q(stub)+' @args } else { & '+q(Path(sys.executable))+' '+q(stub)+' @args }\r\nexit $LASTEXITCODE\r\n', encoding='utf-8-sig')
shim_stdin = run / 'codex-shim-stdin.txt'
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/shim 결과.md',
              extra=dict(fakeenv, PATH=str(shimbin)+os.pathsep+env['PATH'], EK_FAKE_STDIN=str(shim_stdin)))
check(result.returncode == 0 and shim_stdin.exists() and
      shim_stdin.read_text(encoding='utf-8-sig').strip() == expected_prompt().strip(), 'Codex ps1 실행기(npm)에도 한국어 브리프 stdin 전달', result)
for index, quote in enumerate('‘’‚‛'):
    injection_work = home / (f'주입{index}' + quote + ';New-Item EK_INJECTION_MARKER;# $x `tick')
    write_json(profile, dict(data, workspacePath=str(injection_work)))
    result = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
    check(result.returncode == 0, f'workspace 특수문자 경로 {index+1} 생성', result)
    injection_brief = injection_work / '검토/brief.md'
    injection_brief.write_text('더미 검토', encoding='utf-8')
    injection_out = injection_work / '검토/out.md'
    result = subprocess.run(ps + ['-File', str(scripts / 'ek-codex-review.ps1'), '-Workspace', str(injection_work),
                                 '-Brief', str(injection_brief), '-Target', str(injection_brief), '-Out', str(injection_out)], cwd=run,
                            env=dict(env, **dict(fakeenv, PATH=str(shimbin)+os.pathsep+env['PATH'])), capture_output=True, timeout=60)
    check(result.returncode == 0 and injection_out.exists() and not (run / 'EK_INJECTION_MARKER').exists() and
          Path(json.loads(record.read_text(encoding='utf-8'))[-2]).parent.parent == injection_work / '검토',
          f'Codex 둥근 따옴표 {index+1}·달러·백틱·세미콜론 인자 보존·주입 없음', result)
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/실패.md', extra=dict(fakeenv, EK_FAKE_EXIT='7'))
check(result.returncode == 7, 'Codex 종료 코드 7 전달', result)
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/미설치.md', extra={'PATH': str(Path(ps[0]).parent)})
check(result.returncode == 2, 'Codex 미설치 종료 2', result)
barrier = run / 'race-barrier'
barrier.mkdir()
race_out = workspace / '검토/동시 결과.md'
def race(label):
    return tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', race_out,
                extra=dict(fakeenv, EK_FAKE_BARRIER=str(barrier), EK_FAKE_TEXT=label,
                           EK_FAKE_ARGS=str(run / ('race-'+label+'.json')), EK_FAKE_STDIN=str(run / ('race-'+label+'.txt'))))
with ThreadPoolExecutor(max_workers=2) as pool:
    concurrent = list(pool.map(race, ('A', 'B')))
check(sorted(p.returncode for p in concurrent) == [0, 1] and race_out.read_text(encoding='utf-8-sig') in ('A','B') and
      not list((workspace / '검토').glob('.ek-review-*')), 'Codex 동시 실행 1개만 결과 생성·덮어쓰기 0·임시 정리')

for payload, expected in [
    ({'model': {'display_name': 'Opus 5.5'}, 'workspace': {'current_dir': 'D:/업무/AI작업실'},
      'context_window': {'used_percentage': 12}, 'rate_limits': {'five_hour': {'used_percentage': 23}}}, 'Opus 5.5 · AI작업실 · 대화 12% · 5시간 23%'),
    ({}, 'AI 작업실'), (b'{broken', 'AI 작업실'),
    ({'model': {'display_name': 'Opus 5.5'}, 'context_window': {'used_percentage': 0}}, 'Opus 5.5 · 대화 0%')]:
    result = tool('statusline', input=payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    check(result.returncode == 0 and result.stdout.decode('utf-8-sig').strip() == expected, '상태줄 전체/없음/깨짐/0% 기대 출력·종료0', result)

# 부트스트랩 공식 설치 호출을 가짜 다운로드로 바꾸고 exit 격리를 실제 하위 프로세스로 확인한다.
for fail in (False, True):
    fixture = run / ('bootstrap-fail' if fail else 'bootstrap-ok')
    fixture.mkdir()
    ready = fixture / 'ready'
    claude = fixture / 'claude.cmd'
    claude.write_text('@echo fake Claude\r\n', encoding='utf-8')
    codex = fixture / 'codex.cmd'
    codex.write_text('@echo codex 0.99.0\r\n@exit /b 0\r\n', encoding='utf-8')
    installer = fixture / 'installer.ps1'
    installer.write_text(('exit 7\n' if fail else "[IO.File]::WriteAllText("+q(ready)+",'ready'); exit 0\n"), encoding='utf-8-sig')
    runner = fixture / 'runner.ps1'
    runner.write_text('. '+q(root / 'bootstrap/bootstrap.ps1')+' -Library\n'+'''
function Get-Command { param($Name,$CommandType,$ErrorAction)
    if($Name -eq 'codex') { if(Test-Path -LiteralPath READY) { return [pscustomobject]@{Source=CODEX} }; return $null }
    Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters
}
function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec)
    if($Uri -ne 'https://chatgpt.com/codex/install.ps1'){throw '잘못된 공식 URL'}
    Copy-Item -LiteralPath INSTALLER -Destination $OutFile
}
$ok=Invoke-EkCodexInstall -TargetHome FIXTURE -KitRoot FIXTURE
if($ok -ne EXPECTED){throw '예상 결과 불일치'}
if(-not(Test-Path -LiteralPath CLAUDE)){throw 'Claude 보존 실패'}
Write-Output 'PARENT_CONTINUED'
'''.replace('READY', q(ready)).replace('CODEX', q(codex)).replace('INSTALLER', q(installer)).replace('FIXTURE', q(fixture)).replace('EXPECTED', '$false' if fail else '$true').replace('CLAUDE', q(claude)), encoding='utf-8-sig', newline='\r\n')
    result = execute(ps + ['-File', str(runner)])
    check(result.returncode == 0 and b'PARENT_CONTINUED' in result.stdout and (ready.exists() != fail),
          'bootstrap Codex '+('실패 Claude 보존·exit 격리' if fail else '설치 성공·PATH/버전 확인·exit 격리'), result)

skills = sorted(p.parent.name for p in (root / 'plugins/ek-workroom/skills').glob('*/SKILL.md'))
expected = sorted(('ek-start ek-safety ek-mode ek-codex-link ek-flow ek-handoff cross-check worksheet-pdf lesson-slides hwpx-read parent-message spreadsheet-check korean-review explanation-draft question-draft blog-column').split())
check(skills == expected, '스킬 정확히 16개 정합')
blocked = ['offline'+'-spacing', 'scan'+'-cleanup', 'blog'+'-copy', 'director'+'-column', 'hwp'+'-convert',
           'kit/'+'ek-setup', 'Wa'+'rp', 'cs'+'wap', 'account'+'Label', 'selected'+'Skills', 'kor'+'doc', 'kiwi'+'piepy', 'Every'+'thing', 'VS'+' Code']
history = {'docs/review-v0.1-response.md', 'docs/validation-report.md', 'docs/validation-v0.1.1.md'}
listing = execute(['git', 'ls-files', '-co', '--exclude-standard', '-z']).stdout.decode('utf-8')
violations = []
for name in set(listing.split('\0')) - {''}:
    path = root / name
    if name in history or not path.is_file() or path.suffix not in ('.md', '.json', '.ps1', '.sh', '.py', '.txt'):
        continue
    text = path.read_text(encoding='utf-8-sig')
    for word in blocked:
        if word.lower() in text.lower():
            violations.append(name + ': ' + word)
check(not violations, '삭제 대상 참조 0 (이력 3개 제외): ' + ', '.join(violations))
print('v0.2.2 실행 도구 검사 완료')
