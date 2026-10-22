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
        profile = home / 'profile.json'
        profile.write_text(json.dumps({'studentDataPaths': ['/private/StudentRecords'], 'accountLabel': '업무용'}, ensure_ascii=False), encoding='utf-8')
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
            assert 'Read(//private/StudentRecords/**)' in value['permissions']['deny']
            assert 'Edit(//private/StudentRecords/**)' in value['permissions']['deny']
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
empty_profile.write_text(json.dumps({'studentDataPaths': [], 'accountLabel': '업무용'}), encoding='utf-8')
empty = subprocess.run([sys.executable, str(engine), 'apply-safety', '--home', str(home), '--profile', str(empty_profile)], capture_output=True)
assert empty.returncode != 0 and not (home / '.claude/settings.json').exists()
module.command = lambda *a, **kw: (0, '10.20.30.40')
module.diag(SimpleNamespace(home=home, output=None))
assert '10.20.30.40' not in (home / 'ek-diag.txt').read_text(encoding='utf-8')
print('Mac 엔진 검사 통과 (Mac OS 현장 실행은 별도 필요)')
