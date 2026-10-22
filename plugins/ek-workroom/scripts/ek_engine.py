"""Mac 실행기: Python 3.9 이상, 표준 라이브러리만 사용."""
import argparse
import copy
import datetime
import json
import math
import ipaddress
import os
import signal
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import time
from urllib.parse import quote
import zipfile
import xml.etree.ElementTree as ET


class SafeInputError(ValueError):
    """정해진 검증 문구만 공유합니다. 시스템 예외에는 사용하지 않습니다."""


def safe_path(path, home):
    home = Path(home).absolute()
    path = Path(path).absolute()
    if not path.is_relative_to(home):
        raise SafeInputError('저장은 지정한 홈 안에서만 가능합니다.')
    # /var, /tmp 같은 상위 시스템 별칭은 허용합니다. 홈 아래 연결은
    # 최종 경로가 같은 홈 안에 남는 경우에만 허용합니다.
    if not path.resolve().is_relative_to(home.resolve()):
        raise SafeInputError('홈 밖으로 연결된 저장 경로에는 쓰지 않습니다.')


def student_paths(folder, home):
    if not isinstance(folder, str):
        raise SafeInputError('학생 폴더 경로는 문자열이어야 합니다.')
    folder = folder.strip()
    entered = Path(folder)
    if (not entered.is_absolute() or folder.startswith('//') or
            re.search(r'[\r\n*?\[\]{}!]', folder) or '..' in entered.parts):
        raise SafeInputError('와일드카드 없는 로컬 절대 경로가 필요합니다.')
    if entered == Path(entered.anchor) or same_location(entered.resolve(), Path(home).resolve()):
        raise SafeInputError('드라이브 루트나 홈 전체는 학생 폴더로 지정할 수 없습니다.')
    if not entered.is_dir():
        raise SafeInputError('학생정보 폴더가 없습니다. 프로필의 경로를 확인하세요.')
    actual = entered.resolve(strict=True)
    if actual == Path(actual.anchor):
        raise SafeInputError('드라이브 루트는 학생 폴더로 지정할 수 없습니다.')
    variants = []
    for value in (str(entered), str(actual)):
        for form in ('NFC', 'NFD'):
            normalized = unicodedata.normalize(form, value)
            if normalized not in variants:
                variants.append(normalized)
    return variants


def obj(path):
    try:
        raw = path.read_text(encoding='utf-8-sig', errors='strict')
    except UnicodeError:
        raise SafeInputError('인코딩 오류입니다. UTF-8로 저장한 뒤 다시 실행하세요. 원본을 유지합니다.')
    if '\ufffd' in raw:
        raise SafeInputError('인코딩 오류입니다. UTF-8로 저장한 뒤 다시 실행하세요. 원본을 유지합니다.')
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise SafeInputError('JSON을 읽을 수 없습니다. 원본을 유지합니다. 판매자와 확인하세요.')
    if not isinstance(value, dict):
        raise SafeInputError('JSON 객체가 필요합니다.')
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


