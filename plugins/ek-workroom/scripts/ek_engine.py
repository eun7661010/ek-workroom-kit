"""Mac 실행기: 표준 라이브러리만 사용. Python이 없으면 셸이 안내 후 중단한다."""
import argparse
import copy
import datetime
import json
import ipaddress
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile


def safe_path(path):
    for candidate in [path, *path.parents]:
        if candidate.is_symlink():
            raise ValueError('연결 경로에는 쓰지 않습니다.')


def obj(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('JSON 객체가 필요합니다.')
    return value


def command(args, timeout=6):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, ''


def backup(path):
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    dest = path.with_name(path.name + '.ek-backup-' + stamp)
    with dest.open('xb') as f:
        f.write(path.read_bytes())


def save(path, data):
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    if path.exists():
        backup(path)
    fd, temporary = tempfile.mkstemp(prefix='.ek-write-', dir=path.parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    os.replace(temporary, path)


def settings(a):
    path = a.home / '.claude/settings.json'
    safe_path(path)
    value = obj(path) if path.exists() else {}
    before = copy.deepcopy(value)
    profile = obj(Path(a.profile))
    paths = profile.get('studentDataPaths')
    if not isinstance(paths, list) or not paths:
        raise ValueError('studentDataPaths 배열에 폴더 1개 이상이 필요합니다.')
    extra = None
    if a.action == 'apply-safety':
        perm = value.setdefault('permissions', {})
        if not isinstance(perm, dict):
            raise ValueError('permissions 객체가 필요합니다.')
        rules = []
        for folder in paths:
            if (not isinstance(folder, str) or not folder.startswith('/') or
                    folder.startswith('//') or re.search(r'[\r\n*?\[\]{}!]', folder) or
                    '..' in Path(folder).parts):
                raise ValueError('와일드카드 없는 로컬 절대 경로가 필요합니다.')
            anchor = '/' + folder.rstrip('/')
            for tool in ('Read', 'Edit'):
                rules.extend([f'{tool}({anchor})', f'{tool}({anchor}/**)'])
        for key, additions in [('deny', rules), ('ask', ['Bash', 'PowerShell', 'WebFetch', 'WebSearch', 'mcp__*'])]:
            old = perm.get(key, [])
            if not isinstance(old, list) or any(not isinstance(x, str) for x in old):
                raise ValueError('권한 목록은 문자열 배열이어야 합니다.')
            perm[key] = list(dict.fromkeys(old + additions))
        perm['defaultMode'] = 'default'
        perm['disableBypassPermissionsMode'] = 'disable'
    else:
        label = profile.get('accountLabel')
        if label not in ('업무용', '개인용'):
            raise ValueError('계정 별칭을 확인하세요.')
        dest = a.home / '.claude/ek-workroom/ek_engine.py'
        safe_path(dest)
        text = str(dest)
        if re.search(r'[\r\n"$`]', text):
            raise ValueError('홈 경로의 특수문자를 확인하세요.')
        line = value.setdefault('statusLine', {})
        if not isinstance(line, dict):
            raise ValueError('statusLine 객체가 필요합니다.')
        # 현재 확인한 Python 경로를 고정합니다. Node 설치는 필요 없습니다.
        python = sys.executable
        if re.search(r'[\r\n"$`]', python):
            raise ValueError('실행기 경로를 확인하세요.')
        line.update(type='command', command=f'"{python}" "{text}" statusline --account-label {"work" if label == "업무용" else "personal"}')
        extra = (dest, Path(__file__).read_bytes())
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if not a.apply or a.dry_run:
        print('미리보기(DryRun): 저장하지 않습니다. 승인 후 같은 명령에 --apply를 붙이세요.')
        print(encoded.decode('utf-8'))
        if extra:
            print('상태줄 실행기 1개를 고객 홈의 .claude/ek-workroom에 복사할 예정입니다.')
    else:
        if extra:
            save(*extra)
        if value != before or not path.exists():
            save(path, encoded)
            print('설정을 저장했습니다. 기존 파일이 있으면 수정 전 백업도 남겼습니다.')
        else:
            print('이미 같은 설정입니다. 변경과 새 백업이 없습니다.')
    print('학생 폴더 차단은 도구 규칙입니다. 셸에서 간접 읽기는 승인 시 거절하세요. 계정 별칭은 /status에서 확인하세요.')


def diag(a):
    lines = ['보내기 전에 직접 읽어 보세요', 'AI 작업실 진단: 파일 내용·폴더 목록·계정 정보는 수집하지 않습니다.',
             '사용자 <USER> / 컴퓨터 <COMPUTER> / 홈 <HOME>',
             'OS: ' + platform.system() + ' ' + platform.release()]
    for name in ('claude', 'codex', 'git', 'node', 'python', 'winget', 'pwsh'):
        code, output = command([name, '--version'])
        match = re.search(r'(?<![\d.])\d+(?:\.\d+){1,4}(?![\d.])', output)
        lines.append(name + ': ' + (match.group() if match else ('없음' if code is None else '버전 확인 불가')))
    lines += ['PATH 항목 수: ' + str(len([x for x in os.environ.get('PATH', '').split(os.pathsep) if x])),
              '디스크 여유 GB: ' + str(round(shutil.disk_usage(a.home).free / 1024**3, 1)),
              '실행 정책: Mac 해당 없음']
    known = []
    for label, process in [('Defender', 'wdavdaemon'), ('AhnLab', 'AhnLab'), ('CrowdStrike', 'falcond')]:
        if command(['pgrep', '-x', process])[0] == 0:
            known.append(label)
    lines.append('보안 SW: ' + (', '.join(known) if known else '확인 불가 (등록한 제품만 검사)'))
    for host in ('claude.ai', 'chatgpt.com'):
        code, _ = command(['curl', '--head', '--silent', '--max-time', '4', 'https://' + host])
        lines.append(host + ': ' + ('도달함' if code == 0 else '확인 불가'))
    result = '\n'.join(lines)
    for raw, token in [(str(a.home), '<HOME>'), (str(Path.home()), '<HOME>'),
                       (os.environ.get('USER'), '<USER>'), (platform.node(), '<COMPUTER>')]:
        if raw and len(raw) > 2:
            result = re.sub(re.escape(raw), lambda _: token, result, flags=re.I)
    result = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<EMAIL>', result)
    result = re.sub(r'01[016789][- ]?\d{3,4}[- ]?\d{4}', '<PHONE>', result)
    def hide_ip(match):
        try:
            ipaddress.ip_address(match.group())
            return '<IP>'
        except ValueError:
            return match.group()
    result = re.sub(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', hide_ip, result)
    output = Path(a.output) if a.output else a.home / 'ek-diag.txt'
    if not output.is_absolute():
        output = Path.cwd() / output
    if not output.resolve().is_relative_to(a.home.resolve()):
        raise ValueError('진단 저장은 지정한 홈 안에서만 가능합니다.')
    safe_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result + '\n', encoding='utf-8')
    print(result)


def end_check(a):
    print('종료 점검 (읽기 전용): 서비스·프로그램을 변경하지 않습니다.')
    found, unknown = False, False
    code, ssh = command(['/usr/sbin/systemsetup', '-getremotelogin'])
    if code == 0 and re.search(r'Remote Login: (On|Off)', ssh):
        on = 'Remote Login: On' in ssh
        found |= on
        print('OpenSSH 서버: ' + ('켜짐' if on else '꺼짐'))
    else:
        unknown = True
        print('OpenSSH 서버: 확인 불가. 시스템 설정 > 일반 > 공유에서 원격 로그인을 확인하세요.')
    if shutil.which('tailscale'):
        code, raw = command(['tailscale', 'status', '--json'])
        try:
            state = json.loads(raw).get('BackendState')
            if code != 0 or state not in ('Running', 'Stopped', 'NeedsLogin', 'NoState'):
                raise ValueError()
            found |= state == 'Running'
            print('Tailscale: ' + ('연결 켜짐' if state == 'Running' else '연결 꺼짐'))
        except (ValueError, TypeError):
            print('Tailscale: 확인 불가')
            unknown = True
    else:
        print('Tailscale: 명령 없음 (프로세스 별도 확인)')
    for label, pattern in [('Tailscale', 'tailscaled|Tailscale'), ('AnyDesk', 'AnyDesk|anydesk'),
                           ('TeamViewer', 'TeamViewer'), ('RustDesk', 'RustDesk|rustdesk'),
                           ('Chrome 원격 데스크톱', 'remoting_host')]:
        code, _ = command(['pgrep', '-f', pattern])
        on = code == 0
        found |= on
        unknown |= code not in (0, 1)
        print(label + ': ' + ('실행 중' if on else ('실행 흔적 없음' if code == 1 else '확인 불가')))
    code, jobs = command(['launchctl', 'list'])
    if code == 0:
        count = sum('EK-Workroom-' in row for row in jobs.splitlines())
        found |= count > 0
        print('이번 세션 예약 작업(EK-Workroom-*): ' + str(count) + '개 / 키트는 예약 작업을 만들지 않습니다.')
    else:
        unknown = True
        print('이번 세션 예약 작업: 확인 불가')
    print('남은 원격 접속 있음' if found else ('남은 원격 접속 여부 확인 불가' if unknown else '남은 원격 접속 없음 (점검한 구성요소 기준)'))
    print('Zoom 공유 중지·원격 제어 해제·브라우저 지원 종료는 원장님이 화면에서 확인하세요. 이 검사만으로 접속 부재가 보장되지는 않습니다.')


def main():
    parser = argparse.ArgumentParser(description='AI 작업실: 기본은 미리보기')
    parser.add_argument('action', choices=['apply-safety', 'apply-statusline', 'ek-diag', 'ek-end-check', 'statusline'])
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--profile')
    parser.add_argument('--output')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--account-label', choices=['work', 'personal'], default='work')
    a = parser.parse_args()
    if not a.home.is_absolute():
        raise ValueError('홈 경로는 절대 경로로 입력하세요.')
    if a.action.startswith('apply-'):
        settings(a)
    elif a.action == 'ek-diag':
        diag(a)
    elif a.action == 'ek-end-check':
        end_check(a)
    else:
        session = json.load(sys.stdin)
        model = session.get('model', {}).get('display_name', '확인 필요')
        folder = Path(session.get('workspace', {}).get('current_dir') or session.get('cwd', '')).name
        clean = lambda x: re.sub(r'[\x00-\x1f\x7f]', '', str(x))
        print(f'모델 {clean(model)} | 폴더 {clean(folder)} | 계정 별칭 {"업무용" if a.account_label == "work" else "개인용"} (/status 확인)')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('실패: 프로필·기존 JSON·경로·필수 도구를 확인하세요. 상세 원문은 공유하지 마세요.', file=sys.stderr)
        sys.exit(1)
