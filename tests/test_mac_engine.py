import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import unicodedata
from unittest.mock import patch
sys.dont_write_bytecode = True

root = Path(__file__).resolve().parents[1]
engine = root / 'plugins/ek-workroom/scripts/ek_engine.py'
# /tmp 별칭으로 시작해도 열린 핸들 경로와 race 테스트의 비교가 일치해야 합니다.
run = (Path(sys.argv[1]) / 'mac-engine').resolve()
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
with patch.object(module, 'security_software', return_value=[]):
    module.diag(SimpleNamespace(home=home, output=None))
report = (home / 'ek-diag.txt').read_text(encoding='utf-8')
for secret in ('PrivateStudentFolderZZ', 'DummyStudentZZ', '010-1234-5678', 'dummy.student@example.test', str(home)):
    assert secret not in report
empty_profile = home / 'empty-profile.json'
empty_profile.write_text(json.dumps({'studentDataPaths': []}), encoding='utf-8')
empty = subprocess.run([sys.executable, str(engine), 'apply-safety', '--home', str(home), '--profile', str(empty_profile)], capture_output=True)
assert empty.returncode != 0 and not (home / '.claude/settings.json').exists()
module.command = lambda *a, **kw: (0, '10.20.30.40')
with patch.object(module, 'security_software', return_value=[]):
    module.diag(SimpleNamespace(home=home, output=None))
assert '10.20.30.40' not in (home / 'ek-diag.txt').read_text(encoding='utf-8')
assert '보안 SW: 확인 필요' in (home / 'ek-diag.txt').read_text(encoding='utf-8')

# 명령의 성공 코드·프로세스 이름만으로 설치를 판정하지 않습니다.
applications = home / 'Applications'
daemons = home / 'LaunchDaemons'
applications.mkdir()
daemons.mkdir()
def app_fixture(name, identifier=None, executable=True):
    app = applications / (name + '.app')
    (app / 'Contents/MacOS').mkdir(parents=True)
    data = {'CFBundleExecutable': 'agent'}
    if identifier is not None:
        data['CFBundleIdentifier'] = identifier
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(data))
    if executable:
        binary = app / 'Contents/MacOS/agent'
        binary.write_bytes(b'FAKE_EXECUTABLE')
        binary.chmod(0o755)
    return app

app_fixture('Defender AhnLab CrowdStrike')
app_fixture('Unrelated', 'com.microsoft.wdavlookalike')
app_fixture('MissingBinary', 'com.ahnlab.v3', executable=False)
(daemons / 'com.crowdstrike.falcon.plist').write_bytes(b'broken plist')
(daemons / 'malformed-xml.plist').write_bytes(b'<plist><dict>')
(daemons / 'wrong-type.plist').write_bytes(plistlib.dumps(['com.microsoft.wdav']))
assert module.security_software(applications, daemons) == []
app_fixture('DifferentDisplayName', 'com.microsoft.wdav')
app_fixture('V3', 'com.ahnlab.v3')
falcon = home / 'falcond'
falcon.write_bytes(b'FAKE_EXECUTABLE')
falcon.chmod(0o755)
daemon = daemons / 'installed.plist'
for program in ({'Program': str(falcon.resolve())}, {'ProgramArguments': [str(falcon.resolve()), '--daemon']}):
    daemon.write_bytes(plistlib.dumps(dict(program, Label='com.crowdstrike.falcon.Agent')))
    assert module.security_software(applications, daemons) == ['Defender', 'AhnLab', 'CrowdStrike']
for program in ({'Program': 'falcond'}, {'Program': str(home / 'missing')},
                {'ProgramArguments': []}, {'ProgramArguments': [42]}):
    daemon.write_bytes(plistlib.dumps(dict(program, Label='com.crowdstrike.falcon.Agent')))
    assert module.security_software(applications, daemons) == ['Defender', 'AhnLab']
with patch.object(module, 'security_software', return_value=['Defender']), contextlib.redirect_stdout(io.StringIO()):
    module.diag(SimpleNamespace(home=home, output=None))
report = (home / 'ek-diag.txt').read_text(encoding='utf-8')
assert '보안 SW: Defender (설치 흔적 확인, 실행 상태는 확인 필요)' in report
assert str(applications) not in report and 'DifferentDisplayName' not in report
print('PASS Mac 보안 SW: 프로세스 성공·이름만으로 판정 금지, 앱/launchd 식별자+실행 파일 확인')

# 새 실행기는 가짜 홈·합성 문서만 다루며 실제 Claude/Codex를 실행하지 않습니다.
import re
import zipfile