def save(path, data, home):
    safe_path(path, home)
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
    safe_path(path, a.home)
    value = obj(path) if path.exists() else {}
    before = copy.deepcopy(value)
    extra = None
    if a.action == 'apply-safety':
        profile = obj(Path(a.profile))
        paths = profile.get('studentDataPaths')
        if not isinstance(paths, list) or not paths:
            raise SafeInputError('studentDataPaths 배열에 폴더 1개 이상이 필요합니다.')
        perm = value.setdefault('permissions', {})
        if not isinstance(perm, dict):
            raise SafeInputError('permissions 객체가 필요합니다.')
        rules = []
        for folder in paths:
            for candidate in student_paths(folder, a.home):
                anchor = '/' + candidate.rstrip('/')
                for tool in ('Read', 'Edit'):
                    rules.extend([f'{tool}({anchor})', f'{tool}({anchor}/**)'])
        for key, additions in [('deny', rules), ('ask', ['Bash', 'PowerShell', 'WebFetch', 'WebSearch', 'mcp__*'])]:
            old = perm.get(key, [])
            if not isinstance(old, list) or any(not isinstance(x, str) for x in old):
                raise SafeInputError('권한 목록은 문자열 배열이어야 합니다.')
            perm[key] = list(dict.fromkeys(old + additions))
        perm['defaultMode'] = 'default'
        perm['disableBypassPermissionsMode'] = 'disable'
    else:
        dest = a.home / '.claude/ek-workroom/ek_engine.py'
        safe_path(dest, a.home)
        text = str(dest)
        if re.search(r'[\r\n"$`]', text):
            raise SafeInputError('홈 경로의 특수문자를 확인하세요.')
        line = value.setdefault('statusLine', {})
        if not isinstance(line, dict):
            raise SafeInputError('statusLine 객체가 필요합니다.')
        # 현재 확인한 Python 경로를 고정합니다. Node 설치는 필요 없습니다.
        python = sys.executable
        if re.search(r'[\r\n"$`]', python):
            raise SafeInputError('실행기 경로를 확인하세요.')
        line.update(type='command', command=f'"{python}" "{text}" statusline')
        extra = (dest, Path(__file__).read_bytes())
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if not a.apply or a.dry_run:
        print('미리보기(DryRun): 저장하지 않습니다. 승인 후 같은 명령에 --apply를 붙이세요.')
        print(encoded.decode('utf-8'))
        if extra:
            print('상태줄 실행기 1개를 고객 홈의 .claude/ek-workroom에 복사할 예정입니다.')
    else:
        if extra:
            save(*extra, home=a.home)
        if value != before or not path.exists():
            save(path, encoded, a.home)
            print('설정을 저장했습니다. 기존 파일이 있으면 수정 전 백업도 남겼습니다.')
        else:
            print('이미 같은 설정입니다. 변경과 새 백업이 없습니다.')
    if a.action == 'apply-safety':
        print('학생 폴더 차단은 Claude 도구 규칙이며 OS 권한 보호가 아닙니다. 셸 승인 요청에 학생 폴더 경로가 보이면 거절하세요.')


def contains(parent, child):
    if sys.platform == 'darwin':
        # Default APFS may accept different casing without resolving to canonical spelling.
        normalized = lambda p: unicodedata.normalize('NFC', p.as_posix()).rstrip('/').casefold()
        parent_text, child_text = normalized(parent), normalized(child)
        return child_text == parent_text or child_text.startswith(parent_text + '/')
    return child == parent or parent in child.parents


def relative_inside(parent, child):
    """Use the same case/Unicode comparison as contains on default Mac volumes."""
    if not contains(parent, child):
        raise ValueError('outside root')
    return Path(*child.parts[len(parent.parts):])


def hidden_path(path, boundary):
    if not contains(boundary, path):
        return True
    current = path
    while True:
        info = current.stat()
        if (current.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2 or
                getattr(info, 'st_flags', 0) & getattr(stat, 'UF_HIDDEN', 0x8000)):
            return True
        if same_location(current, boundary):
            return False
        current = current.parent


def same_location(first, second):
    return contains(first, second) and contains(second, first)


