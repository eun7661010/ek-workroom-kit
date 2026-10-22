"""One-render loopback file server. Configuration is passed only through the environment."""
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import stat
import sys
import threading
from urllib.parse import unquote, urlsplit


EXTENSIONS = {'.html', '.htm', '.css', '.png', '.jpg', '.jpeg', '.gif', '.webp',
              '.svg', '.woff', '.woff2', '.ttf', '.otf'}
MIME = {'.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
        '.svg': 'image/svg+xml', '.woff': 'font/woff', '.woff2': 'font/woff2',
        '.ttf': 'font/ttf', '.otf': 'font/otf'}
CSP = ("default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline' data:; "
       "font-src 'self' data:; script-src 'none'; connect-src 'none'; object-src 'none'; "
       "frame-src 'none'; base-uri 'none'; form-action 'none'")


def contains(root, path):
    if sys.platform == 'darwin':
        import unicodedata
        normalize = lambda value: unicodedata.normalize('NFC', value.as_posix()).rstrip('/').casefold()
        first, second = normalize(root), normalize(path)
        return second == first or second.startswith(first + '/')
    return path == root or root in path.parents


def relative_inside(root, path):
    if not contains(root, path):
        raise ValueError('outside root')
    return Path(*path.parts[len(root.parts):])


def hidden_path(path, root):
    if not contains(root, path):
        return True
    while True:
        info = path.stat()
        if (path.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2 or
                getattr(info, 'st_flags', 0) & getattr(stat, 'UF_HIDDEN', 0x8000)):
            return True
        if contains(path, root):
            return False
        path = path.parent


def request_relative(request, token):
    parsed = urlsplit(request)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith('/') or parsed.path.startswith('//'):
        return None
    try:
        decoded = unquote(parsed.path[1:], encoding='utf-8', errors='strict')
    except UnicodeError:
        return None
    parts = decoded.split('/')
    if (len(parts) < 2 or parts[0] != token or not re.fullmatch(r'[0-9a-f]{32}', token) or
            ':' in decoded or '\\' in decoded or any(ord(c) < 32 for c in decoded) or
            any(not part or part.startswith('.') for part in parts[1:])):
        return None
    return '/'.join(parts[1:])


def safe_target(root, request, token):
    relative = request_relative(request, token)
    if relative is None:
        return None
    try:
        lexical = root / relative
        candidate = lexical.resolve(strict=True)
        if (not contains(root, candidate) or not candidate.is_file() or
                candidate.suffix.lower() not in EXTENSIONS or lexical.suffix.lower() not in EXTENSIONS or
                hidden_path(lexical, root) or hidden_path(candidate, root)):
            return None
        return candidate
    except (OSError, ValueError):
        return None


def opened_file_path(stream):
    """Find the object actually opened, including a directory swapped after validation."""
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


def read_resource(root, request, token):
    target = safe_target(root, request, token)
    if target is None:
        return None
    try:
        with target.open('rb') as stream:
            opened = opened_file_path(stream)
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink >= 2 or
                    not contains(root, opened) or opened.suffix.lower() not in EXTENSIONS or
                    hidden_path(opened, root)):
                return None
            return opened, stream.read()
    except (OSError, ValueError):
        return None


def main():
    root = Path(os.environ['EK_PDF_ROOT']).resolve(strict=True)
    state = Path(os.environ['EK_PDF_STATE_DIR'])
    audit = os.environ.get('EK_PDF_AUDIT_LOG')
    token = os.environ['EK_PDF_TOKEN']
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('invalid token')

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def finish_response(self, status, target=None):
            if audit:
                decoded = unquote(urlsplit(self.path).path)
                decoded = decoded.removeprefix('/' + token)
                outside = ('\\' in decoded or decoded.startswith('//') or
                           any(part == '..' for part in decoded.split('/')))
                if not outside:
                    try:
                        outside = not contains(root, (root / decoded.lstrip('/')).resolve())
                    except (OSError, ValueError):
                        outside = True
                with open(audit, 'a', encoding='utf-8') as log:
                    log.write(json.dumps({'status': status, 'path': relative_inside(root, target).as_posix()
                                          if target else None, 'outside': outside}, ensure_ascii=False) + '\n')

        def do_GET(self):
            resource = read_resource(root, self.path, token)
            if resource is None:
                self.finish_response(404)
                self.send_error(404)
                return
            target, data = resource
            self.finish_response(200, target)
            self.send_response(200)
            self.send_header('Content-Type', MIME[target.suffix.lower()])
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', CSP)
            self.end_headers()
            self.wfile.write(data)

        def do_HEAD(self):
            self.finish_response(404)
            self.send_error(404)

        do_POST = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = do_HEAD

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    with Server(('127.0.0.1', 0), Handler) as server:
        (state / 'port.txt').write_text(str(server.server_port), encoding='ascii')
        timer = threading.Timer(120, server.shutdown)
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            timer.cancel()


if __name__ == '__main__':
    main()