assert run.resolve().is_relative_to((root / '.tmp').resolve())
with patch.object(module.sys, 'platform', 'darwin'):
    assert module.contains(Path('/Users/owner/학생/abc'), Path('/Users/owner/학생/ABC/child'))
    assert module.same_location(Path('/Users/Owner'), Path('/users/owner'))
    assert not module.contains(Path('/Users/owner/abc'), Path('/Users/owner/abcd'))
    assert module.relative_inside(Path('/Users/Owner/WORK'), Path('/users/owner/work/Folder/File.md')).as_posix() == 'Folder/File.md'

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
protected_file = workspace_dir / '.ek-workroom/protected-paths.json'
protected_original = protected_file.read_bytes()
protected = json.loads(protected_original)
assert protected['schemaVersion'] == 1 and str(student) in protected['paths']
for name in ('입력', '결과', '원본', '검토'):
    assert (workspace_dir / name).is_dir()
agents = workspace_dir / 'AGENTS.md'
agents.write_text('KEEP_EXISTING', encoding='utf-8')
again = invoke('apply-workspace', '--home', work_home, '--profile', profile, '--apply')
assert again.returncode == 0 and agents.read_text(encoding='utf-8') == 'KEEP_EXISTING'
assert '기존 파일 유지' in again.stdout.decode('utf-8')
another_student = work_home / 'new-student-records'
another_student.mkdir()
profile.write_text(json.dumps(dict(profile_data, studentDataPaths=[str(another_student)])), encoding='utf-8')
again = invoke('apply-workspace', '--home', work_home, '--profile', profile)
assert again.returncode == 0
merged_paths = json.loads(protected_file.read_bytes())['paths']
assert str(student) in merged_paths and str(another_student) in merged_paths
backups = list(protected_file.parent.glob('*.bak-*'))
assert len(backups) == 1 and backups[0].read_bytes() == protected_original
again = invoke('apply-workspace', '--home', work_home, '--profile', profile)
assert again.returncode == 0 and len(list(protected_file.parent.glob('*.bak-*'))) == 1
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
# 보호 목록에는 사용자가 입력한 alias와 실제 경로, NFC/NFD를 모두 보존합니다.
unicode_student = work_home / '학생 기록'
unicode_student.mkdir()
variants = module.student_paths(str(unicode_student), work_home)
assert unicodedata.normalize('NFC', str(unicode_student)) in variants
assert unicodedata.normalize('NFD', str(unicode_student)) in variants
alias_workspace = work_home / 'alias-workspace'
profile.write_text(json.dumps(dict(profile_data, workspacePath=str(alias_workspace),
                                  studentDataPaths=[str(alias)])), encoding='utf-8')
assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode == 0
alias_paths = json.loads((alias_workspace / '.ek-workroom/protected-paths.json').read_bytes())['paths']
assert str(alias) in alias_paths and str(student.resolve()) in alias_paths
linked_workspace = work_home / 'linked-workspace'
linked_workspace.mkdir()
metadata_alias = linked_workspace / '.ek-workroom'
if os.name == 'nt':
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(metadata_alias), str(student)], capture_output=True)
    assert made.returncode == 0, made.stderr
else:
    metadata_alias.symlink_to(student, target_is_directory=True)
profile.write_text(json.dumps(dict(profile_data, workspacePath=str(linked_workspace))), encoding='utf-8')
assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode != 0
assert not (student / 'protected-paths.json').exists() and not (linked_workspace / '입력').exists()
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
    empty = Path(args[args.index('-C') + 1])
    assert empty.is_dir() and not list(empty.iterdir())
    assert not Path(args[args.index('-o') + 1]).is_relative_to(empty)
    calls.append((args, kwargs))
    Path(args[args.index('-o') + 1]).write_text('가짜 검토 결과', encoding='utf-8')
    return SimpleNamespace(returncode=0)
target = workspace_dir / '결과/검토 초안.md'
target.write_text('전달할 초안 내용', encoding='utf-8')
review_args = SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out), target=[str(target)])
with patch.object(module.shutil, 'which', return_value='fake-codex'), patch.object(module.subprocess, 'run', fake_codex):
    assert module.codex_review(review_args) == 0