def workspace(a):
    profile = obj(Path(a.profile))
    raw = profile.get('workspacePath') or str(a.home / 'AI작업실')
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise SafeInputError('작업실은 절대 경로로 지정하세요.')
    entered = Path(os.path.abspath(raw))
    actual = entered.resolve()
    if entered == Path(entered.anchor) or actual == Path(actual.anchor) or same_location(entered, a.home) or same_location(actual, a.home.resolve()):
        raise SafeInputError('드라이브 루트나 홈 전체는 작업실로 지정할 수 없습니다.')
    paths = profile.get('studentDataPaths')
    if not isinstance(paths, list) or not paths:
        raise SafeInputError('studentDataPaths 배열에 폴더 1개 이상이 필요합니다.')
    protected = []
    for raw_student in paths:
        protected.extend(student_paths(raw_student, a.home))
        student = Path(os.path.abspath(raw_student))
        for w in (entered, actual):
            for s in (student, student.resolve()):
                if contains(w, s) or contains(s, w):
                    raise SafeInputError('작업실과 학생 폴더가 서로 포함되어 있어 만들 수 없습니다.')
    workflow = profile.get('workflow', {})
    code = workflow.get('code') if isinstance(workflow, dict) else None
    if not isinstance(code, str) or len(code) != 1 or code not in 'ABCDE':
        raise SafeInputError('업무 코드는 A~E 중 하나로 지정하세요.')
    templates = Path(__file__).resolve().parent.parent / 'templates'
    files = {
        'CLAUDE.md': '@AGENTS.md\n이 폴더 규칙은 AGENTS.md에 있습니다.\n',
        'AGENTS.md': (templates / 'AGENTS.md').read_text(encoding='utf-8-sig'),
        '검토/검토요청-양식.md': (templates / 'review-brief.md').read_text(encoding='utf-8-sig'),
        '내-업무-실행법.md': (templates / 'flows' / (code + '.md')).read_text(encoding='utf-8-sig'),
        '.ek-workroom/protected-paths.json': json.dumps(
            {'schemaVersion': 1, 'paths': list(dict.fromkeys(protected))},
            ensure_ascii=False, indent=2) + '\n',
    }
    dirs = ('입력', '결과', '원본', '검토', '.ek-workroom')
    # Existing children may themselves be links. Validate before any mutation.
    for name in list(dirs) + list(files):
        if not contains(actual, (entered / name).resolve()):
            raise SafeInputError('작업실 밖으로 연결된 경로에는 쓰지 않습니다.')
    metadata = entered / '.ek-workroom/protected-paths.json'
    metadata_changed = False
    if metadata.exists():
        old = obj(metadata)
        existing = old.get('paths')
        if old.get('schemaVersion') != 1 or not isinstance(existing, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in existing):
            raise SafeInputError('보호 경로 목록을 확인할 수 없습니다. 판매자와 확인하세요.')
        merged = list(dict.fromkeys(existing + protected))
        metadata_changed = merged != existing
        files['.ek-workroom/protected-paths.json'] = json.dumps({'schemaVersion': 1, 'paths': merged}, ensure_ascii=False, indent=2) + '\n'
    if a.dry_run:
        if metadata_changed:
            print('병합 예정: .ek-workroom/protected-paths.json')
        for name in dirs + tuple(files):
            if not (entered / name).exists() and not (entered / name).is_symlink():
                print('만들 예정: ' + name)
        return
    for name in dirs:
        (entered / name).mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = entered / name
        if target == metadata and metadata_changed:
            stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
            with metadata.with_name(metadata.name + '.bak-' + stamp).open('xb') as saved:
                saved.write(metadata.read_bytes())
            fd, temporary = tempfile.mkstemp(prefix='.ek-write-', dir=metadata.parent)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as saved:
                saved.write(content)
            os.replace(temporary, metadata)
            print('보호 경로 병합: ' + name)
        elif target.exists() or target.is_symlink():
            print('기존 파일 유지: ' + name)
        else:
            with target.open('x', encoding='utf-8', newline='\n') as out:
                out.write(content)
            print('생성: ' + name)


def new_output(raw):
    output = Path(raw).absolute()
    if output.exists() or output.is_symlink():
        raise SafeInputError('출력 파일이 이미 있습니다. 새 파일 이름을 지정하세요.')
    if not output.parent.is_dir():
        raise SafeInputError('출력 폴더를 먼저 만들어 주세요.')
    return output


def hwpx_text(a):
    source = Path(a.hwpx)
    output = new_output(a.out)
    with source.open('rb') as stream:
        header = stream.read(4)
    if source.suffix.lower() == '.hwp' or header == bytes.fromhex('D0CF11E0'):
        print('한컴오피스에서 HWPX나 PDF로 다른 이름 저장 후 다시 실행하세요.')
        return 2
    if source.suffix.lower() != '.hwpx':
        raise SafeInputError('HWPX 파일을 지정하세요.')
    lines = []
    with zipfile.ZipFile(source, 'r') as archive:
        if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
            raise SafeInputError('HWPX의 압축 해제 크기가 50MB를 넘습니다.')
        sections = [(int(match.group(1)), info) for info in archive.infolist()
                    if (match := re.fullmatch(r'Contents/section(\d+)\.xml', info.filename))]
        if not sections:
            raise SafeInputError('HWPX 본문을 찾지 못했습니다.')
        for _, info in sorted(sections, key=lambda row: row[0]):
            data = archive.read(info)
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise SafeInputError('지원하지 않는 HWPX XML 형식입니다.')
            tree = ET.fromstring(data)
            namespace = {'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph'}
            for paragraph in tree.findall('.//hp:p', namespace):
                # A nested table paragraph is emitted independently, once.
                pieces = []
                def collect(element):
                    for child in element:
                        if child.tag == '{' + namespace['hp'] + '}p':
                            continue
                        if child.tag == '{' + namespace['hp'] + '}t':
                            pieces.append(''.join(child.itertext()))
                        else:
                            collect(child)
                collect(paragraph)
                lines.append(''.join(pieces))
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines) + '\n')
    print('본문 저장: ' + output.name)
    return 0


