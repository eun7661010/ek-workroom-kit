"""Windows HTTP PDF isolation: real Edge rendering and raw HTTP boundary probes."""
import hashlib
import base64
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import sys
import threading
import tempfile
import time
import zlib
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'plugins/ek-workroom/scripts'
BASE = Path(sys.argv[1]).resolve() / 'pdf-isolation'
BASE.mkdir(parents=True, exist_ok=True)
WORKSPACE = BASE / '작업실'
ROOT = WORKSPACE / '한글 공백 HTML'
ROOT.mkdir(parents=True, exist_ok=True)
PRIVATE = BASE / 'StudentPrivate'
PRIVATE.mkdir(exist_ok=True)
METADATA = WORKSPACE / '.ek-workroom/protected-paths.json'
METADATA.parent.mkdir(exist_ok=True)
METADATA.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(PRIVATE)]}), encoding='utf-8')
TOKEN = secrets.token_hex(16)
ENV = os.environ.copy()
TEMP = BASE / 'temp'
TEMP.mkdir(exist_ok=True)
ENV.update(TEMP=str(TEMP), TMP=str(TEMP))
PS = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def check(ok, message):
    assert ok, message
    print('PASS ' + message, flush=True)


def png(path, width, height, seed):
    # Deterministic, large, incompressible RGB pixels give an unambiguous fingerprint.
    raw = hashlib.shake_256(seed.encode()).digest(width * height * 3)
    scanlines = b''.join(b'\0' + raw[i:i + width * 3]
                         for i in range(0, len(raw), width * 3))
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))
    return hashlib.sha256(raw).hexdigest()


logo_hash = png(ROOT / '로고.png', 43, 29, 'normal-logo')
SECRET = BASE / '비밀 이미지.png'
secret_hash = png(SECRET, 431, 317, 'private-large-image')
(ROOT / '정상.html').write_text('''<!doctype html><meta charset="utf-8">
<style>@page{size:A4;margin:20mm} .next{break-before:page}</style>
<h1>학습지 1쪽</h1><img src="로고.png"><div class="next">학습지 2쪽</div>''', encoding='utf-8')
(ROOT / '.hidden.html').write_text('hidden', encoding='utf-8')
(ROOT / 'secret.txt').write_text('not served', encoding='utf-8')
(ROOT / 'visible.html').write_text('<h1>allowed</h1>', encoding='utf-8')
state = BASE / 'server-state'
state.mkdir(exist_ok=True)
server_env = dict(ENV, EK_PDF_ROOT=str(ROOT), EK_PDF_STATE_DIR=str(state), EK_PDF_TOKEN=TOKEN)
server = subprocess.Popen([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPTS / 'pdf-server.ps1')],
                          env=server_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def request(path, method='GET', *, token=True):
    if token:
        path = '/' + TOKEN + path
    with socket.create_connection(('127.0.0.1', port), timeout=5) as client:
        client.sendall(f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'.encode('ascii'))
        data = b''
        while True:
            part = client.recv(65536)
            if not part:
                break
            data += part
        return int(data.split(b' ', 2)[1]), data


try:
    ready = state / 'port.txt'
    for _ in range(500):
        if ready.exists():
            break
        if server.poll() is not None:
            raise AssertionError('PDF server failed')
        time.sleep(.03)
    port = int(ready.read_text(encoding='utf-8-sig'))
    code, data = request('/visible.html')
    check(code == 200 and b"script-src 'none'" in data, 'PDF 서버 정상 파일·CSP 제공')
    check(request('/visible.html', token=False)[0] == 404
          and request('/' + '0' * 32 + '/visible.html', token=False)[0] == 404,
          'PDF 서버 토큰 없음·틀린 토큰 404')
    denied = ['/../outside.png', '/%2e%2e/outside.png', '/%5coutside.png', '//outside.png',
              '/C:/outside.png', '/.hidden.html', '/secret.txt', '/visible.html:secret', '/visible.html%3Asecret']
    os.link(SECRET, ROOT / 'hardlink.png')
    denied.append('/hardlink.png')
    import ctypes
    hidden_parent = ROOT / 'HiddenParent'
    hidden_parent.mkdir()
    (hidden_parent / 'image.png').write_bytes((ROOT / '로고.png').read_bytes())
    assert ctypes.windll.kernel32.SetFileAttributesW(str(hidden_parent), 2)
    hidden_file = ROOT / 'hidden-attribute.png'
    hidden_file.write_bytes((ROOT / '로고.png').read_bytes())
    assert ctypes.windll.kernel32.SetFileAttributesW(str(hidden_file), 2)
    denied.extend(('/HiddenParent/image.png', '/hidden-attribute.png'))
    junction = ROOT / 'escape'
    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(BASE)], capture_output=True)
    check(made.returncode == 0, 'PDF 서버 junction 시험 준비')
    denied.append('/escape/' + quote(SECRET.name))
    for path in denied:
        check(request(path)[0] == 404, 'PDF 서버 경계·숨김·확장자 404: ' + path)
    assert ctypes.windll.kernel32.SetFileAttributesW(str(ROOT), 2)
    try:
        check(request('/visible.html')[0] == 404, 'PDF 서버 숨김 루트 속성도 404')
    finally:
        assert ctypes.windll.kernel32.SetFileAttributesW(str(ROOT), 16)
    check(request('/visible.html', 'POST')[0] == 404, 'PDF 서버 GET 외 404')
    logs = [json.loads(line) for line in (state / 'access.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    check(all(x['path'] is None or (not x['path'].startswith('/') and '..' not in x['path']) for x in logs)
          and any(x['status'] == 404 and x['outside'] for x in logs), 'PDF 서버 감사: 탈출 404·성공 경로 루트 내부만')
finally:
    server.kill()
    server.wait()


def pdf_tool(html, output, audit):
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPTS / 'ek-pdf.ps1'),
                           '-Html', str(html), '-Pdf', str(output)], env=dict(ENV, EK_PDF_AUDIT_LOG=str(audit)),
                          capture_output=True, timeout=140)


