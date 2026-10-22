"""v0.2.3 회귀. 외부 다운로드·설치는 모두 가짜로 대체한다."""
from compat_support import write_text
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
import zipfile

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
work, release = (Path(x).resolve() for x in sys.argv[1:3])
assert work.is_relative_to(root / '.tmp') and release.is_relative_to(root / '.tmp'), '테스트는 저장소 .tmp 안에서만 실행합니다.'
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
isolated = work / 'python-isolated-home'
isolated.mkdir(exist_ok=True)
env.update(USERPROFILE=str(isolated), HOME=str(isolated), CLAUDE_CONFIG_DIR=str(isolated / 'claude'), CODEX_HOME=str(isolated / 'codex'))
bash_exe = shutil.which('bash')
assert bash_exe, 'Git Bash가 필요합니다.'
env['PATH'] = str(Path(bash_exe).parent) + os.pathsep + env['PATH']
ps = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass']

def run(args, **kw):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=kw.pop('env', env), timeout=60, **kw)

def check(condition, name):
    assert condition, name
    print('PASS ' + name)

# 입력/출력을 바이트로 잡아 CP949 호스트에서의 실제 경계를 확인한다.
payload = json.dumps({'model': {'display_name': '테스트 모델'}, 'workspace': {'current_dir': 'D:/업무/AI작업실'}}, ensure_ascii=False).encode('utf-8')
statusline = root / 'plugins/ek-workroom/scripts/statusline.ps1'
cmd = "[Console]::InputEncoding=[Text.Encoding]::GetEncoding(949);[Console]::OutputEncoding=[Text.Encoding]::GetEncoding(949); & '" + str(statusline).replace("'", "''") + "'"
p = run(ps + ['-Command', cmd], input=payload)
output = p.stdout.decode('utf-8', errors='strict')
check(p.returncode == 0 and output.strip() == '테스트 모델 · AI작업실', 'CP949 호스트 상태줄 UTF-8 stdin/stdout')

engine_path = root / 'plugins/ek-workroom/scripts/ek_engine.py'
spec = importlib.util.spec_from_file_location('engine_v011', engine_path)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
home = work / 'python-home'
home.mkdir()
student = home / '학생정보(2026)'
student.mkdir()
variants = engine.student_paths(str(student), home)
check(unicodedata.normalize('NFC', str(student)) in variants and unicodedata.normalize('NFD', str(student)) in variants, '학생 경로 NFC/NFD 모두 생성')
alias = home / 'student-link'
if os.name == 'nt':
    command = 'New-Item -ItemType Junction -Path ' + "'" + str(alias).replace("'", "''") + "' -Target '" + str(student).replace("'", "''") + "' | Out-Null"
    assert run(ps + ['-Command', command]).returncode == 0
else:
    alias.symlink_to(student, target_is_directory=True)
check(str(alias) in engine.student_paths(str(alias), home) and str(student.resolve()) in engine.student_paths(str(alias), home), 'Mac 엔진 입력/연결 최종 경로 둘 다 생성')
for folder in [home, Path(home.anchor), home / 'missing']:
    rejected = False
    try:
        engine.student_paths(str(folder), home)
    except engine.SafeInputError:
        rejected = True
    check(rejected, 'Mac 엔진 홈/루트/없는 경로 거부')
private = '은광 원장 010.1234.5678 02-123-4567 0507-1234-5678 10.20.30.40 2001:db8::1234'
masked = engine.mask_text(private, home, user='은광', computer='원장')
check(all(x not in masked for x in private.split()), 'Mac 엔진 두 글자·전화·IPv6 마스킹')

archive = release / 'ek-workroom-0.2.3.zip'
with zipfile.ZipFile(archive) as z:
    check(z.testzip() is None, '릴리스 ZIP 무결성')
    for name in z.namelist():
        if name.endswith(('.sh', '.py')):
            check(b'\r' not in z.read(name), '릴리스 Mac 실행 파일 CR 0: ' + name)

# 텍스트 파일은 git 대상 목록으로 읽어 .tmp·.git과 고객 파일을 탐색하지 않는다.
listing = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=root).decode('utf-8')
for name in set(listing.split('\0')) - {''}:
    path = root / name
    if path.suffix not in ('.md', '.json', '.ps1', '.sh', '.py', '.txt') and path.name not in ('.gitignore', '.gitattributes'):
        continue
    if not path.is_file():
        continue
    data = path.read_bytes()
    text = data.decode('utf-8-sig', errors='strict')
    check(not any(unicodedata.category(c) == 'Cc' and c not in '\t\r\n' for c in text), '제어문자 0: ' + name)
    if path.suffix in ('.sh', '.py'):
        check(b'\r' not in data, 'Mac 실행 파일 LF: ' + name)
    if path.suffix == '.ps1':
        check(re.search(rb'(?<!\r)\n', data) is None, 'PowerShell CRLF: ' + name)

