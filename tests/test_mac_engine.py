import importlib.util
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True

root = Path(__file__).resolve().parents[1]
engine = root / 'plugins/ek-workroom/scripts/ek_engine.py'
run = Path(sys.argv[1]) / 'mac-engine'
run.mkdir(parents=True, exist_ok=True)
for action in ('apply-safety', 'apply-statusline'):
    for case in ('absent', 'existing', 'invalid'):
        home = run / (action + '-' + case)
        home.mkdir()
        path = home / '.claude/settings.json'
        path.parent.mkdir()
        old = {'permissions': {'allow': ['Read(README.md)'], 'deny': ['Read(//private/**)']}, 'other': 42, 'statusLine': {'padding': 2}}
        if case == 'existing':
            path.write_text(json.dumps(old), encoding='utf-8')
        elif case == 'invalid':
            path.write_text('{broken', encoding='utf-8')
        original = path.read_bytes() if path.exists() else None
        student = home / 'StudentRecords'
        student.mkdir()
        profile = home / 'profile.json'
        profile.write_text(json.dumps({'studentDataPaths': [str(student)]}, ensure_ascii=False), encoding='utf-8')
        args = [sys.executable, str(engine), action, '--home', str(home), '--profile', str(profile)]
        preview = subprocess.run(args, capture_output=True)
        assert (path.read_bytes() if path.exists() else None) == original
        result = subprocess.run(args + ['--apply'], capture_output=True)
        if case == 'invalid':
            assert result.returncode != 0 and path.read_bytes() == original
            continue
        assert preview.returncode == result.returncode == 0, result.stderr
        value = json.loads(path.read_bytes())
        if case == 'existing':
            assert value['other'] == 42 and value['permissions']['allow'] == old['permissions']['allow']
            copies = list(path.parent.glob('settings.json.ek-backup-*'))
            assert len(copies) == 1 and copies[0].read_bytes() == original
        if action == 'apply-safety':
            assert any('StudentRecords/**)' in rule for rule in value['permissions']['deny'])
            assert any(rule.startswith('Edit(') and 'StudentRecords/**)' in rule for rule in value['permissions']['deny'])
            assert 'Bash' in value['permissions']['ask']
        after = path.read_bytes()
        count = len(list(path.parent.glob('settings.json.ek-backup-*')))
        again = subprocess.run(args + ['--apply'], capture_output=True)
        assert again.returncode == 0 and path.read_bytes() == after
        assert len(list(path.parent.glob('settings.json.ek-backup-*'))) == count

# 진단은 수집 루틴의 외부 명령만 고정해, Mac 없이 누출 경계를 검사합니다.
spec = importlib.util.spec_from_file_location('ek_engine', engine)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.command = lambda *a, **kw: (None, '')
home = run / 'diag'
home.mkdir()
(home / 'PrivateStudentFolderZZ').mkdir()
(home / 'PrivateStudentFolderZZ/DummyStudentZZ.txt').write_text('DummyStudentZZ 010-1234-5678 dummy.student@example.test')
from types import SimpleNamespace
module.diag(SimpleNamespace(home=home, output=None))
report = (home / 'ek-diag.txt').read_text(encoding='utf-8')
for secret in ('PrivateStudentFolderZZ', 'DummyStudentZZ', '010-1234-5678', 'dummy.student@example.test', str(home)):
    assert secret not in report
empty_profile = home / 'empty-profile.json'
empty_profile.write_text(json.dumps({'studentDataPaths': []}), encoding='utf-8')
empty = subprocess.run([sys.executable, str(engine), 'apply-safety', '--home', str(home), '--profile', str(empty_profile)], capture_output=True)
assert empty.returncode != 0 and not (home / '.claude/settings.json').exists()
module.command = lambda *a, **kw: (0, '10.20.30.40')
module.diag(SimpleNamespace(home=home, output=None))
assert '10.20.30.40' not in (home / 'ek-diag.txt').read_text(encoding='utf-8')

# 새 실행기는 가짜 홈·합성 문서만 다루며 실제 Claude/Codex를 실행하지 않습니다.
import contextlib
import io
import os
import re
import zipfile
from unittest.mock import patch