args, options = calls[0]
assert args[args.index('--sandbox') + 1] == 'read-only' and args[-1] == '-'
staged_path = Path(args[args.index('-o') + 1])
assert staged_path.parent.parent.resolve() == brief.parent.resolve() and staged_path.parent.name.startswith('.ek-review-')
assert not staged_path.parent.exists()
assert all(token not in args for token in ('--full-auto', 'workspace-write'))
assert [args[i + 1] for i, value in enumerate(args) if value == '-c'] == ['mcp_servers={}', 'web_search="disabled"']
assert [args[i + 1] for i, value in enumerate(args) if value == '--disable'] == module.CODEX_DISABLED_FEATURES
empty_cwd = Path(args[args.index('-C') + 1])
assert empty_cwd != workspace_dir and not empty_cwd.exists()
assert not any(token.startswith('--dangerously-') for token in args)
assert options['input'].decode('utf-8') == module.REVIEW_HEADER + brief.read_text(encoding='utf-8') + '\n\n=== 파일: 결과/검토 초안.md ===\n전달할 초안 내용'
assert '도구는 없다' in options['input'].decode('utf-8')
assert all(path not in options['input'].decode('utf-8') for path in protected['paths'])
with patch.object(module.shutil, 'which', return_value=None):
    assert module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('missing.md')), target=[str(target)])) == 2
try:
    module.codex_review(review_args)
    assert False, '기존 결과 거부 누락'
except module.SafeInputError:
    pass
try:
    module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(run / 'outside.md'), target=[str(target)]))
    assert False, '검토 밖 결과 거부 누락'
except module.SafeInputError:
    pass
print('PASS Mac codex-review: 가짜 호출·고정 read-only 인자·stdin·덮어쓰기·경계·도구 없음')

# 보호 목록이 없거나 망가졌거나 브리프가 보호 경로를 언급하면 Codex에 도달하지 않습니다.
clean_brief = brief.read_text(encoding='utf-8')
for forbidden in (str(student).upper(), str(student).replace('\\', '/'),
                  str(student).replace('/', '\\'), student.name.upper()):
    brief.write_text('검토 대상: ' + forbidden, encoding='utf-8')
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')):
        try:
            module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('protected.md')), target=[str(target)]))
            assert False, forbidden
        except module.SafeInputError:
            pass
brief.write_text(clean_brief, encoding='utf-8')
protected_file.write_text(json.dumps({'schemaVersion': 1, 'paths': variants}, ensure_ascii=False), encoding='utf-8')
brief.write_text(unicodedata.normalize('NFD', str(unicode_student)).upper(), encoding='utf-8')
try:
    module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('unicode.md')), target=[str(target)]))
    assert False, 'NFC/NFD 보호 경로 거부 누락'
except module.SafeInputError:
    pass
brief.write_text(clean_brief, encoding='utf-8')
for bad_metadata in ({}, {'schemaVersion': 1, 'paths': []}, {'schemaVersion': 1, 'paths': ['']},
                     {'schemaVersion': 1, 'paths': [123]}, {'schemaVersion': 1, 'paths': ['relative']}):
    protected_file.write_text(json.dumps(bad_metadata), encoding='utf-8')
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')):
        try:
            module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('invalid.md')), target=[str(target)]))
            assert False, bad_metadata
        except module.SafeInputError:
            pass
protected_file.unlink()
try:
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')), contextlib.redirect_stdout(io.StringIO()) as guidance:
        assert module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('missing-protection.md')), target=[str(target)])) == 2
    assert '작업실 만들기(ek-mode)를 먼저 하세요' in guidance.getvalue()
finally:
    protected_file.write_bytes(protected_original)
print('PASS Mac codex-review: 보호 경로 대소문자·슬래시·폴더명 거부·목록 누락 종료2·손상 fail closed·머리말')

# 대상은 문자열 경로 필터가 아닌 최종 실제 파일 위치와 크기로 제한합니다.
protected_file.write_bytes(protected_original)
protected_target = student / 'private.md'
protected_target.write_text('학생정보', encoding='utf-8')
protected_alias = workspace_dir / '결과/student-alias'
if os.name == 'nt':
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(protected_alias), str(student)], capture_output=True)
    assert made.returncode == 0, made.stderr
else:
    protected_alias.symlink_to(student, target_is_directory=True)
hidden = workspace_dir / '.hidden'
hidden.mkdir()
(hidden / 'brief.md').write_text('hidden', encoding='utf-8')
unsupported = workspace_dir / '결과/unsupported.py'
unsupported.write_text('print(1)', encoding='utf-8')
large = workspace_dir / '결과/large.md'
large.write_bytes(b'x' * (200 * 1024 + 1))
invalid_utf8 = workspace_dir / '결과/invalid.txt'
invalid_utf8.write_bytes(b'\xff')
for bad in (protected_target, protected_alias / 'private.md', hidden / 'brief.md', unsupported, large, invalid_utf8):
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')):
        try:
            module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(review_out.with_name('blocked.md')), target=[str(bad)]))
            assert False, str(bad)
        except module.SafeInputError:
            pass