# 실제 설치 스크립트 대신 DryRun 표지만 출력하는 배포 fixture로 붙여넣기 전체를 실행한다.
fixture = work / 'paste-fixture'
(fixture / '.claude-plugin').mkdir(parents=True)
(fixture / '.claude-plugin/marketplace.json').write_text('{}', encoding='utf-8')
(fixture / 'bootstrap').mkdir()
stub_ps = fixture / 'bootstrap/bootstrap.ps1'
write_text(stub_ps, "param($Source,$ExpectedSha256,$Version,[switch]$DryRun)\nWrite-Output 'PASTE_STUB_DRYRUN'\nexit 0\n", encoding='utf-8-sig', newline='\r\n')
stub_sh = fixture / 'bootstrap/bootstrap.sh'
write_text(stub_sh, "#!/usr/bin/env bash\necho PASTE_STUB_DRYRUN\n", encoding='utf-8', newline='\n')
paste_release = work / 'paste-release'
built = run(ps + ['-File', str(root / 'bootstrap/make-release.ps1'), '-SourceDirectory', str(fixture), '-OutputDirectory', str(paste_release), '-ReleaseBaseUrl', 'https://release.example.test/kit'])
check(built.returncode == 0, '붙여넣기 블록 fixture 릴리스')
for mismatch in (False, True):
    ps_source = stub_ps
    sh_source = stub_sh
    if mismatch:
        ps_source = work / 'wrong-bootstrap.ps1'
        ps_source.write_text("Write-Output 'SHOULD_NOT_RUN'", encoding='utf-8')
        sh_source = work / 'wrong-bootstrap.sh'
        sh_source.write_text('echo SHOULD_NOT_RUN\n', encoding='utf-8')
    wrapper = work / ('paste-wrong.ps1' if mismatch else 'paste-good.ps1')
    mock = "function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing); Copy-Item -LiteralPath '" + str(ps_source).replace("'", "''") + "' -Destination $OutFile }\n"
    write_text(wrapper, mock + (paste_release / 'paste-block-windows.txt').read_text(encoding='utf-8-sig'), encoding='utf-8-sig', newline='\r\n')
    result = run(ps + ['-File', str(wrapper)])
    check((result.returncode != 0 and b'SHOULD_NOT_RUN' not in result.stdout) if mismatch else (result.returncode == 0 and b'PASTE_STUB_DRYRUN' in result.stdout), 'Windows 붙여넣기 ' + ('불일치 중단' if mismatch else '자동 검증 후 DryRun'))
    bash_wrapper = work / ('paste-wrong.sh' if mismatch else 'paste-good.sh')
    mock = 'curl() { local out=""; while [ "$#" -gt 0 ]; do if [ "$1" = "-o" ]; then out=$2; shift 2; else shift; fi; done; cp ' + shlex.quote(sh_source.as_posix()) + ' "$out"; }\n'
    write_text(bash_wrapper, mock + (paste_release / 'paste-block-mac.txt').read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
    bash_env = dict(env, HOME=(work / ('mac-paste-wrong' if mismatch else 'mac-paste-good')).as_posix())
    result = run([bash_exe, str(bash_wrapper)], env=bash_env)
    check((result.returncode != 0 and b'SHOULD_NOT_RUN' not in result.stdout) if mismatch else (result.returncode == 0 and b'PASTE_STUB_DRYRUN' in result.stdout), 'Mac 붙여넣기 ' + ('불일치 중단' if mismatch else '자동 검증 후 DryRun'))

# 같은 실제 ZIP을 Mac 셸 진입점으로 배치하고 동버전 거부를 확인한다. 설치는 호출하지 않는다.
mac_home = work / 'mac-prepare-home'
mac_home.mkdir()
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
args = [bash_exe, str(root / 'bootstrap/bootstrap.sh'), '--source', str(archive), '--expected-sha256', digest, '--home', str(mac_home), '--prepare-only']
result = run(args)
check(result.returncode == 0 and (mac_home / 'ek-workroom/kit-0.2.3/.claude-plugin/marketplace.json').exists(), 'Mac 진입점 고정 경로 준비만 실행')
check(run(args).returncode != 0, 'Mac 진입점 같은 위치 재실행 거부')
print('v0.2.3 Python 회귀 완료')
