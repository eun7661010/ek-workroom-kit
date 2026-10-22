"""Codex 제한 시간과 실제 자식 프로세스 종료. 모든 파일은 .tmp 가짜 홈에 둡니다."""
import contextlib
import ctypes
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from compat_support import write_text

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]).resolve() / 'codex-timeout'
assert run.is_relative_to(root / '.tmp')
run.mkdir(parents=True)
scripts = root / 'plugins/ek-workroom/scripts'
spec = importlib.util.spec_from_file_location('timeout_engine', scripts / 'ek_engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
message = 'Codex 검토가 10분 안에 끝나지 않아 멈췄습니다. 새 터미널에서 codex --version과 로그인을 확인하세요.'

# 같은 입력 표를 두 구현에 적용합니다. 공백·부호·소수·범위 밖은 기본 600초입니다.
cases = [('', 600), ('1', 1), ('2', 2), ('599', 599), ('600', 600), ('601', 600),
         ('0', 600), ('-1', 600), ('2.5', 600), ('abc', 600), (' 2', 600),
         ('2 ', 600), ('+2', 600), ('2\n', 600), ('9999999999999999999999', 600)]
with patch.dict(os.environ):
    os.environ.pop('EK_CODEX_REVIEW_TIMEOUT', None)
    assert engine.codex_review_timeout() == 600
    for value, expected in cases:
        os.environ['EK_CODEX_REVIEW_TIMEOUT'] = value
        assert engine.codex_review_timeout() == expected, value

ps = None
if os.name == 'nt':
    ps = [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
          '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass']
    table = run / 'timeout-cases.json'
    table.write_text(json.dumps(cases), encoding='utf-8')
    checker = run / 'check-timeouts.ps1'
    write_text(checker, '''param($Common, $Cases)
. $Common
Remove-Item Env:EK_CODEX_REVIEW_TIMEOUT -ErrorAction SilentlyContinue
if ((Get-EkCodexReviewTimeout) -ne 600) { throw 'missing timeout' }
foreach ($case in (Get-Content -LiteralPath $Cases -Raw | ConvertFrom-Json)) {
    $env:EK_CODEX_REVIEW_TIMEOUT = $case[0]
    if ((Get-EkCodexReviewTimeout) -ne $case[1]) { throw 'invalid timeout parsing' }
}
''', encoding='utf-8-sig')
    parsed = subprocess.run(ps + ['-File', str(checker), str(scripts / 'common.ps1'), str(table)],
                            capture_output=True, timeout=20)
    assert parsed.returncode == 0, parsed.stderr
print('PASS Codex timeout: 기본 600초·1~600 정수·잘못된 값/상한 초과 600초')

# Windows에서도 POSIX Popen/killpg 계약과 프로세스가 이미 끝난 경합을 검사합니다.
for gone in (False, True):
    process = Mock(pid=12345)
    process.communicate.side_effect = subprocess.TimeoutExpired('fake-codex', 2)
    with patch.dict(os.environ, EK_CODEX_REVIEW_TIMEOUT='2'), \
            patch.object(engine.os, 'name', 'posix'), \
            patch.object(engine.signal, 'SIGKILL', 9, create=True), \
            patch.object(engine.subprocess, 'Popen', return_value=process) as popen, \
            patch.object(engine.os, 'killpg', create=True,
                         side_effect=ProcessLookupError if gone else None) as killpg:
        try:
            engine.run_codex(['fake-codex'], input=b'prompt')
            raise AssertionError('timeout missing')
        except subprocess.TimeoutExpired:
            pass
        assert popen.call_args.kwargs['start_new_session'] is True
        process.communicate.assert_called_once_with(b'prompt', timeout=2)
        killpg.assert_called_once_with(12345, signal.SIGKILL if hasattr(signal, 'SIGKILL') else 9)
        assert process.kill.call_count == int(gone)
        process.wait.assert_called_once_with()
print('PASS Mac timeout: 별도 세션·2초 communicate·killpg(SIGKILL)·종료 경합 회수')

home = run / 'home'
workspace = home / 'workspace'
review = workspace / '검토'
review.mkdir(parents=True)
student = home / 'student'
student.mkdir()
metadata = workspace / '.ek-workroom/protected-paths.json'
metadata.parent.mkdir()
metadata.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(student)]}), encoding='utf-8')
brief = review / 'brief.md'
brief.write_text('더미 초안만 검토', encoding='utf-8')
target = workspace / 'draft.md'
target.write_text('합성 문서', encoding='utf-8')
with patch.object(engine.shutil, 'which', return_value='fake-codex'), \
        patch.object(engine, 'run_codex', return_value=SimpleNamespace(returncode=7)):
    assert engine.codex_review(SimpleNamespace(workspace=str(workspace), brief=str(brief),
                               target=[str(target)], out=str(review / 'exit7.md'))) == 7