batch = []
for n in range(3):
    file = workspace_dir / '결과' / f'batch{n}.txt'
    file.write_bytes(b'x' * (180 * 1024))
    batch.append(str(file))
try:
    module.target_text(workspace_dir.resolve(), protected['paths'], batch)
    assert False, '합계 500KB 제한 누락'
except module.SafeInputError:
    pass
for spelling in ('ｓｔｕｄｅｎｔ', 's\u200btudent', 's\u034f\u180b\ufe0ftudent',
                 str(student).replace('\\', '＼').replace('/', '／')):
    try:
        module.protected_brief(protected['paths'], spelling)
        assert False, 'NFKC 또는 제로폭 검사 누락'
    except module.SafeInputError:
        pass
print('PASS Mac Codex 대상: 작업실·보호 경로·junction·숨김·확장자·파일/합계 용량·UTF8·NFKC/제로폭 경계')

# Brief도 Target과 동일한 열린 핸들·숨김·용량·인코딩·하드링크 검사를 통과해야 합니다.
hard_target = workspace_dir / '결과/hardlink.md'
os.link(target, hard_target)
hard_brief = brief.with_name('hardlink.md')
os.link(brief, hard_brief)
try:
    for raw, boundary in ((target, None), (hard_target, None), (brief, brief.parent), (hard_brief, brief.parent)):
        try:
            module.read_review_file(workspace_dir.resolve(), protected['paths'], str(raw), boundary)
            assert False, '하드링크 허용'
        except module.SafeInputError:
            pass
finally:
    hard_target.unlink()
    hard_brief.unlink()
hidden_brief_dir = brief.parent / '.brief-hidden'
hidden_brief_dir.mkdir()
hidden_brief = hidden_brief_dir / 'brief.md'
hidden_brief.write_text('brief', encoding='utf-8')
large_brief = brief.with_name('large.md')
large_brief.write_bytes(b'x' * (200 * 1024 + 1))
invalid_brief = brief.with_name('invalid-utf8.md')
invalid_brief.write_bytes(b'\xff')
for bad in (hidden_brief, large_brief, invalid_brief):
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')):
        try:
            module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(bad), out=str(brief.with_name('invalid-result.md')), target=[str(target)]))
            assert False, str(bad)
        except module.SafeInputError:
            pass
# 실제 OS의 숨김 상위 속성도 검사합니다. 파일 자체는 visible입니다.
attribute_folder = workspace_dir / '결과/attribute-hidden'
attribute_folder.mkdir()
attribute_target = attribute_folder / 'visible.md'
attribute_target.write_text('visible', encoding='utf-8')
if os.name == 'nt':
    import ctypes
    assert ctypes.windll.kernel32.SetFileAttributesW(str(attribute_folder), 2)
    try:
        try:
            module.read_review_file(workspace_dir.resolve(), protected['paths'], str(attribute_target))
            assert False, '숨김 상위 속성 허용'
        except module.SafeInputError:
            pass
    finally:
        assert ctypes.windll.kernel32.SetFileAttributesW(str(attribute_folder), 0x80)
elif sys.platform == 'darwin':
    import stat
    os.chflags(attribute_folder, stat.UF_HIDDEN)
    try:
        try:
            module.read_review_file(workspace_dir.resolve(), protected['paths'], str(attribute_target))
            assert False, 'Mac 숨김 상위 속성 허용'
        except module.SafeInputError:
            pass
    finally:
        os.chflags(attribute_folder, 0)
print('PASS Mac Codex: Brief/Target 공용 검사·하드링크·Brief UTF8/200KB/숨김·상위 폴더 속성 거부')

# 검증 후 열기 직전에 디렉터리를 보호 폴더 연결로 바꿔도 열린 핸들의 실경로가 거부됩니다.
race_folder = workspace_dir / '결과/open-race'
race_folder.mkdir()
race_file = race_folder / 'race.md'
race_file.write_text('ALLOWED_BEFORE_SWAP', encoding='utf-8')
(student / 'race.md').write_text('SECRET_AFTER_SWAP', encoding='utf-8')
original_open = Path.open
swapped = []
def swap_before_open(path, *args, **kwargs):
    if path == race_file and not swapped:
        race_folder.rename(race_folder.with_name('open-race-original'))
        if os.name == 'nt':
            made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(race_folder), str(student)], capture_output=True)
            assert made.returncode == 0, made.stderr
        else:
            race_folder.symlink_to(student, target_is_directory=True)
        swapped.append(True)
    return original_open(path, *args, **kwargs)