orphan = BASE / 'outside-workspace.html'
orphan.write_text('<h1>outside</h1>', encoding='utf-8')
result = pdf_tool(orphan, BASE / 'orphan.pdf', BASE / 'orphan.jsonl')
check(result.returncode == 2 and result.stdout.decode('utf-8-sig').strip() == '작업실 안 HTML만 PDF로 만들 수 있습니다'
      and not (BASE / 'orphan.pdf').exists(), 'PDF 작업실 메타데이터 없는 HTML 종료 2')
inside_private = WORKSPACE / 'PrivateInside'
inside_private.mkdir()
(inside_private / 'private.html').write_text('<h1>private</h1>', encoding='utf-8')
saved_metadata = METADATA.read_bytes()
METADATA.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(PRIVATE), str(inside_private)]}), encoding='utf-8')
private_alias = WORKSPACE / 'PrivateAlias'
assert subprocess.run(['cmd', '/c', 'mklink', '/J', str(private_alias), str(inside_private)], capture_output=True).returncode == 0
for number, candidate in enumerate((inside_private / 'private.html', private_alias / 'private.html', ROOT / 'escape/outside-workspace.html')):
    output = BASE / f'private-{number}.pdf'
    result = pdf_tool(candidate, output, BASE / f'private-{number}.jsonl')
    check(result.returncode == 1 and not output.exists(), f'PDF 보호 폴더·junction 실제 경로 거부 {number+1}')
contained_private = ROOT / 'StudentBelow'
contained_private.mkdir()
METADATA.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(contained_private)]}), encoding='utf-8')
result = pdf_tool(ROOT / '정상.html', BASE / 'contains-private.pdf', BASE / 'contains-private.jsonl')
check(result.returncode == 1 and not (BASE / 'contains-private.pdf').exists(), 'PDF 서버 루트가 보호 폴더를 품으면 거부')
METADATA.write_bytes(saved_metadata)
os.link(orphan, ROOT / 'hardlink.html')
result = pdf_tool(ROOT / 'hardlink.html', BASE / 'hardlink.pdf', BASE / 'hardlink.jsonl')
check(result.returncode == 1 and not (BASE / 'hardlink.pdf').exists(), 'PDF 하드링크 HTML 입력 거부')


edge = next((Path(os.environ.get(key, '')) / 'Microsoft/Edge/Application/msedge.exe'
             for key in ['ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA']
             if (Path(os.environ.get(key, '')) / 'Microsoft/Edge/Application/msedge.exe').is_file()), None)
if edge is None:
    print('SKIP Edge 실제 PDF 격리: Edge 없음')
