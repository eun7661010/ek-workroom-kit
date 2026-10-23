"""Windows findings regressions; synthetic inputs and subprocesses in .tmp only."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]).resolve() / 'windows-findings'
assert run.is_relative_to(root / '.tmp')
run.mkdir(parents=True)
scripts = root / 'plugins/ek-workroom/scripts'
ps = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass']
env = dict(os.environ)
for key in ('USERPROFILE', 'HOME', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'TEMP', 'TMP'):
    folder = run / key.lower()
    folder.mkdir(exist_ok=True)
    env[key] = str(folder)

def quote(path):
    return "'" + str(path).replace("'", "''") + "'"

for state in ('Stopped', 'Running'):
    fixture = run / ('end-' + state + '.ps1')
    fixture.write_text('''
function Get-Service { param($Name, $ErrorAction)
    if ($Name -eq 'sshd') { [pscustomobject]@{Status='%s'} }
}
function Get-Command { param($Name, $CommandType, $ErrorAction) }
function Get-Process { param($ErrorAction) }
function Get-ScheduledTask { param($ErrorAction) }
. %s
''' % (state, quote(scripts / 'ek-end-check.ps1')), encoding='utf-8-sig')
    result = subprocess.run(ps + ['-File', str(fixture)], env=env, capture_output=True, timeout=20)
    output = result.stdout.decode('utf-8-sig')
    assert result.returncode == 0, result.stderr
    if state == 'Stopped':
        assert 'OpenSSH 서버: 설치됨(꺼짐)' in output and '남은 원격 접속 없음' in output, output
    else:
        assert 'OpenSSH 서버: 실행 중' in output and '남은 원격 접속 있음' in output, output
    print('PASS OpenSSH ' + state + ': 설치와 실행 구분')

failed_cli = run / 'tailscale.cmd'
failed_cli.write_bytes(b'@exit /b 1\r\n')
for state in ('Stopped', 'Running'):
    fixture = run / ('tailscale-' + state + '.ps1')
    fixture.write_text('''
function Get-Service { param($Name, $ErrorAction)
    if ($Name -eq 'Tailscale') { [pscustomobject]@{Status='%s'} }
}
function Get-Command { param($Name, $CommandType, $ErrorAction)
    if ($Name -eq 'tailscale') { [pscustomobject]@{Source=%s} }
}
function Get-Process { param($ErrorAction) }
function Get-ScheduledTask { param($ErrorAction) }
. %s
''' % (state, quote(failed_cli), quote(scripts / 'ek-end-check.ps1')), encoding='utf-8-sig')
    result = subprocess.run(ps + ['-File', str(fixture)], env=env, capture_output=True, timeout=20)
    output = result.stdout.decode('utf-8-sig')
    assert result.returncode == 0 and '실제 접속 상태 확인 불가' in output, output
    assert ('Tailscale 서비스: 설치됨(꺼짐)' if state == 'Stopped'
            else 'Tailscale 서비스: 실행 중') in output, output
    if state == 'Running':
        assert '남은 원격 접속 있음' in output, output
    print('PASS Tailscale CLI 실패에도 서비스 ' + state + ' 별도 검사')

fixture = run / 'encoding.ps1'
fixture.write_text("[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(949)\n. "
                   + quote(scripts / 'common.ps1') + "\nWrite-Output '한글 출력 확인'\n", encoding='utf-8-sig')
result = subprocess.run(ps + ['-File', str(fixture)], env=env, capture_output=True, timeout=20)
assert result.returncode == 0 and result.stdout.decode('utf-8-sig').strip() == '한글 출력 확인'
print('PASS CP949 부모에서도 외부 프로그램에 UTF-8 한글 출력')