with patch.object(Path, 'open', swap_before_open):
    try:
        module.target_text(workspace_dir.resolve(), protected['paths'], [str(race_file)])
        assert False, '검증과 열기 사이 보호 폴더 교체 허용'
    except module.SafeInputError:
        pass
assert swapped
print('PASS Mac Codex 열린 핸들: 검증 직후 junction/symlink 교체로 보호 파일을 열어도 읽기 전 거부')

# Mac 실행기는 인자를 subprocess 배열로 넘기므로 경로의 셸 문자를 소스로 해석하지 않습니다.
unusual_workspace = work_home / '‘’‚‛$`;' / 'AI작업실'
profile.write_text(json.dumps(dict(profile_data, workspacePath=str(unusual_workspace))), encoding='utf-8')
assert invoke('apply-workspace', '--home', work_home, '--profile', profile).returncode == 0
unusual_brief = unusual_workspace / '검토/brief.md'
unusual_brief.write_text(clean_brief, encoding='utf-8')
unusual_target = unusual_workspace / '결과/초안.md'
unusual_target.write_text('특수 경로 초안', encoding='utf-8')
with patch.object(module.shutil, 'which', return_value='fake-codex'), patch.object(module.subprocess, 'run', fake_codex):
    assert module.codex_review(SimpleNamespace(workspace=str(unusual_workspace), brief=str(unusual_brief), out=str(unusual_brief.with_name('result.md')), target=[str(unusual_target)])) == 0
assert calls[-1][0][calls[-1][0].index('-C') + 1] != str(unusual_workspace.resolve())
print('PASS Mac codex-review: 둥근 따옴표·달러·백틱·세미콜론 경로를 인자 배열로 유지')

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
        module.codex_review(SimpleNamespace(workspace=str(workspace_dir), brief=str(brief), out=str(race_out), target=[str(target)]))
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

html = workspace_dir / '결과/입력 문서.html'
html.write_text('<!doctype html><p>한글</p>', encoding='utf-8')
with patch.dict(os.environ, {'EK_PDF_BROWSER': str(run / 'no-browser')}):
    assert module.pdf(SimpleNamespace(html=str(html), pdf=str(run / 'none.pdf'))) == 2
outside_html = run / 'outside.html'
outside_html.write_text('outside', encoding='utf-8')
with contextlib.redirect_stdout(io.StringIO()) as guidance:
    assert module.pdf(SimpleNamespace(html=str(outside_html), pdf=str(run / 'outside.pdf'))) == 2
assert '작업실 안 HTML만 PDF로 만들 수 있습니다' in guidance.getvalue()
inside_protected = workspace_dir / '결과/보호자료'
inside_protected.mkdir()
secret_html = inside_protected / 'secret.html'
secret_html.write_text('secret', encoding='utf-8')
old_metadata = protected_file.read_bytes()
protected_file.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(student), str(inside_protected)]}), encoding='utf-8')
try:
    for bad in (secret_html, html):
        try:
            module.pdf(SimpleNamespace(html=str(bad), pdf=str(run / 'blocked.pdf')))
            assert False, '보호 경로 내부 또는 품는 서버 루트 허용'
        except module.SafeInputError:
            pass
finally:
    protected_file.write_bytes(old_metadata)
main_hardlink = html.with_name('hard-main.html')
os.link(html, main_hardlink)
try:
    try:
        module.pdf(SimpleNamespace(html=str(main_hardlink), pdf=str(run / 'hard-main.pdf')))
        assert False, 'HTML 하드링크 초기 거부 누락'
    except module.SafeInputError:
        pass
finally:
    main_hardlink.unlink()
linked_main = html.parent / 'file-alias.html'
other_html = workspace_dir / '원본/other.html'
other_html.write_text('elsewhere in workspace', encoding='utf-8')
try:
    linked_main.symlink_to(other_html)
except OSError:
    print('SKIP Mac PDF 파일 symlink 초기 경계: 이 Windows 사용자 파일 symlink 권한 없음')
else:
    try:
        try:
            module.pdf(SimpleNamespace(html=str(linked_main), pdf=str(run / 'linked-main.pdf')))
            assert False, '서버 루트 밖 HTML 파일 symlink 초기 거부 누락'
        except module.SafeInputError:
            pass
    finally:
        linked_main.unlink()