else:
    ENV['EK_PDF_BROWSER'] = str(edge)
    try:
        import fitz
    except ImportError:
        fitz = None

    def images(pdf):
        if fitz is None:
            # The stdlib fallback still checks every image dictionary's dimensions.
            raw = pdf.read_bytes()
            sizes = [(int(a), int(b)) for a, b in re.findall(rb'/Width\s+(\d+)\s*/Height\s+(\d+)', raw)]
            return sizes, set(), len(re.findall(rb'/Type\s*/Page\b', raw))
        with fitz.open(pdf) as doc:
            # CSS backgrounds may be nested in tiling patterns instead of page image lists.
            xrefs = {xref for xref in range(1, doc.xref_length())
                     if doc.xref_get_key(xref, 'Subtype')[1] == '/Image'}
            sizes, hashes = [], set()
            for xref in xrefs:
                pix = fitz.Pixmap(doc, xref)
                sizes.append((pix.width, pix.height))
                hashes.add(hashlib.sha256(pix.samples).hexdigest())
            return sizes, hashes, len(doc)

    started = time.monotonic()
    good = BASE / '정상 2쪽.pdf'
    audit = BASE / 'normal.jsonl'
    result = pdf_tool(ROOT / '정상.html', good, audit)
    check(result.returncode == 0, 'Edge 정상 상대 로고 PDF 생성: ' + result.stdout.decode('utf-8', 'replace').strip())
    sizes, hashes, pages = images(good)
    check(pages == 2 and (43, 29) in sizes and (fitz is None or logo_hash in hashes),
          f'Edge 실제 PDF 2쪽·상대 로고 이미지 크기/픽셀 SHA256 ({time.monotonic()-started:.1f}초)')
    uri = SECRET.as_uri()
    secret_css = BASE / 'secret.css'
    secret_css.write_text('body { background-image: url("' + uri + '"); background-repeat: no-repeat; '
                          '-webkit-print-color-adjust: exact; print-color-adjust: exact; }', encoding='utf-8')
    css_uri = secret_css.as_uri()
    data_candidate = 'data:image/png;base64,' + base64.b64encode((ROOT / '로고.png').read_bytes()).decode('ascii')
    data_css = 'data:text/css,' + quote(f'@import url("{css_uri}");', safe='')
    # Printing can prefer the highest-density candidate regardless of screen DPR.
    # The second srcset keeps the secret as the highest candidate for that path too.
    attack_html = [f'<img src="{uri}">', f'<img srcset="{data_candidate} 2x, {uri} 1x">'
                   + f'<img srcset="{data_candidate} 0.5x, {uri} 1x">',
                   f'<style>body{{background-image:url("{uri}")}}</style>', f'<style>@import url("{css_uri}");</style>',
                   f'<link rel="stylesheet" href="{data_css}">',
                   f'<body background="{uri}">', f'<base href="{BASE.as_uri()}/"><img src="{quote(SECRET.name)}">']

    def positive_control(source, number):
        # Test-only controlled local fixtures: remove browser file-origin restrictions
        # so each attack must actually reveal this synthetic image without our HTTP boundary.
        with tempfile.TemporaryDirectory(prefix='positive-', dir=TEMP) as private:
            out = Path(private) / 'positive.pdf'
            result = subprocess.run([str(edge), '--headless', '--disable-gpu', '--no-first-run',
                                     '--no-pdf-header-footer', '--disable-background-networking', '--disable-extensions',
                                     '--proxy-server=127.0.0.1:9', '--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1',
                                     '--allow-file-access-from-files', '--disable-web-security', '--force-device-scale-factor=1',
                                     '--user-data-dir=' + str(Path(private) / 'profile'), '--print-to-pdf=' + str(out),
                                     source.as_uri()], env=ENV, capture_output=True, timeout=120)
            check(result.returncode == 0 and out.exists(), f'Edge 통제된 양성 대조 {number} PDF 생성')
            control_sizes, control_hashes, _ = images(out)
            check((431, 317) in control_sizes and (fitz is None or secret_hash in control_hashes),
                  f'Edge 양성 대조 {number}: 합성 비밀 이미지 크기·픽셀 SHA256 일치')

    for number, html in enumerate(attack_html, 1):
        source = ROOT / f'attack-{number}.html'
        source.write_text('<!doctype html><meta charset="utf-8"><body style="min-height:600px;'
                          '-webkit-print-color-adjust:exact;print-color-adjust:exact"><h1>비밀 이미지 차단</h1>' + html, encoding='utf-8')
        positive_control(source, number)
        out, log = BASE / f'attack-{number}.pdf', BASE / f'attack-{number}.jsonl'
        result = pdf_tool(source, out, log)
        check(result.returncode == 0 and out.exists(), f'Edge 공격 HTML {number} PDF 생성')
        sizes, hashes, _ = images(out)
        entries = [json.loads(line) for line in log.read_text(encoding='utf-8-sig').splitlines()]
        check((431, 317) not in sizes and secret_hash not in hashes and all(w < 64 and h < 64 for w, h in sizes)
              and all(not item['outside'] for item in entries),
              f'Edge 공격 {number}: 비밀 이미지 0개(총 {len(sizes)}, 깨진 이미지 아이콘 허용)·크기/픽셀 SHA256 불일치·서버 루트 밖 요청 0')
    # CSP prevents inline JavaScript and a second local HTTP origin as well.
    observed = []
    class Observer(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append(self.path)
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            self.wfile.write((ROOT / '로고.png').read_bytes())
        def log_message(self, *args):
            pass
    observer = http.server.HTTPServer(('127.0.0.1', 0), Observer)
    thread = threading.Thread(target=observer.serve_forever, daemon=True)
    thread.start()
    script_html = ROOT / 'script.html'
    script_html.write_text('<h1>CSP</h1><script>document.write(\'<img src="로고.png">\')</script>'
                           + f'<img src="http://127.0.0.1:{observer.server_port}/other-origin.png">', encoding='utf-8')
    script_pdf, script_log = BASE / 'script.pdf', BASE / 'script.jsonl'
    try:
        check(pdf_tool(script_html, script_pdf, script_log).returncode == 0 and (43, 29) not in images(script_pdf)[0]
              and not any(x['path'] == '로고.png' for x in map(json.loads, script_log.read_text(encoding='utf-8-sig').splitlines()))
              and not observed, 'Edge CSP: 인라인 JavaScript 실행·다른 루프백 포트 이미지 요청 0')
    finally:
        observer.shutdown()
        observer.server_close()
        thread.join(timeout=2)
    # Top-level meta refresh must not bypass the proxy via either loopback family.
    for family, address, host in ((socket.AF_INET, '127.0.0.1', '127.0.0.1'),
                                  (socket.AF_INET6, '::1', '[::1]')):
        nav_hits = []
        secret_text = 'EK_LOOPBACK_SECRET_' + secrets.token_hex(12).upper()
        class SecretPage(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nav_hits.append(self.path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(('<h1>' + secret_text + '</h1>').encode('utf-8'))
            def log_message(self, *args):
                pass
        class LocalServer(http.server.HTTPServer):
            address_family = family
        local = LocalServer((address, 0), SecretPage)
        worker = threading.Thread(target=local.serve_forever, daemon=True)
        worker.start()
        label = 'IPv4' if family == socket.AF_INET else 'IPv6'
        try:
            # Prove the listener is reachable without the renderer's proxy restriction.
            connection = http.client.HTTPConnection(address, local.server_port, timeout=5)
            connection.request('GET', '/secret.html')
            response = connection.getresponse()
            check(response.status == 200 and secret_text.encode() in response.read(), label + ' 비밀 테스트 서버 양성 대조')
            connection.close()
            nav_hits.clear()
            source = ROOT / ('navigate-' + label + '.html')
            source.write_text('<!doctype html><meta http-equiv="refresh" content="0; url=http://'
                              + host + ':' + str(local.server_port) + '/secret.html"><h1>safe</h1>', encoding='utf-8')
            output, log = BASE / ('navigate-' + label + '.pdf'), BASE / ('navigate-' + label + '.jsonl')
            result = pdf_tool(source, output, log)
            entries = [json.loads(line) for line in log.read_text(encoding='utf-8-sig').splitlines()]
            check(any(entry['status'] == 200 and entry['path'] == source.name for entry in entries),
                  label + ' 이동 HTML을 임시 서버에서 실제 로드')
            check((result.returncode == 0 and output.exists()) or (result.returncode == 1 and not output.exists()),
                  label + ' 루프백 이동: PDF 생성 또는 차단 시 출력 없음')
            if not output.exists():
                check(not nav_hits, label + ' meta refresh: Edge 출력 중단·비밀 PDF 없음·다른 로컬 서버 요청 0')
            elif fitz is not None:
                with fitz.open(output) as document:
                    extracted = ''.join(page.get_text() for page in document)
                check(secret_text not in extracted and not nav_hits,
                      label + ' meta refresh: 비밀 문자열 미포함·다른 로컬 서버 요청 0')
            else:
                check(not nav_hits, label + ' meta refresh: 다른 로컬 서버 요청 0 (PDF 텍스트 검사는 PyMuPDF 없음)')
        finally:
            local.shutdown()
            local.server_close()
            worker.join(timeout=2)
    before = hashlib.sha256(good.read_bytes()).hexdigest()
    check(pdf_tool(ROOT / '정상.html', good, BASE / 'overwrite.jsonl').returncode == 1
          and hashlib.sha256(good.read_bytes()).hexdigest() == before, 'PDF 기존 출력 유지')
missing_env = dict(ENV, EK_PDF_BROWSER=str(BASE / 'absent.exe'))
missing = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPTS / 'ek-pdf.ps1'),
                          '-Html', str(ROOT / '정상.html'), '-Pdf', str(BASE / 'no-browser.pdf')], env=missing_env, capture_output=True)
check(missing.returncode == 2, 'PDF 브라우저 없음 종료 2')
check(not list(TEMP.glob('ek-pdf-*')), 'PDF 임시 프로필·서버 상태 정리')