def pdf(a):
    entered = Path(a.html).absolute()
    source = entered.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in ('.html', '.htm'):
        raise SafeInputError('HTML 파일을 지정하세요.')
    workspace_root = next((folder for folder in (entered.parent, *entered.parent.parents)
                           if (folder / '.ek-workroom/protected-paths.json').is_file()), None)
    if workspace_root is None:
        print('작업실 안 HTML만 PDF로 만들 수 있습니다')
        return 2
    base = workspace_root.resolve(strict=True)
    server_root = entered.parent.resolve(strict=True)
    paths = protected_paths(base)
    if paths is None:
        return 2
    protected = [Path(path).resolve() for path in paths]
    if (not contains(base, source) or not contains(base, server_root) or not contains(server_root, source) or
            any(contains(folder, source) or contains(folder, server_root) or
                contains(server_root, folder) for folder in protected)):
        raise SafeInputError('보호 대상 폴더를 포함한 위치에서는 PDF를 만들 수 없습니다.')
    with source.open('rb') as stream:
        if os.fstat(stream.fileno()).st_nlink >= 2:
            raise SafeInputError('하드링크 HTML은 PDF로 만들 수 없습니다.')
    output = new_output(a.pdf)
    override = os.environ.get('EK_PDF_BROWSER')
    candidates = ([override] if override is not None else [
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
    browser = next((p for p in candidates if p and Path(p).is_file()), None)
    if not browser:
        print('브라우저에서 열어 인쇄→PDF로 저장하세요.')
        return 2
    with tempfile.TemporaryDirectory(prefix='ek-pdf-') as temporary:
        rendered = Path(temporary) / 'output.pdf'
        token = os.urandom(16).hex()
        child_env = dict(os.environ, EK_PDF_ROOT=str(server_root), EK_PDF_STATE_DIR=temporary, EK_PDF_TOKEN=token)
        server = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name('pdf_server.py'))],
                                  env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port_file = Path(temporary) / 'port.txt'
            deadline = time.monotonic() + 10
            while not port_file.exists():
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise SafeInputError('PDF 임시 서버를 시작하지 못했습니다.')
                time.sleep(0.02)
            port = int(port_file.read_text(encoding='ascii'))
            url = f'http://127.0.0.1:{port}/{token}/' + quote(entered.name, safe='')
            result = subprocess.run([browser, '--headless', '--disable-gpu', '--no-first-run',
                                     '--no-pdf-header-footer', '--proxy-server=127.0.0.1:9',
                                     f'--proxy-bypass-list=<-loopback>;127.0.0.1:{port}',
                                     '--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1',
                                     '--disable-background-networking', '--disable-extensions',
                                     '--user-data-dir=' + temporary,
                                     '--print-to-pdf=' + str(rendered), url],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if result.returncode or not rendered.is_file():
                raise SafeInputError('PDF를 만들지 못했습니다. HTML을 확인하세요.')
            data = rendered.read_bytes()
            pages = len(re.findall(rb'/Type\s*/Page\b', data))
            if not pages:
                raise SafeInputError('PDF 페이지를 확인하지 못했습니다.')
            with output.open('xb') as stream:
                stream.write(data)
        finally:
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=10)
    print(f'PDF {pages}쪽: {output.name}')
    return 0


