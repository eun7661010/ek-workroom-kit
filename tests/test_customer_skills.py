"""고객 스킬 계약과 실제 Edge 조판. 쓰기는 전달받은 저장소 .tmp 안으로 한정한다."""
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/ek-workroom'
TEMPLATES = PLUGIN / 'templates'
NAMES = ('cross-check worksheet-pdf lesson-slides hwpx-read parent-message '
         'spreadsheet-check korean-review explanation-draft question-draft blog-column').split()
SECTIONS = ('입력 체크리스트', '단계', '출력 양식', '품질 점검표', '더미 예시', '막힐 때 대처')


def check(ok, message):
    if not ok:
        raise AssertionError(message)
    print('PASS ' + message, flush=True)


def section(text, title):
    match = re.search(r'^## ' + re.escape(title) + r'\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    check(match is not None and bool(match[1].strip()), '필수 섹션: ' + title)
    return match[1]


def static_checks():
    texts = {}
    for name in NAMES:
        path = PLUGIN / 'skills' / name / 'SKILL.md'
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig', errors='strict')
        texts[name] = text
        check(len(raw) <= 6000 and '\ufffd' not in text and '???' not in text,
              name + ' UTF-8·6KB 이하·깨진 문자 없음')
        check(re.search(r'^name: ' + re.escape(name) + '$', text, re.M)
              and re.search(r'^description: .+필요할 때', text, re.M), name + ' 이름·트리거')
        parts = {title: section(text, title) for title in SECTIONS}
        check(2 <= parts['입력 체크리스트'].count('?”') <= 3, name + ' 부족한 입력 질문 2~3개')
        check(5 <= len(re.findall(r'^- \[ \]', parts['품질 점검표'], re.M)) <= 8,
              name + ' 업무 점검 5~8개')
        check(all(word in parts['단계'] for word in ('계획', '승인', '새', '열')),
              name + ' 계획·승인·생성·열람')
        check('입력:' in parts['더미 예시'] and '출력 요약:' in parts['더미 예시'], name + ' 입출력 예시')
        check(all(rule in text for rule in ('개인정보를 제거', '학생정보 폴더', '덮어쓰기 금지',
                                           '결과 파일을 열어 확인하기 전', '외부 검색·게시·발송·프로그램 설치',
                                           '잔여 개인정보', '처리를 중단', '제거본을 요청',
                                           '답변·검수표·다른 AI 입력에 재기재하지')),
              name + ' 공통 보호 원칙 유지')

    for name in ('worksheet-a4.html', 'answer-a4.html', 'slides-16x9.html',
                 'parent-message.md', 'notice-table.md', 'weekly-report.md'):
        check((TEMPLATES / name).is_file(), '템플릿 존재: ' + name)
    # 새 양식뿐 아니라 A~E 및 검토 브리프도 네트워크에 의존하지 않는다.
    for path in TEMPLATES.rglob('*'):
        if path.is_file():
            text = path.read_bytes().decode('utf-8-sig', errors='strict')
            check(not re.search(r'(?:https?|ftp|file):/{2}|(?:src|href)\s*=\s*[\"\']\s*//', text, re.I)
                  and '\ufffd' not in text, '템플릿 UTF-8·외부 URL 0: ' + path.name)
    check('worksheet-a4.html' in texts['worksheet-pdf'] and 'answer-a4.html' in texts['worksheet-pdf']
          and 'slides-16x9.html' in texts['lesson-slides'], 'HTML 양식 복사 연결')
    check(all(name in texts['parent-message'] for name in
              ('parent-message.md', 'notice-table.md', 'weekly-report.md')), 'A·B·C 양식 복사 연결')
    sheet = texts['spreadsheet-check']
    check(all(word in sheet for word in ('CSV UTF-8', '다른 이름으로 저장', '일치/불일치/누락',
                                         '자동 수정하지', '수식·매크로를 실행하거나 추가하지',
                                         '보고서만', '앞자리 0')), 'CSV 입력·분류·보고 전용 계약')
    for code, expected in {'A': 'parent-message.md', 'B': 'notice-table.md', 'C': 'weekly-report.md',
                           'D': 'blog-column', 'E': 'worksheet-a4.html'}.items():
        flow = (TEMPLATES / 'flows' / (code + '.md')).read_text(encoding='utf-8')
        command = re.search(r'`(/ek-workroom:[^`]+)`', flow)[1]
        check(expected in command and all(x in command for x in ('계획', '승인', '열')),
              '업무 ' + code + ' 실행 한 줄·절차·양식')
    check('answer-a4.html' in (TEMPLATES / 'flows/E.md').read_text(encoding='utf-8'), 'E 정답 양식 분리')

    # 문서 예시의 옵션 집합을 실제 양 플랫폼의 파서와 대조한다.
    ps_source = (PLUGIN / 'scripts/ek-codex-review.ps1').read_text(encoding='utf-8-sig')
    mac_source = (PLUGIN / 'scripts/ek_engine.py').read_text(encoding='utf-8')
    check("'-Workspace','-Brief','-Out','-Target'" in ps_source
          and "add_argument('--target', action='append')" in mac_source, '실제 반복 대상 파서 대조')
    for command in re.findall(r'^.*ek-codex-review\.(?:ps1|sh).*$', texts['cross-check'], re.M):
        flags = [x for x in shlex.split(command) if x.startswith('-')]
        if '.ps1' in command:
            check(flags == ['-NoProfile', '-ExecutionPolicy', '-File', '-Workspace', '-Brief',
                            '-Target', '-Target', '-Out'], 'Windows 반복 -Target 예시')
        else:
            check(flags == ['--workspace', '--brief', '--target', '--target', '--out'], 'Mac 반복 --target 예시')
    check(all(x in texts['cross-check'] for x in ('맞음/틀림/부분', '근거 파일·위치', '반영 여부')),
          '지적 판정표의 판정·근거·반영 여부')

    for name in ('question-draft', 'explanation-draft', 'worksheet-pdf'):
        check(all(x in texts[name] for x in ('출처 표기와 이용 허락은 별개', '전재·변형·인쇄 배부·온라인 공개',
                                             '원장에게 확인받기 전 진행하지', '이용범위-새번호.md')),
              name + ' 출처·허락 구분 및 미확인 이용 보류')
    check(all(x in texts['parent-message'] for x in
              ('원장 확정 문구라도', '사용 전 원장에게 근거·적용 규정 확인을 요청', '확인일',
               '초안에 ‘확인 필요’', '사용을 보류', '법률 판단을 대신하지', '법적 검증으로 표시하지'))
          and '환불은 제공된 확정 문구만 씁니다' not in texts['parent-message'], '권리 제한 문구 확인·법률 판단 위임 금지')
    agents = (TEMPLATES / 'AGENTS.md').read_text(encoding='utf-8')
    check(all(x in agents for x in ('고객 자료는 작업실 안에서만', '설치된 ek-workroom 플러그인의 스킬·양식·스크립트',
                                    '그 밖의 경로는 찾거나 열지', '보호 대상 폴더는 열지')), '작업실 경계·설치 플러그인 읽기 예외')
    check(all(x in texts['cross-check'] for x in ('Codex 필요', '수정 HTML에서 새 PDF', '전 쪽을 열어 확인',
                                                 'PDF는 미완료', '방금 만든 학생용·정답용 HTML', '실제 경로')),
          'HTML 교차 검토 후 새 PDF·열람·실제 대상 연결')
    check('`E-입력.txt`' in texts['worksheet-pdf'] and '탐색기로' in texts['worksheet-pdf']
          and all('학습지-' + kind + '-001.html/.pdf' in texts['worksheet-pdf']
                  for kind in ('학생용', '정답용')), '학습지 예시 입력 준비·실제 출력 이름')


class TemplateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = set()
        self.notes = False
        self.note_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.classes.update(attrs.get('class', '').split())
        if 'speaker-notes' in attrs.get('class', '').split():
            self.notes = True
        check(tag not in ('script', 'base', 'iframe', 'link'), '정적 템플릿 태그: ' + tag)
        for attr in ('src', 'href', 'srcset', 'background'):
            if attr in attrs:
                value = attrs[attr]
                check(not re.search(r'^[/\\]|:|(?:^|[/\\])\.\.(?:[/\\]|$)', value),
                      '템플릿 자원 상대 경로: ' + value)

    def handle_endtag(self, tag):
        if tag == 'section' and self.notes:
            self.notes = False

    def handle_data(self, data):
        if self.notes:
            self.note_text.append(data)


def check_template(name, text):
    parser = TemplateParser()
    parser.feed(text)
    if name == 'worksheet-a4':
        check({'sheet-header', 'metadata', 'name-field', 'question', 'question-number', 'choices'} <= parser.classes
              and 'answer-only' not in parser.classes and '정답표' not in text,
              '학생용 구조·정답 영역 미포함')
    elif name == 'answer-a4':
        check('answer-only' in parser.classes, '정답용 별도 클래스')
    else:
        check('speaker-notes' in parser.classes and not ''.join(parser.note_text).strip()
              and '@page{size:1280px 720px;margin:0}' in text, '16:9 쪽 규격·비어 있는 별도 메모 섹션')
    check(all(font in text for font in ("'Malgun Gothic'", "'Apple SD Gothic Neo'"))
          and 'break-inside:avoid' in text, name + ' 한글 글꼴·쪽나눔 보호')


def template_checks():
    for name in ('worksheet-a4', 'answer-a4', 'slides-16x9'):
        text = (TEMPLATES / (name + '.html')).read_text(encoding='utf-8')
        check_template(name, text)
        if name != 'slides-16x9':
            # Validate reusable formula markup even though template content is inert in the base PDF.
            formula = re.search(r'<template id="formula-block">(.*?)</template>', text, re.S)
            check(formula is not None, name + ' 복사용 수식 블록 존재')
            parser = TemplateParser()
            parser.feed(formula[1])
            check({'formula', 'fraction', 'numerator', 'denominator', 'radical', 'root-sign', 'root-body'}
                  <= parser.classes and '<sub>' in formula[1] and '<sup>' in formula[1],
                  name + ' 분수·첨자·근호 구조')
            check(all('.' + cls + '{' in text for cls in
                      ('formula', 'fraction', 'numerator', 'denominator', 'radical', 'root-sign', 'root-body'))
                  and 'border-bottom:1px solid currentColor' in text
                  and 'border-top:1px solid currentColor' in text, name + ' 외부 라이브러리 없는 수식 CSS')
            check('한 쪽 초과 문항·해설' in text and '승인된 문단 경계' in text
                  and '계속' in text and '그림·답안 칸도 쪽 경계' in text, name + ' 큰 블록 수동 분할 지침')


def render_checks(run):
    # 자체 실행할 때도 실제 홈·임시 폴더를 사용하지 않는다.
    base = run / 'customer-skills'
    base.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    for key, folder in [('USERPROFILE', 'home'), ('HOME', 'home'), ('CLAUDE_CONFIG_DIR', 'claude'),
                        ('CODEX_HOME', 'codex'), ('TEMP', 'temp'), ('TMP', 'temp')]:
        target = base / folder
        target.mkdir(exist_ok=True)
        env[key] = str(target)
    edge = next((Path(os.environ[key]) / 'Microsoft/Edge/Application/msedge.exe'
                 for key in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')
                 if key in os.environ and (Path(os.environ[key]) / 'Microsoft/Edge/Application/msedge.exe').is_file()), None)
    if sys.platform.startswith('linux'):
        print('SKIP Edge 렌더: Linux에는 Windows Edge·PowerShell이 없어 실제 PDF·수식 시각 검증은 판매자 PC에서 실행', flush=True)
        return False
    check(edge is not None, '실제 Edge 필수(없으면 실패, 모의 렌더 없음)')
    env['EK_PDF_BROWSER'] = str(edge)
    import fitz
    workspace = base / '가상 작업실'
    output = workspace / '결과'
    output.mkdir(parents=True)
    private = base / 'StudentProtected'
    private.mkdir()
    metadata = workspace / '.ek-workroom/protected-paths.json'
    metadata.parent.mkdir()
    metadata.write_text(json.dumps({'schemaVersion': 1, 'paths': [str(private)]}), encoding='utf-8')
    before = hashlib.sha256(metadata.read_bytes()).hexdigest()
    ps = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    specs = [('worksheet-a4', 1, ('일차방정식 연습', '이름:', '2x + 3 = 7')),
             ('answer-a4', 1, ('정답표', '근거 위치', '오답 이유')),
             ('slides-16x9', 2, ('밀도는 같은 부피에서 비교합니다', '두 물체의 부피가 같다면?'))]
    specs += [(name + '-math', pages, markers) for name, pages, markers in specs[:2]]
    for name, expected, markers in specs:
        source_name = name.removesuffix('-math')
        source = TEMPLATES / (source_name + '.html')
        text = source.read_text(encoding='utf-8')
        html, pdf, audit = [output / (name + ext) for ext in ('.html', '.pdf', '.jsonl')]
        if name.endswith('-math'):
            # 별도 수식 표본은 배포 양식의 기존 블록만 활성화한다. 기본 3종은 원본 바이트 그대로 렌더한다.
            text = text.replace('<template id="formula-block">', '<div>').replace('</template>', '</div>')
            html.write_text(text, encoding='utf-8')
            markers = markers + ('a + b', '√')
        else:
            html.write_bytes(source.read_bytes())
        result = subprocess.run([ps, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                 str(PLUGIN / 'scripts/ek-pdf.ps1'), '-Html', str(html), '-Pdf', str(pdf)],
                                env=dict(env, EK_PDF_AUDIT_LOG=str(audit)), capture_output=True, timeout=140)
        check(result.returncode == 0 and pdf.is_file(),
              name + ' 실제 ek-pdf 종료 0: ' + result.stdout.decode('utf-8-sig', errors='replace').strip())
        with fitz.open(pdf) as doc:
            check(len(doc) >= 1 and len(doc) == expected, name + f' PDF 쪽수 {len(doc)}')
            content = '\n'.join(page.get_text() for page in doc)
            # PDF 한글 추출은 글자 사이 공백이 들어갈 수 있다.
            compact = re.sub(r'\s+', '', content)
            check(all(re.sub(r'\s+', '', marker) in compact for marker in markers), name + ' 한글·핵심 내용 실제 PDF 포함')
            for page in doc:
                w, h = page.rect.width, page.rect.height
                ratio = 16 / 9 if name == 'slides-16x9' else 210 / 297
                check(abs(w / h - ratio) < .01, name + f' 실제 쪽 비율 {w:.1f}×{h:.1f}')
                check(all(block[0] >= -1 and block[1] >= -1 and block[2] <= w + 1 and block[3] <= h + 1
                          for block in page.get_text('blocks')), name + ' PDF 글자 경계 넘침 없음')
            # 사람이 확인할 세 대표 쪽만 남긴다.
            doc[0].get_pixmap(matrix=fitz.Matrix(.8, .8)).save(str(output / (name + '.png')))
        entries = [json.loads(line) for line in audit.read_text(encoding='utf-8-sig').splitlines()]
        check(any(x['status'] == 200 and x['path'] == html.name for x in entries)
              and all(not x['outside'] for x in entries), name + ' 임시 HTTP 서버 실제 로드·경계 유지')
    check(hashlib.sha256(metadata.read_bytes()).hexdigest() == before, '렌더 후 보호 목록 변경 0')
    check(not list((base / 'temp').glob('ek-pdf-*')), '렌더 임시 프로필·서버 상태 정리')
    print('고객 스킬 검증 산출물: ' + str(output), flush=True)
    return True


if __name__ == '__main__':
    run = Path(sys.argv[1]).resolve()
    check(run.is_relative_to(ROOT / '.tmp'), '테스트 쓰기는 저장소 .tmp 내부만')
    static_checks()
    template_checks()
    rendered = render_checks(run)
    print('CUSTOMER SKILLS ALL PASSED' if rendered else 'CUSTOMER SKILLS LINUX PASSED (Edge SKIP)', flush=True)