assert not (review / 'exit7.md').exists() and not list(review.glob('.ek-review-*'))
print('PASS Mac Codex: 종료 코드 7 전달·결과 미생성·임시 폴더 정리')
fakebin = run / 'bin'
fakebin.mkdir()
fake = fakebin / 'codex'
write_text(fake, '''#!/usr/bin/env python3
import os, subprocess, sys, time
from pathlib import Path
role = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith('--') else '--parent'
Path(os.environ['EK_TIMEOUT_PIDS'], role[2:] + '.pid').write_text(str(os.getpid()))
if role != '--grandchild':
    subprocess.Popen([sys.executable, __file__, '--child' if role == '--parent' else '--grandchild'])
if role == '--parent':
    sys.stdin.buffer.read()
time.sleep(90)
''', encoding='utf-8', newline='\n')
fake.chmod(0o755)


def alive(pid):
    if os.name == 'nt':
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Linux CI에서 init이 아직 회수하지 않은 zombie는 실행 중인 프로세스가 아닙니다.
    stat = Path('/proc') / str(pid) / 'stat'
    return not (stat.exists() and stat.read_text().split(') ', 1)[1].startswith('Z'))


def check_tree(label, invoke):
    pids = run / label
    pids.mkdir()
    try:
        started = time.monotonic()
        result, output = invoke(pids)
        elapsed = time.monotonic() - started
        assert result == 1 and message in output, (result, output)
        assert 2 <= elapsed < 15, elapsed
        records = list(pids.glob('*.pid'))
        assert len(records) == 3, records
        ids = [int(path.read_text()) for path in records]
        deadline = time.monotonic() + 3
        while any(alive(pid) for pid in ids) and time.monotonic() < deadline:
            time.sleep(.05)
        assert not any(alive(pid) for pid in ids), ids
        assert not (review / (label + '.md')).exists()
        assert not list(review.glob('.ek-review-*'))
        print('PASS {}: 제한 2초·종료 1·안내 일치·부모/자식/손자 PID 종료 ({:.2f}초)'.format(label, elapsed))
    finally:
        # 실패해도 이번 테스트가 직접 만든 PID만 정리합니다.
        for path in pids.glob('*.pid'):
            pid = int(path.read_text())
            if alive(pid):
                if os.name == 'nt':
                    subprocess.run(['taskkill.exe', '/T', '/F', '/PID', str(pid)], capture_output=True, timeout=10)
                else:
                    os.kill(pid, signal.SIGKILL)


original_popen = subprocess.Popen


def python_stub(arguments, **kwargs):
    # Windows는 shebang을 실행하지 않으므로 가짜 실행 파일 앞에 Python만 붙입니다.
    if os.name == 'nt' and arguments[0] == str(fake):
        arguments = [sys.executable] + arguments
    return original_popen(arguments, **kwargs)


def invoke_engine(pids):
    output = io.StringIO()
    with patch.dict(os.environ, EK_CODEX_REVIEW_TIMEOUT='2', EK_TIMEOUT_PIDS=str(pids)), \
            patch.object(engine.shutil, 'which', return_value=str(fake)), \
            patch.object(engine.subprocess, 'Popen', python_stub), contextlib.redirect_stdout(output):
        result = engine.codex_review(SimpleNamespace(workspace=str(workspace), brief=str(brief),
                                     target=[str(target)], out=str(review / 'engine.md')))
    return result, output.getvalue()


check_tree('engine', invoke_engine)
if ps:
    (fakebin / 'codex.cmd').write_text('@"' + sys.executable + '" "%~dp0codex" %*\r\n', encoding='utf-8')

    def invoke_windows(pids):
        env = dict(os.environ, EK_CODEX_REVIEW_TIMEOUT='2', EK_TIMEOUT_PIDS=str(pids),
                   PATH=str(fakebin) + os.pathsep + os.environ['PATH'])
        for key in ('HOME', 'USERPROFILE', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'TEMP', 'TMP'):
            folder = home / key.lower()
            folder.mkdir(exist_ok=True)
            env[key] = str(folder)
        result = subprocess.run(ps + ['-File', str(scripts / 'ek-codex-review.ps1'),
                                '-Workspace', str(workspace), '-Brief', str(brief),
                                '-Target', str(target), '-Out', str(review / 'windows.md')],
                                env=env, capture_output=True, timeout=20)
        return result.returncode, result.stdout.decode('utf-8-sig')

    check_tree('windows', invoke_windows)