assert run.resolve().is_relative_to((root / '.tmp').resolve())
with patch.object(module.sys, 'platform', 'darwin'):
    assert module.contains(Path('/Users/owner/학생/abc'), Path('/Users/owner/학생/ABC/child'))
    assert module.same_location(Path('/Users/Owner'), Path('/users/owner'))
    assert not module.contains(Path('/Users/owner/abc'), Path('/Users/owner/abcd'))

def invoke(action, *options, stdin=None):
    return subprocess.run([sys.executable, str(engine), action, *map(str, options)],
                          input=stdin, capture_output=True)

work_home = run / 'workspace-home'
work_home.mkdir()
student = work_home / 'student'
student.mkdir()
profile = work_home / 'profile.json'
profile_data = {'studentDataPaths': [str(student)], 'workflow': {'code': 'A'}}
profile.write_text(json.dumps(profile_data), encoding='utf-8')
workspace_dir = work_home / 'AI작업실'
preview = invoke('apply-workspace', '--home', work_home, '--profile', profile, '--dry-run')
assert preview.returncode == 0 and not workspace_dir.exists(), preview.stderr
created = invoke('apply-workspace', '--home', work_home, '--profile', profile)
assert created.returncode == 0, created.stderr
assert (workspace_dir / 'CLAUDE.md').read_text(encoding='utf-8').splitlines()[0] == '@AGENTS.md'
for name in ('입력', '결과', '원본', '검토'):
    assert (workspace_dir / name).is_dir()
agents = workspace_dir / 'AGENTS.md'
agents.write_text('KEEP_EXISTING', encoding='utf-8')
again = invoke('apply-workspace', '--home', work_home, '--profile', profile, '--apply')
assert again.returncode == 0 and agents.read_text(encoding='utf-8') == 'KEEP_EXISTING'
assert '기존 파일 유지' in again.stdout.decode('utf-8')
for bad in (student, student / 'child', work_home, Path(work_home.anchor)):
    bad_profile = dict(profile_data, workspacePath=str(bad))
    profile.write_text(json.dumps(bad_profile), encoding='utf-8')
    rejected = invoke('apply-workspace', '--home', work_home, '--profile', profile)
    assert rejected.returncode != 0, str(bad)
# 작업실이 학생 폴더의 상위인 경우도 거부합니다.
(work_home / 'new/student').mkdir(parents=True)
profile.write_text(json.dumps(dict(profile_data, workspacePath=str(work_home / 'new'),
                                  studentDataPaths=[str(work_home / 'new/student')])), encoding='utf-8')
assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode != 0
# 실제 경로의 연결도 검사합니다. Windows는 관리 권한 없는 junction으로 검증합니다.
alias = work_home / 'alias'
if os.name == 'nt':
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(alias), str(student)], capture_output=True)
    assert made.returncode == 0, made.stderr
else:
    alias.symlink_to(student, target_is_directory=True)
profile.write_text(json.dumps(dict(profile_data, workspacePath=str(alias / 'child'))), encoding='utf-8')
assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode != 0
for unsafe_students in ([], [str(work_home)], [str(work_home / 'missing-student')]):
    profile.write_text(json.dumps(dict(profile_data, studentDataPaths=unsafe_students)), encoding='utf-8')
    assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode != 0
print('PASS Mac workspace: 생성·미리보기·기존 파일·양방향 학생 폴더·실제 연결 경로·루트 차단')

sample = run / 'synthetic.hwpx'
xml = '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:p><hp:run><hp:t>{}</hp:t></hp:run></hp:p></hs:sec>'
with zipfile.ZipFile(sample, 'w') as archive:
    for number in (10, 1, 0):
        archive.writestr(f'Contents/section{number}.xml', xml.format('문단' + str(number)))