print('PASS Mac PDF 입력 위치: 작업실 없음 종료2·보호 내부·보호 폴더 품는 루트 거부')
print('PASS Mac pdf: 브라우저 없는 경우 종료 2 (Mac 실제 렌더는 현장 필요)')

# 정규식 HTML 검사를 제거했으므로 서버가 파일 제공 경계를 직접 검사합니다.
import http.client
import time
server_script = engine.with_name('pdf_server.py')
server_spec = importlib.util.spec_from_file_location('pdf_server', server_script)
server_module = importlib.util.module_from_spec(server_spec)
server_spec.loader.exec_module(server_module)
# Python fcntl accepts at most 1024 bytes; Darwin MAXPATHLEN is 1024.
from pathlib import PurePosixPath
for consumer in (module, server_module):
    handle_calls = []
    def fake_f_getpath(fd, operation, buffer):
        handle_calls.append((fd, operation, len(buffer)))
        assert operation == 50 and len(buffer) == 1024
        return b'/Users/owner/work/file.txt\0IGNORED_PADDING'
    with patch.object(consumer.os, 'name', 'posix'), patch.object(consumer.sys, 'platform', 'darwin'), \
            patch.object(consumer, 'Path', PurePosixPath), \
            patch.dict(sys.modules, {'fcntl': SimpleNamespace(fcntl=fake_f_getpath)}):
        assert str(consumer.opened_file_path(SimpleNamespace(fileno=lambda: 7))) == '/Users/owner/work/file.txt'
    assert handle_calls == [(7, 50, 1024)]
print('PASS Mac F_GETPATH: 두 소비자 cmd50·1024버퍼·NUL 종료 파싱')
assets = html.parent / 'assets'
assets.mkdir()
logo = assets / '학원 로고.png'
logo.write_bytes(b'FAKE_LOGO')
(run / '.hidden.html').write_text('secret', encoding='utf-8')
(run / 'private.txt').write_text('secret', encoding='utf-8')
server_token = 'a' * 32
server_root = run / 'serve-root'
server_root.mkdir()
(server_root / 'visible.html').write_text('visible', encoding='utf-8')
(server_root / '.hidden.html').write_text('hidden', encoding='utf-8')
(server_root / 'private.txt').write_text('private', encoding='utf-8')
secret_folder = run / 'outside-server'
secret_folder.mkdir()
(secret_folder / 'secret.png').write_bytes(b'SECRET_OUTSIDE')
server_race = server_root / 'open-race'
server_race.mkdir()
server_race_file = server_race / 'secret.png'
server_race_file.write_bytes(b'ALLOWED_BEFORE_SWAP')
server_swapped = []
def swap_resource_before_open(path, *args, **kwargs):
    if path == server_race_file and not server_swapped:
        server_race.rename(server_race.with_name('open-race-original'))
        if os.name == 'nt':
            made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(server_race), str(secret_folder)], capture_output=True)
            assert made.returncode == 0, made.stderr
        else:
            server_race.symlink_to(secret_folder, target_is_directory=True)
        server_swapped.append(True)
    return original_open(path, *args, **kwargs)
with patch.object(Path, 'open', swap_resource_before_open):
    assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/open-race/secret.png', server_token) is None
assert server_swapped
assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/visible.html', server_token)[1] == b'visible'
print('PASS Mac PDF 열린 핸들: 검증 직후 junction/symlink 외부 교체 시 내용 미반환')
hard_resource = server_root / 'hard.html'
os.link(server_root / 'visible.html', hard_resource)
try:
    assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/visible.html', server_token) is None
    assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/hard.html', server_token) is None
finally:
    hard_resource.unlink()
assert server_module.read_resource(server_root.resolve(), '/visible.html', server_token) is None
assert server_module.read_resource(server_root.resolve(), '/' + 'b' * 32 + '/visible.html', server_token) is None
assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/visible.html:secret', server_token) is None
print('PASS Mac PDF 서버: 열린 핸들 하드링크·누락/틀린 난수 토큰·ADS 거부')
server_alias = server_root / 'alias'
if os.name == 'nt':
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(server_alias), str(secret_folder)], capture_output=True)
    assert made.returncode == 0, made.stderr
else:
    server_alias.symlink_to(secret_folder, target_is_directory=True)
attribute_server_dir = server_root / 'attribute-hidden'
attribute_server_dir.mkdir()
(attribute_server_dir / 'visible.png').write_bytes(b'HIDDEN_PARENT')
if os.name == 'nt':
    assert ctypes.windll.kernel32.SetFileAttributesW(str(attribute_server_dir), 2)
    try:
        assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/attribute-hidden/visible.png', server_token) is None
    finally:
        assert ctypes.windll.kernel32.SetFileAttributesW(str(attribute_server_dir), 0x80)
