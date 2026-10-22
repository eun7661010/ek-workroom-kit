"""Source fidelity and seller-only Edge PDF build; no install or real-home writes."""
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / 'docs/guidebook'
BASE = Path(sys.argv[1]).resolve() / 'guidebook'
BASE.mkdir(parents=True, exist_ok=True)


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print('PASS ' + name, flush=True)


def norm(text):
    return re.sub(r'\s+', ' ', text).strip()


def plain(text):
    return text.replace('**', '').replace('`', '')


def source_units(md):
    """Each Markdown paragraph, list item, heading, code block and table row."""
    units, paragraph, code = [], [], None

    def flush():
        if paragraph:
            units.append(plain(' '.join(paragraph)))
            paragraph.clear()

    for line in md.splitlines():
        if line.startswith('```'):
            flush()
            if code is None:
                code = []
            else:
                units.append('\n'.join(code))
                code = None
        elif code is not None:
            code.append(line)
        elif not line.strip():
            flush()
        elif line.startswith('|'):
            flush()
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                units.append(plain(' '.join(cells)))
        elif re.match(r'^(#{1,6} |\d+\. |- )', line):
            flush()
            units.append(plain(re.sub(r'^(#{1,6} |\d+\. |- )', '', line)))
        else:
            paragraph.append(line)
    flush()
    return [norm(unit) for unit in units]