text_out = run / 'synthetic.txt'
converted = invoke('ek-hwpx-text', '--hwpx', sample, '--out', text_out)
assert converted.returncode == 0, converted.stderr
assert text_out.read_text(encoding='utf-8').splitlines() == ['문단0', '문단1', '문단10']
assert invoke('ek-hwpx-text', '--hwpx', sample, '--out', text_out).returncode != 0
ole = run / 'old.hwp'
ole.write_bytes(bytes.fromhex('D0CF11E0') + b'FAKE')
assert invoke('ek-hwpx-text', '--hwpx', ole, '--out', run / 'ole.txt').returncode == 2
oversize = run / 'oversize.hwpx'
with zipfile.ZipFile(oversize, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('Contents/section0.xml', b' ' * (50 * 1024 * 1024 + 1))
assert invoke('ek-hwpx-text', '--hwpx', oversize, '--out', run / 'large.txt').returncode != 0
assert not (run / 'large.txt').exists()
print('PASS Mac hwpx-text: section 숫자순·UTF-8·덮어쓰기·OLE 종료 2·50MB 거부')

for payload, expected in [
        ({'model': {'display_name': 'Opus 5.5'}, 'workspace': {'current_dir': '/work/AI작업실'},
          'context_window': {'used_percentage': 12}, 'rate_limits': {'five_hour': {'used_percentage': 23}}},
         'Opus 5.5 · AI작업실 · 대화 12% · 5시간 23%'),
        ({}, 'AI 작업실'), ('{broken', 'AI 작업실')]:
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    result = invoke('statusline', stdin=raw.encode('utf-8'))
    assert result.returncode == 0 and result.stdout.decode('utf-8').strip() == expected, result.stdout
print('PASS Mac statusline: 전체·빈 필드·깨진 JSON 모두 종료 0')
for raw in (b'\xff\xfe', b'{"context_window":{"used_percentage":NaN}}',
            b'{"rate_limits":{"five_hour":{"used_percentage":101}}}'):
    result = invoke('statusline', stdin=raw)
    assert result.returncode == 0 and result.stdout.decode('utf-8').strip() == 'AI 작업실'

# subprocess를 가짜 실행기로 바꿔 실제 Codex 호출 없이 고정 인자와 경계를 검사합니다.
brief = workspace_dir / '검토/brief.md'
brief.write_text('목표: 더미 초안만 검토', encoding='utf-8')
review_out = workspace_dir / '검토/result.md'
calls = []
def fake_codex(args, **kwargs):
    calls.append((args, kwargs))
    Path(args[args.index('-o') + 1]).write_text('가짜 검토 결과', encoding='utf-8')
    return SimpleNamespace(returncode=0)
review_args = SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out))
with patch.object(module.shutil, 'which', return_value='fake-codex'), patch.object(module.subprocess, 'run', fake_codex):
    assert module.codex_review(review_args) == 0
args, options = calls[0]
assert args[args.index('--sandbox') + 1] == 'read-only' and args[-1] == '-'
staged_path = Path(args[args.index('-o') + 1])
assert staged_path.parent.parent == brief.parent and staged_path.parent.name.startswith('.ek-review-')
assert not staged_path.parent.exists()
assert all(token not in args for token in ('--full-auto', '-c', 'workspace-write'))
assert not any(token.startswith('--dangerously-') for token in args)
assert options['input'].decode('utf-8') == brief.read_text(encoding='utf-8')
with patch.object(module.shutil, 'which', return_value=None):
    assert module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('missing.md')))) == 2
try:
    module.codex_review(review_args)
    assert False, '기존 결과 거부 누락'
except module.SafeInputError:
    pass
try:
    module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(run / 'outside.md')))
    assert False, '검토 밖 결과 거부 누락'
except module.SafeInputError:
    pass
print('PASS Mac codex-review: 가짜 호출·고정 read-only 인자·stdin·덮어쓰기·경계·도구 없음')

# 두 호출이 모두 사전체크를 통과해도 결과 공개 시 한 호출만 새 파일을 만듭니다.
import concurrent.futures
import threading
barrier = threading.Barrier(2)
race_out = review_out.with_name('race.md')
def fake_racing_codex(args, **kwargs):
    Path(args[args.index('-o') + 1]).write_text('race-' + threading.current_thread().name, encoding='utf-8')
    barrier.wait(timeout=10)
    return SimpleNamespace(returncode=0)