elif sys.platform == 'darwin':
    os.chflags(attribute_server_dir, stat.UF_HIDDEN)
    try:
        assert server_module.read_resource(server_root.resolve(), '/' + server_token + '/attribute-hidden/visible.png', server_token) is None
    finally:
        os.chflags(attribute_server_dir, 0)
# Mac UF_HIDDEN is checked independently of dot names and Windows attributes.
real_stat = Path.stat
def mac_hidden_info(path, *args, **kwargs):
    info = real_stat(path, *args, **kwargs)
    if path == attribute_server_dir:
        return SimpleNamespace(st_flags=0x8000, st_file_attributes=0)
    return info
with patch.object(Path, 'stat', mac_hidden_info):
    assert server_module.hidden_path(attribute_server_dir / 'visible.png', server_root.resolve())
    assert module.hidden_path(attribute_server_dir / 'visible.png', server_root.resolve())
print('PASS Mac PDF/Codex 숨김 검사: 상위 폴더 OS 속성·UF_HIDDEN 비점 이름 거부')
state = run / 'server-state'
state.mkdir()
audit = state / 'audit.jsonl'
server_env = dict(os.environ, EK_PDF_ROOT=str(server_root), EK_PDF_STATE_DIR=str(state), EK_PDF_AUDIT_LOG=str(audit), EK_PDF_TOKEN=server_token)
server = subprocess.Popen([sys.executable, '-B', str(server_script)], env=server_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.monotonic() + 10
    while not (state / 'port.txt').exists():
        assert server.poll() is None and time.monotonic() < deadline
        time.sleep(.02)
    port = int((state / 'port.txt').read_text(encoding='ascii'))
    for path in ('/../outside-server/secret.png', '/%2e%2e/outside-server/secret.png',
                 '/folder\\secret.png', '//outside-server/secret.png', '/C:/secret.png',
                 '/alias/secret.png', '/.hidden.html', '/private.txt'):
        client = http.client.HTTPConnection('127.0.0.1', port)
        client.request('GET', '/' + server_token + path)
        response = client.getresponse()
        assert response.status == 404, (path, response.status)
        assert b'SECRET_OUTSIDE' not in response.read()
        client.close()
    for path in ('/visible.html', '/' + 'b' * 32 + '/visible.html', '/' + server_token + '/visible.html%3Asecret'):
        client = http.client.HTTPConnection('127.0.0.1', port)
        client.request('GET', path)
        response = client.getresponse()
        assert response.status == 404
        response.read()
        client.close()
    client = http.client.HTTPConnection('127.0.0.1', port)
    client.request('POST', '/' + server_token + '/visible.html')
    assert client.getresponse().status == 404
    client.close()
    client = http.client.HTTPConnection('127.0.0.1', port)
    client.request('GET', '/' + server_token + '/visible.html')
    response = client.getresponse()
    assert response.status == 200 and response.read() == b'visible'
    assert response.getheader('Content-Security-Policy') == server_module.CSP
    client.close()
finally:
    server.terminate()
    server.wait(timeout=10)
rows = [json.loads(row) for row in audit.read_text(encoding='utf-8').splitlines()]
assert all(row['path'] is None for row in rows if row['status'] == 404)
assert sum(row['status'] == 200 for row in rows) == 1
print('PASS Mac PDF 서버: traversal·percent·역슬래시·절대 경로·junction·숨김·확장자·GET 한정 404, 루트 파일만 제공')

html.write_text('<link rel="stylesheet" href="assets/style.css"><img src="assets/학원 로고.png">', encoding='utf-8')
browser_calls = []
def fake_browser(args, **kwargs):
    browser_calls.append((args, kwargs))
    from urllib.request import urlopen
    assert urlopen(args[-1]).read() == html.read_bytes()
    target = next(value.split('=', 1)[1] for value in args if value.startswith('--print-to-pdf='))
    Path(target).write_bytes(b'%PDF-1.4\n/Type /Page\n/Type /Page\n')
    return SimpleNamespace(returncode=0)
with patch.dict(os.environ, {'EK_PDF_BROWSER': str(engine)}), patch.object(module.subprocess, 'run', fake_browser):
    assert module.pdf(SimpleNamespace(html=str(html), pdf=str(run / 'relative-logo.pdf'))) == 0
flags = browser_calls[0][0]
assert all(flag in flags for flag in ('--proxy-server=127.0.0.1:9',
                                     '--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1',
                                     '--disable-background-networking', '--disable-extensions'))
from urllib.parse import urlsplit
render_url = urlsplit(flags[-1])
assert '--proxy-bypass-list=<-loopback>;127.0.0.1:' + str(render_url.port) in flags
assert re.fullmatch('[0-9a-f]{32}', render_url.path.split('/')[1])
assert flags[-1].startswith('http://127.0.0.1:') and '--no-pdf-header-footer' in flags
assert browser_calls[0][1]['timeout'] == 120
print('PASS Mac PDF: 별도 HTTP 프로세스·난수 토큰·포트 한정 루프백 bypass·CSP·서버 종료 (실제 Mac 렌더는 현장 필요)')

# /tmp -> /private/tmp처럼 홈 위의 상위 경로 전체를 연결합니다.
# Windows에서는 관리자 권한이 필요 없는 junction으로 같은 차이를 만듭니다.
ancestor = run / 'ancestor-alias'
if os.name == 'nt':
    made = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(ancestor), str(work_home.resolve())], capture_output=True)
    assert made.returncode == 0, made.stderr