CODEX_REVIEW_TIMEOUT = 600
CODEX_DISABLED_FEATURES = [
    'shell_tool', 'unified_exec', 'browser_use', 'browser_use_external',
    'browser_use_full_cdp_access', 'in_app_browser', 'computer_use', 'apps',
    'plugins', 'remote_plugin', 'multi_agent', 'view_image', 'code_mode_host',
    'memories', 'hooks', 'workspace_dependencies', 'skill_mcp_dependency_install',
]
CODEX_CONFIG = ['mcp_servers={}', 'web_search="disabled"']
REVIEW_HEADER = '아래 파일 내용만 근거로 검토한다. 도구는 없다. 결과는 답변 텍스트로만.\n\n'


def protected_paths(base):
    metadata = base / '.ek-workroom/protected-paths.json'
    if not metadata.is_file():
        print('작업실 만들기(ek-mode)를 먼저 하세요')
        return None
    if not contains(base, metadata.resolve()):
        raise SafeInputError('보호 경로 목록을 확인할 수 없습니다. 판매자와 확인하세요.')
    value = obj(metadata)
    paths = value.get('paths')
    if value.get('schemaVersion') != 1 or not isinstance(paths, list) or not paths:
        raise SafeInputError('보호 경로 목록을 확인할 수 없습니다. 판매자와 확인하세요.')
    for path in paths:
        if not isinstance(path, str) or not path.strip() or not Path(path).is_absolute() or Path(path) == Path(Path(path).anchor):
            raise SafeInputError('보호 경로 목록을 확인할 수 없습니다. 판매자와 확인하세요.')
    return paths


def protected_brief(paths, prompt):
    def normalize(text):
        text = unicodedata.normalize('NFKC', text)
        text = ''.join(char for char in text if unicodedata.category(char) != 'Cf'
                       and char != '\u034f' and not '\u180b' <= char <= '\u180d'
                       and not '\ufe00' <= char <= '\ufe0f')
        return text.replace('\\', '/').casefold().rstrip('/')
    normalized = normalize(prompt)
    for path in paths:
        candidate = normalize(path)
        name = candidate.rsplit('/', 1)[-1]
        if candidate in normalized or name in normalized:
            raise SafeInputError('검토 요청에 보호 대상 폴더가 있습니다. 학생 경로를 빼고 다시 작성하세요.')