def racing_review():
    try:
        module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(race_out)))
        return 'created'
    except FileExistsError:
        return 'preserved'
with patch.object(module.shutil, 'which', return_value='fake-codex'), patch.object(module.subprocess, 'run', fake_racing_codex):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(racing_review) for _ in range(2)]
        outcomes = [future.result(timeout=15) for future in futures]
assert sorted(outcomes) == ['created', 'preserved']
assert race_out.read_text(encoding='utf-8').startswith('race-')
assert not list(brief.parent.glob('.ek-review-*'))
print('PASS Mac codex-review: 동시 실행 2개 중 1개만 생성·기존 결과 유지·임시 폴더 정리')

html = run / '입력 문서.html'
html.write_text('<!doctype html><p>한글</p>', encoding='utf-8')
with patch.dict(os.environ, {'EK_PDF_BROWSER': str(run / 'no-browser')}):
    assert module.pdf(SimpleNamespace(html=str(html), pdf=str(run / 'none.pdf'))) == 2
print('PASS Mac pdf: 브라우저 없는 경우 종료 2 (Mac 실제 렌더는 현장 필요)')

# Mac 설치 함수도 가짜 공식 스크립트로 exit 격리·실패 후 Claude 보존을 확인합니다.
import shlex
bootstrap = (root / 'bootstrap/bootstrap.sh').read_text(encoding='utf-8')
install_function = bootstrap.split('\ninstall_codex() {', 1)[1].split('\nif install_codex; then', 1)[0]
install_function = 'install_codex() {' + install_function
bash = __import__('shutil').which('bash')
if bash:
    for installer_exit in (0, 7):
        home = run / ('mac-install-' + str(installer_exit))
        home.mkdir()
        (home / '.local/bin').mkdir(parents=True)
        marker = home / '.local/bin/claude'
        marker.write_bytes(b'CLAUDE_KEEP')
        fake_installer = home / 'fake-install.sh'
        fake_installer.write_text("#!/usr/bin/env bash\nif [ \"$FAKE_INSTALL_EXIT\" -ne 0 ]; then exit \"$FAKE_INSTALL_EXIT\"; fi\nprintf '#!/usr/bin/env bash\\necho codex-cli 0.2.0\\n' > \"$target_home/.local/bin/codex\"\nchmod +x \"$target_home/.local/bin/codex\"\nexit 0\n", encoding='utf-8', newline='\n')
        wrapper = home / 'test-install.sh'
        wrapper.write_text('set -euo pipefail\n' +
            'export target_home=' + shlex.quote(home.as_posix()) + '\nverified_root="$target_home"\n' +
            'command() { if [ "$1" = "-v" ] && [ "$2" = "codex" ]; then [ -x "$target_home/.local/bin/codex" ]; else builtin command "$@"; fi; }\n' +
            'codex() { "$target_home/.local/bin/codex" "$@"; }\n' +
            'curl() { local dest=""; while [ "$#" -gt 0 ]; do if [ "$1" = "-o" ]; then dest=$2; shift 2; else shift; fi; done; cp ' + shlex.quote(fake_installer.as_posix()) + ' "$dest"; }\n' +
            install_function + '\nif install_codex; then echo INSTALL_OK; else echo INSTALL_INCOMPLETE; fi\necho PARENT_CONTINUES\n', encoding='utf-8', newline='\n')
        result = subprocess.run([bash, str(wrapper)], capture_output=True,
                                env=dict(os.environ, FAKE_INSTALL_EXIT=str(installer_exit)))
        assert result.returncode == 0 and b'PARENT_CONTINUES' in result.stdout, result.stderr
        assert (b'INSTALL_OK' if installer_exit == 0 else b'INSTALL_INCOMPLETE') in result.stdout
        assert marker.read_bytes() == b'CLAUDE_KEEP'
    print('PASS Mac bootstrap: 가짜 설치 성공·exit 7 격리·부모 계속·Claude 보존')
else:
    print('SKIP Mac bootstrap shell: 이 검사 환경에 bash 없음')
print('Mac 엔진 검사 통과 (Mac OS 현장 실행은 별도 필요)')