class GuideText(HTMLParser):
    BLOCKS = {'p', 'li', 'h1', 'h2', 'h3', 'div', 'section', 'main', 'nav',
              'tr', 'td', 'th', 'pre', 'br'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.visible = False
        self.text = []
        self.links = []
        self.section_ids = []
        self.toc = {}
        self.toc_key = None
        self.external = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'body':
            self.visible = True
        if self.visible and tag in self.BLOCKS:
            self.text.append('\n')
        if tag == 'section':
            self.section_ids.append(attrs.get('id'))
        if tag == 'a':
            self.links.append(attrs.get('href'))
        if 'data-section' in attrs:
            self.toc_key = attrs['data-section']
        for key in ('src', 'href'):
            if key in attrs and not attrs[key].startswith('#'):
                self.external.append(attrs[key])

    def handle_endtag(self, tag):
        if tag == 'body':
            self.visible = False
        if self.visible and tag in self.BLOCKS:
            self.text.append('\n')
        if tag == 'span':
            self.toc_key = None

    def handle_data(self, data):
        if self.visible:
            self.text.append(data)
        if self.toc_key:
            self.toc[self.toc_key] = data.strip()


md_path = REPO / 'docs/customer-guidebook.md'
source_hash = hashlib.sha256(md_path.read_bytes()).hexdigest()
md = md_path.read_text(encoding='utf-8')
html = (GUIDE / 'guidebook.html').read_text(encoding='utf-8')
parsed = GuideText()
parsed.feed(html)
units = source_units(md)
visible = norm(''.join(parsed.text))
missing = [unit for unit in units if unit not in visible]
check(not missing, f'Markdown paragraphs/table rows preserved: {len(units)} units; missing={missing}')
check([s for s in parsed.section_ids if s and s.startswith('section-')] == [f'section-{n}' for n in range(1, 11)],
      'Body sections 1-10 in original order')
check(not parsed.external and not re.search(r'@import|url\s*\(', html, re.I),
      'No external URLs, fonts or resources')
check('table-header-group' in html and 'word-break: keep-all' in html
      and "'Malgun Gothic','Apple SD Gothic Neo'" in html,
      'Print table headers, Korean wrapping and requested fonts')

ps = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
output = BASE / 'guidebook.pdf'
command = [ps, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
           str(GUIDE / 'build.ps1'), '-OutputPath', str(output)]
env = os.environ.copy()
for key, folder in {'USERPROFILE': 'home', 'HOME': 'home',
                    'CLAUDE_CONFIG_DIR': 'claude-config', 'CODEX_HOME': 'codex-config',
                    'TEMP': 'temp', 'TMP': 'temp'}.items():
    target = BASE / folder
    target.mkdir(exist_ok=True)
    env[key] = str(target)
result = subprocess.run(command, capture_output=True, timeout=90, env=env)
log = result.stdout.decode('utf-8', errors='replace')
check(result.returncode == 0 and output.exists() and output.read_bytes().startswith(b'%PDF-'),
      'Seller build: Edge HTML to PDF succeeds')
match = re.search(r'PDF pages: (\d+)', log)
check(match is not None and int(match[1]) > 0, 'Build reports PDF page count')
print(log.strip(), flush=True)
before = hashlib.sha256(output.read_bytes()).hexdigest()
rejected = subprocess.run(command, capture_output=True, timeout=15, env=env)
check(rejected.returncode != 0 and hashlib.sha256(output.read_bytes()).hexdigest() == before,
      'Existing PDF rejected without overwrite')

try:
    import fitz
except ImportError:
    print('SKIP PyMuPDF unavailable: PDF text, A4, TOC and PNG checks', flush=True)
else:
    def inspect(path, render=False):
        with fitz.open(path) as pdf:
            check(len(pdf) == int(match[1]), f'{path.name}: page count {len(pdf)}')
            check('내 AI 작업실 사용 설명서' in norm(pdf[0].get_text()),
                  f'{path.name}: first page title')
            text = re.sub(r'\s+', '', ''.join(page.get_text() for page in pdf))
            missing_pdf = [u for u in units if re.sub(r'\s+', '', u) not in text]
            check(not missing_pdf, f'{path.name}: all source text in PDF; missing={missing_pdf}')
            for number, page in enumerate(pdf, 1):
                check(abs(page.rect.width - 595.276) < 1 and abs(page.rect.height - 841.89) < 1,
                      f'{path.name}: page {number} A4')
                blocks = [b for b in page.get_text('blocks') if b[4].strip()]
                check(bool(blocks), f'{path.name}: page {number} not blank')
                inset = 16 * 72 / 25.4 - 1.5
                check(all(b[0] >= inset and b[1] >= inset
                          and b[2] <= page.rect.width - inset
                          and b[3] <= page.rect.height - inset for b in blocks),
                      f'{path.name}: page {number} text within 16mm print area')
                fonts = page.get_fonts(full=True)
                check(all(pdf.extract_font(f[0])[3] for f in fonts),
                      f'{path.name}: page {number} fonts embedded')
                if render:
                    qa = BASE / 'png'
                    qa.mkdir(exist_ok=True)
                    page.get_pixmap(dpi=300).save(qa / f'page-{number:02}.png')
                    page.get_pixmap(dpi=300, colorspace=fitz.csGRAY).save(qa / f'page-{number:02}-gray.png')
            headings = re.findall(r'^## (.+)$', md, re.M)
            for n, heading in enumerate(headings, 1):
                pages = [i + 1 for i, page in enumerate(pdf) if i > 1
                         and any(norm(b[4]) == norm(plain(heading))
                                 for b in page.get_text('blocks'))]
                check(len(pages) == 1 and parsed.toc[str(n)] == str(pages[0]),
                      f'{path.name}: section {n} TOC page matches {pages}')
            check(norm(pdf[-2].get_text()).startswith('내 업무 실행법')
                  and all(f'업무 {c}' in pdf[-2].get_text() for c in 'ABCDE')
                  and all(label in norm(pdf[-2].get_text()) for label in
                          ('입력 위치', '실행 한 줄', '결과 위치', '검수 항목', '처음/혼자 다시 걸린 분')),
                  f'{path.name}: single worksheet page A-E and all fields')
            check(norm(pdf[-1].get_text()).startswith('승인 창 판단표')
                  and '학생 폴더 경로가 보이는 명령' in norm(pdf[-1].get_text()),
                  f'{path.name}: single approval reference page, protection intact')
            print(f'PDF checked: {len(pdf)} pages; problem pages: none (automated)', flush=True)

    inspect(output)
    delivered = GUIDE / 'ek-workroom-guidebook-0.2.2.pdf'
    check(delivered.is_file(), 'Delivery PDF exists')
    inspect(delivered, render=True)

check(hashlib.sha256(md_path.read_bytes()).hexdigest() == source_hash, 'Source Markdown unchanged')
print('GUIDEBOOK ALL PASSED', flush=True)