def opened_file_path(stream):
    """Get the final name of this open handle; never reopen a checked name."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        function = ctypes.WinDLL('kernel32', use_last_error=True).GetFinalPathNameByHandleW
        function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        function.restype = wintypes.DWORD
        handle = msvcrt.get_osfhandle(stream.fileno())
        size = function(handle, None, 0, 0)
        if not size:
            raise OSError('handle path unavailable')
        buffer = ctypes.create_unicode_buffer(size + 1)
        length = function(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError('handle path unavailable')
        value = buffer.value
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
        return Path(value)
    if sys.platform == 'darwin':
        import fcntl
        return Path(os.fsdecode(fcntl.fcntl(stream.fileno(), 50, b'\0' * 1024).split(b'\0', 1)[0]))
    return Path(os.readlink(f'/proc/self/fd/{stream.fileno()}'))


def read_review_file(base, paths, raw, boundary=None):
    entered = Path(raw).absolute()
    target = entered.resolve(strict=True)
    protected = [Path(path).resolve() for path in paths]
    boundary = boundary or base
    def validate(actual):
        if (not contains(boundary, actual) or same_location(boundary, actual) or
                any(contains(folder, actual) for folder in protected)):
            raise SafeInputError('검토 파일은 작업실 안의 보호되지 않은 파일이어야 합니다.')
        if hidden_path(actual, base):
            raise SafeInputError('숨김 폴더나 파일은 검토 대상으로 지정할 수 없습니다.')
        if actual.suffix.lower() not in ('.md', '.txt', '.html', '.htm', '.csv'):
            raise SafeInputError('검토 파일은 md·txt·html·htm·csv 파일만 가능합니다.')
    validate(target)
    if contains(base, entered) and hidden_path(entered, base):
        raise SafeInputError('숨김 폴더나 파일은 검토 대상으로 지정할 수 없습니다.')
    with target.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink >= 2:
            raise SafeInputError('하드링크 파일은 검토 대상으로 지정할 수 없습니다.')
        opened = opened_file_path(stream)
        validate(opened)
        data = stream.read(200 * 1024 + 1)
    if len(data) > 200 * 1024:
        raise SafeInputError('검토 파일 크기는 파일당 200KB 이하여야 합니다.')
    try:
        text = data.decode('utf-8-sig', errors='strict')
    except UnicodeError:
        raise SafeInputError('검토 파일은 UTF-8로 저장한 파일이어야 합니다.')
    return text, relative_inside(base, opened), len(data)


def target_text(base, paths, targets):
    if not targets:
        raise SafeInputError('검토 대상 파일을 1개 이상 지정하세요.')
    total = 0
    blocks = []
    for raw in targets:
        text, relative, size = read_review_file(base, paths, raw)
        total += size
        if total > 500 * 1024:
            raise SafeInputError('검토 대상 크기는 파일당 200KB·합계 500KB 이하여야 합니다.')
        blocks.append('\n\n=== 파일: ' + relative.as_posix() + ' ===\n' + text)
    return ''.join(blocks)


def codex_review_timeout():
    value = os.environ.get('EK_CODEX_REVIEW_TIMEOUT', '')
    if re.fullmatch(r'[0-9]+', value):
        try:
            seconds = int(value)
            if 1 <= seconds <= CODEX_REVIEW_TIMEOUT:
                return seconds
        except ValueError:
            pass
    return CODEX_REVIEW_TIMEOUT


def run_codex(arguments, *, input):
    # 깨진 옛 Codex도 세션을 끝없이 붙잡지 않도록 별도 프로세스 그룹에 제한을 둡니다.
    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        process.communicate(input, timeout=codex_review_timeout())
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill.exe', '/T', '/F', '/PID', str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, AttributeError):
                process.kill()
        process.wait()
        raise
    return subprocess.CompletedProcess(arguments, process.returncode)


def codex_review(a):
    base = Path(a.workspace).resolve(strict=True)
    review = (base / '검토').resolve(strict=True)
    brief = Path(a.brief).resolve(strict=True)
    output = new_output(a.out)
    if (review == base or not contains(base, review) or brief == review or
            not contains(review, brief) or not contains(review, output.resolve()) or not brief.is_file()):
        raise SafeInputError('검토 요청과 결과는 작업실의 검토 폴더 안에 있어야 합니다.')
    paths = protected_paths(base)
    if paths is None:
        return 2
    prompt, _, _ = read_review_file(base, paths, a.brief, boundary=review)
    protected_brief(paths, prompt)
    files = target_text(base, paths, a.target)
    executable = shutil.which('codex')
    if not executable:
        print('Codex 설치·로그인 먼저 확인하세요.')
        return 2
    prompt = REVIEW_HEADER + prompt + files
    with tempfile.TemporaryDirectory(prefix='.ek-review-', dir=review) as temporary, tempfile.TemporaryDirectory(prefix='ek-codex-empty-') as empty:
        staged = Path(temporary) / 'result.md'
        arguments = [executable, 'exec', '--sandbox', 'read-only', '--skip-git-repo-check',
                     '--ephemeral', '--color', 'never', '-C', empty]
        for feature in CODEX_DISABLED_FEATURES:
            arguments += ['--disable', feature]
        for config in CODEX_CONFIG:
            arguments += ['-c', config]
        arguments += ['-o', str(staged), '-']
        try:
            process = run_codex(arguments, input=prompt.encode('utf-8'))
        except subprocess.TimeoutExpired:
            print('Codex 검토가 10분 안에 끝나지 않아 멈췄습니다. 새 터미널에서 codex --version과 로그인을 확인하세요.')
            return 1
        if process.returncode:
            print('Codex 검토를 마치지 못했습니다.')
            return process.returncode
        if not staged.is_file():
            raise SafeInputError('Codex 검토 결과 파일이 없습니다.')
        # Exclusive publish also protects two invocations that passed validation together.
        with output.open('xb') as stream:
            stream.write(staged.read_bytes())
    print(str(output))
    return 0


def statusline():
    try:
        value = json.load(sys.stdin)
        parts = []
        clean = lambda x: re.sub(r'[\x00-\x1f\x7f]', '', str(x)).strip()
        model = value.get('model', {}).get('display_name')
        folder = value.get('workspace', {}).get('current_dir')
        if model:
            parts.append(clean(model))
        if folder:
            parts.append(clean(re.split(r'[/\\]', folder.rstrip('/\\'))[-1]))
        for container, label in ((value.get('context_window', {}), '대화'),
                                  (value.get('rate_limits', {}).get('five_hour', {}), '5시간')):
            used = container.get('used_percentage')
            if isinstance(used, (int, float)) and not isinstance(used, bool) and math.isfinite(used) and 0 <= used <= 100:
                parts.append(f'{label} {used:g}%')
        print(' · '.join(parts) if parts else 'AI 작업실')
    except Exception:
        print('AI 작업실')
    return 0


def mask_text(text, home, user=None, computer=None):
    """진단은 고정 라벨·숫자만 수집합니다. 이 함수는 추가 방어입니다."""
    values = [(str(home), '<HOME>'), (str(Path.home()), '<HOME>'),
              (user if user is not None else os.environ.get('USER'), '<USER>'),
              (computer if computer is not None else platform.node(), '<COMPUTER>'),
              (Path(home).name, '<USER>')]
    for raw, token in values:
        if raw:
            for candidate in {raw, raw.replace('\\', '/'), raw.replace('/', '\\')}:
                text = re.sub(re.escape(candidate), lambda _: token, text, flags=re.I)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<EMAIL>', text)
    text = re.sub(r'(?<!\d)0(?:1[016789]|2|[3-6]\d|70|50\d?)[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)', '<PHONE>', text)
    def hide_ip(match):
        try:
            ipaddress.ip_address(match.group().split('%')[0])
            return '<IP>'
        except ValueError:
            return match.group()
    text = re.sub(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', hide_ip, text)
    text = re.sub(r'(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:.]*(?:%[\w.-]+)?(?![\w:])', hide_ip, text)
    return text


def security_software(applications=Path('/Applications'), launch_daemons=Path('/Library/LaunchDaemons')):
    """설치 메타데이터와 실행 파일이 함께 있는 제품만 반환합니다."""
    import plistlib
    from xml.parsers.expat import ExpatError
    vendors = [('Defender', 'com.microsoft.wdav'), ('AhnLab', 'com.ahnlab'),
               ('CrowdStrike', 'com.crowdstrike.falcon')]
    known = set()
    # 고정 시스템 위치의 설치 메타데이터만 읽고 경로·원문은 보고하지 않습니다.
    for directory, pattern, bundle in ((applications, '*.app', True),
                                       (launch_daemons, '*.plist', False)):
        try:
            entries = list(directory.glob(pattern))
        except OSError:
            continue
        for entry in entries:
            try:
                metadata = entry / 'Contents/Info.plist' if bundle else entry
                with metadata.open('rb') as stream:
                    value = plistlib.load(stream)
                if not isinstance(value, dict):
                    continue
                identifier = value.get('CFBundleIdentifier' if bundle else 'Label')
                if not isinstance(identifier, str):
                    continue
                if bundle:
                    executable = value.get('CFBundleExecutable')
                    if not isinstance(executable, str) or not executable or Path(executable).name != executable:
                        continue
                    binary = entry / 'Contents/MacOS' / executable
                else:
                    arguments = value.get('ProgramArguments')
                    executable = value.get('Program') or (arguments[0] if isinstance(arguments, list) and arguments else None)
                    if not isinstance(executable, str) or not Path(executable).is_absolute():
                        continue
                    binary = Path(executable)
                if not binary.is_file() or not os.access(binary, os.X_OK):
                    continue
                for label, prefix in vendors:
                    if identifier == prefix or identifier.startswith(prefix + '.'):
                        known.add(label)
            except (OSError, ValueError, TypeError, ExpatError):
                continue
    return [label for label, _ in vendors if label in known]


def diag(a):
    lines = ['보내기 전에 직접 읽어 보세요', 'AI 작업실 진단: 파일 내용·폴더 목록·계정 정보는 수집하지 않습니다.',
             '사용자 <USER> / 컴퓨터 <COMPUTER> / 홈 <HOME>',
             'OS: ' + platform.system() + ' ' + platform.release(),
             'python3: ' + os.environ.get('EK_PYTHON_DESCRIPTION', 'python3 ' + platform.python_version())]
    for name in ('claude', 'codex', 'git', 'node', 'winget', 'pwsh'):
        code, output = command([name, '--version'])
        match = re.search(r'(?<![\d.])\d+(?:\.\d+){1,4}(?![\d.])', output)
        lines.append(name + ': ' + (match.group() if match else ('없음' if code is None else '버전 확인 불가')))
    lines += ['PATH 항목 수: ' + str(len([x for x in os.environ.get('PATH', '').split(os.pathsep) if x])),
              '디스크 여유 GB: ' + str(round(shutil.disk_usage(a.home).free / 1024**3, 1)),
              '실행 정책: Mac 해당 없음']
    known = security_software()
    lines.append('보안 SW: ' + (', '.join(known) + ' (설치 흔적 확인, 실행 상태는 확인 필요)'
                                if known else '확인 필요 (확실한 설치 근거 없음)'))
    for host in ('claude.ai', 'chatgpt.com'):
        code, _ = command(['curl', '--head', '--silent', '--max-time', '4', 'https://' + host])
        lines.append(host + ': ' + ('도달함' if code == 0 else '확인 불가'))
    result = mask_text('\n'.join(lines), a.home)
    output = Path(a.output) if a.output else a.home / 'ek-diag.txt'
    if not output.is_absolute():
        output = Path.cwd() / output
    if not output.resolve().is_relative_to(a.home.resolve()):
        raise SafeInputError('진단 저장은 지정한 홈 안에서만 가능합니다.')
    safe_path(output, a.home)
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
        process_code, _ = command(['pgrep', '-x', 'sshd'])
        service_code, service_raw = command(['launchctl', 'print', 'system/com.openssh.sshd'])
        if process_code == 0 or service_code == 0:
            found = True
            print('OpenSSH 서버: 프로세스 또는 등록 서비스가 있습니다. 시스템 설정에서 원격 로그인을 확인하세요.')
        else:
            unknown = True
            print('OpenSSH 서버: 실행 흔적은 확인되지 않았지만 꺼짐을 확정할 수 없습니다. 시스템 설정 > 일반 > 공유 > 원격 로그인을 직접 확인하세요.')
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
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            raise SafeInputError('명령 옵션을 확인하세요.')
    parser = SafeParser(description='AI 작업실 실행 도구')
    parser.add_argument('action', choices=['apply-safety', 'apply-statusline', 'apply-workspace', 'ek-pdf', 'ek-hwpx-text', 'ek-codex-review', 'ek-diag', 'ek-end-check', 'statusline'])
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--profile')
    parser.add_argument('--output')
    for option in ('html', 'pdf', 'hwpx', 'out', 'workspace', 'brief'):
        parser.add_argument('--' + option)
    parser.add_argument('--target', action='append')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    a = parser.parse_args()
    if not a.home.is_absolute():
        raise SafeInputError('홈 경로는 절대 경로로 입력하세요.')
    if a.action == 'apply-workspace':
        return workspace(a)
    if a.action in ('apply-safety', 'apply-statusline'):
        settings(a)
    elif a.action == 'ek-pdf':
        return pdf(a)
    elif a.action == 'ek-hwpx-text':
        return hwpx_text(a)
    elif a.action == 'ek-codex-review':
        return codex_review(a)
    elif a.action == 'ek-diag':
        diag(a)
    elif a.action == 'ek-end-check':
        end_check(a)
    else:
        return statusline()


if __name__ == '__main__':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
            sys.stdin.reconfigure(encoding='utf-8')
        sys.exit(main() or 0)
    except SafeInputError as error:
        print('실패: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('실패: 프로필·기존 JSON·경로·필수 도구를 확인하세요. 상세 원문은 공유하지 마세요.', file=sys.stderr)
        sys.exit(1)