else:
    ancestor.symlink_to(work_home.resolve(), target_is_directory=True)
aliased_workspace = ancestor / 'AI작업실'
assert aliased_workspace != workspace_dir.resolve()
assert aliased_workspace.resolve() == workspace_dir.resolve()
alias_profile = ancestor / 'alias-profile.json'
alias_profile.write_text(json.dumps({'studentDataPaths': [str(ancestor / 'student')],
                                      'workflow': {'code': 'A'}}), encoding='utf-8')
for action in ('apply-safety', 'apply-statusline', 'apply-workspace'):
    result = invoke(action, '--home', ancestor, '--profile', alias_profile, '--apply')
    assert result.returncode == 0, (action, result.stderr)
alias_rules = json.loads((ancestor / '.claude/settings.json').read_bytes())['permissions']['deny']
assert any(str(student.resolve()).replace('\\', '/') in rule.replace('\\', '/') for rule in alias_rules)
alias_review = SimpleNamespace(workspace=str(aliased_workspace), brief=str(aliased_workspace / '검토/brief.md'),
                               out=str(aliased_workspace / '검토/alias-result.md'),
                               target=[str(aliased_workspace / '결과/검토 초안.md')])
with patch.object(module.shutil, 'which', return_value='fake-codex'), patch.object(module.subprocess, 'run', fake_codex):
    assert module.codex_review(alias_review) == 0
alias_staged = Path(calls[-1][0][calls[-1][0].index('-o') + 1])
assert alias_staged.parent.parent != Path(alias_review.brief).parent
assert alias_staged.parent.parent.resolve() == Path(alias_review.brief).parent.resolve()
assert alias_staged.parent.name.startswith('.ek-review-') and not alias_staged.parent.exists()
assert calls[-1][1]['input'] == options['input']
for bad in (ancestor / 'student/private.md', aliased_workspace / '결과/student-alias/private.md'):
    with patch.object(module.subprocess, 'run', side_effect=AssertionError('Codex 호출 금지')):
        try:
            module.codex_review(SimpleNamespace(**dict(vars(alias_review), target=[str(bad)],
                                                       out=str(aliased_workspace / '검토/alias-blocked.md'))))
            assert False, str(bad)
        except module.SafeInputError:
            pass
with patch.dict(os.environ, {'EK_PDF_BROWSER': str(engine)}), patch.object(module.subprocess, 'run', fake_browser):
    assert module.pdf(SimpleNamespace(html=str(aliased_workspace / '결과' / html.name),
                                     pdf=str(ancestor / 'alias-render.pdf'))) == 0
(student / 'private.html').write_text('SECRET_HTML', encoding='utf-8')
with patch.object(module.subprocess, 'run', side_effect=AssertionError('브라우저 호출 금지')):
    try:
        module.pdf(SimpleNamespace(html=str(aliased_workspace / '결과/student-alias/private.html'),
                                   pdf=str(ancestor / 'alias-blocked.pdf')))
        assert False, '상위 연결 경로에서 보호 HTML 허용'
    except module.SafeInputError:
        pass
with patch.object(module, 'security_software', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
    module.diag(SimpleNamespace(home=ancestor, output=None))
assert (work_home / 'ek-diag.txt').is_file()
print('PASS Mac 상위 경로 별칭: junction/symlink 홈 설정·학생 deny·작업실·Codex·PDF 허용/보호 거부·진단')

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
