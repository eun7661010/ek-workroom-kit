"""v0.2.0 실행 도구 시험. 설치/실제 AI 호출 없이 저장소 .tmp에서만 쓴다."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1]).resolve() / 'v020'
assert run.is_relative_to(root / '.tmp')
run.mkdir(parents=True)
scripts = root / 'plugins/ek-workroom/scripts'
ps = [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
      '-NoProfile', '-ExecutionPolicy', 'Bypass']
env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
for key, name in [('USERPROFILE', 'home'), ('HOME', 'home'), ('TEMP', 'temp'), ('TMP', 'temp'),
                  ('CLAUDE_CONFIG_DIR', 'claude'), ('CODEX_HOME', 'codex')]:
    folder = run / name
    folder.mkdir(exist_ok=True)
    env[key] = str(folder)


def execute(args, *, input=None, extra=None, timeout=140):
    return subprocess.run(args, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=dict(env, **(extra or {})), timeout=timeout)


def tool(name, *args, **kwargs):
    return execute(ps + ['-File', str(scripts / (name + '.ps1'))] + [str(a) for a in args], **kwargs)


def check(ok, name, result=None):
    if not ok and result:
        print(result.stdout.decode('utf-8', errors='replace'))
        print(result.stderr.decode('utf-8', errors='replace'))
    assert ok, name
    print('PASS ' + name)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


home = Path(env['HOME'])
student = home / '학생 자료'
student.mkdir()
profile = home / 'profile.json'
workspace = home / 'AI작업실'
data = {'studentDataPaths': [str(student)], 'workflow': {'code': 'E'}}
write_json(profile, data)
preview = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(preview.returncode == 0 and not workspace.exists(), 'workspace DryRun 쓰기 0', preview)
created = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile)
check(created.returncode == 0 and all((workspace / p).is_dir() for p in ('입력', '결과', '원본', '검토')),
      'workspace 기본 실행 생성', created)
check((workspace / 'CLAUDE.md').read_text(encoding='utf-8-sig').splitlines()[0] == '@AGENTS.md', 'workspace CLAUDE import 첫 줄')
before = {p.relative_to(workspace): p.read_bytes() for p in workspace.rglob('*') if p.is_file()}
(workspace / '내-업무-실행법.md').write_text('고객 수정 유지', encoding='utf-8')
before[Path('내-업무-실행법.md')] = (workspace / '내-업무-실행법.md').read_bytes()
again = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-Apply')
check(again.returncode == 0 and '기존 파일 유지' in again.stdout.decode('utf-8') and
      all((workspace / p).read_bytes() == raw for p, raw in before.items()), 'workspace 재실행 기존 파일 유지', again)


def reject_workspace(path, label):
    write_json(profile, dict(data, workspacePath=str(path)))
    result = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
    check(result.returncode != 0 and str(home).encode() not in result.stdout, label, result)


reject_workspace(student / '작업실', 'workspace 학생 폴더 안 거부')
reject_workspace(home, 'workspace 홈 전체 거부')
reject_workspace(home.anchor, 'workspace 드라이브 루트 거부')
outer = home / '보관함'
nested_student = outer / '학생기록'
nested_student.mkdir(parents=True)
write_json(profile, dict(data, studentDataPaths=[str(nested_student)], workspacePath=str(outer)))
r = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(r.returncode != 0, 'workspace 학생 폴더 포함 거부', r)
reject_workspace(str(student).upper() + '/WORK', 'workspace 대소문자 변형 거부')
alias = home / '연결 폴더'
q = lambda x: "'" + str(x).replace("'", "''") + "'"
r = execute(ps + ['-Command', 'New-Item -ItemType Junction -Path '+q(alias)+' -Target '+q(student)+' | Out-Null'])
check(r.returncode == 0, 'workspace junction 시험 준비', r)
reject_workspace(alias / '새 작업실', 'workspace 실제 junction 학생 경로 거부')
write_json(profile, dict(data, studentDataPaths=[str(alias / '아래')], workspacePath=str(student)))
(student / '아래').mkdir()
r = tool('apply-workspace', '-TargetHome', home, '-ProfilePath', profile, '-DryRun')
check(r.returncode != 0, 'workspace 학생 alias 반대 포함관계 거부', r)

# 한글·공백 로컬 파일을 실제 Edge로 렌더한다. 기존 브라우저 프로필은 사용하지 않는다.
pdf_dir = run / '한글 공백 PDF'
pdf_dir.mkdir()
html, pdf = pdf_dir / '시험 자료.html', pdf_dir / '시험 결과.pdf'
html.write_text('''<!doctype html><meta charset="utf-8"><style>
@page{size:A4;margin:20mm}body{font-family:Arial,sans-serif}section{break-after:page}
section:last-child{break-after:auto}</style><section><h1>한글 첫째 쪽</h1><p>학원 시험 자료</p></section>
<section><h1>한글 둘째 쪽</h1><p>답안 확인</p></section>''', encoding='utf-8')
edge = next((Path(os.environ[k]) / 'Microsoft/Edge/Application/msedge.exe' for k in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')
             if k in os.environ and (Path(os.environ[k]) / 'Microsoft/Edge/Application/msedge.exe').is_file()), None)
if edge:
    start = time.monotonic()
    rendered = tool('ek-pdf', '-Html', html, '-Pdf', pdf, extra={'EK_PDF_BROWSER': str(edge)})
    check(rendered.returncode == 0 and pdf.is_file() and len(re.findall(rb'/Type\s*/Page\b', pdf.read_bytes())) == 2,
          f'Edge 실제 PDF 2쪽 (한글·공백 경로, {time.monotonic()-start:.1f}초)', rendered)
    original = pdf.read_bytes()
    refused = tool('ek-pdf', '-Html', html, '-Pdf', pdf)
    check(refused.returncode != 0 and pdf.read_bytes() == original, 'PDF 기존 출력 덮어쓰기 거부', refused)
    check(not list(Path(env['TEMP']).glob('ek-pdf-*')), 'PDF 임시 브라우저 프로필 정리')
else:
    print('SKIP Edge 없음: 실제 PDF 렌더')
    pdf.write_bytes(b'original')
    check(tool('ek-pdf', '-Html', html, '-Pdf', pdf).returncode != 0, 'PDF 기존 출력 덮어쓰기 거부')
missing = tool('ek-pdf', '-Html', html, '-Pdf', pdf_dir / '없는 브라우저.pdf', extra={'EK_PDF_BROWSER': str(run / 'missing.exe')})
check(missing.returncode == 2 and '인쇄→PDF로 저장' in missing.stdout.decode('utf-8'), 'PDF 브라우저 없음 종료 2', missing)

hwpx, out = run / '합성.hwpx', run / '합성.txt'
ns = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
with zipfile.ZipFile(hwpx, 'w', zipfile.ZIP_DEFLATED) as z:
    for n in (10, 1, 0):
        z.writestr(f'Contents/section{n}.xml', f'<root xmlns:hp="{ns}"><hp:p><hp:run><hp:t>본문{n}</hp:t><hp:t> 끝</hp:t></hp:run></hp:p></root>')
result = tool('ek-hwpx-text', '-Hwpx', hwpx, '-Out', out)
check(result.returncode == 0 and out.read_text(encoding='utf-8-sig').splitlines() == ['본문0 끝', '본문1 끝', '본문10 끝'],
      'HWPX section0·1·10 숫자순·문단 텍스트', result)
check(tool('ek-hwpx-text', '-Hwpx', hwpx, '-Out', out).returncode != 0, 'HWPX 기존 결과 덮어쓰기 거부')
ole = run / '구형.hwp'
ole.write_bytes(bytes.fromhex('D0CF11E0') + b'\0' * 12)
result = tool('ek-hwpx-text', '-Hwpx', ole, '-Out', run / 'ole.txt')
check(result.returncode == 2 and not (run / 'ole.txt').exists(), 'HWP OLE 안내 종료 2', result)
oversize = run / '큰.hwpx'
with zipfile.ZipFile(oversize, 'w', zipfile.ZIP_DEFLATED) as z:
    with z.open('Contents/section0.xml', 'w') as f:
        for _ in range(51):
            f.write(b'x' * 1024 * 1024)
check(tool('ek-hwpx-text', '-Hwpx', oversize, '-Out', run / 'oversize.txt').returncode != 0 and
      not (run / 'oversize.txt').exists(), 'HWPX 압축 내부 합 50MB 초과 거부')

# PATH 앞에 가짜 CLI만 놓고 인자·stdin·종료 코드를 확인한다.
fakebin = run / 'fake-bin'
fakebin.mkdir()
record, prompt_record = run / 'codex-args.json', run / 'codex-stdin.txt'
stub = fakebin / 'fake-codex.py'
stub.write_text('''import json, os, sys, time
from pathlib import Path
Path(os.environ['EK_FAKE_ARGS']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
Path(os.environ['EK_FAKE_STDIN']).write_bytes(sys.stdin.buffer.read())
code = int(os.environ.get('EK_FAKE_EXIT', '0'))
if code: sys.exit(code)
if os.environ.get('EK_FAKE_BARRIER'):
    barrier=Path(os.environ['EK_FAKE_BARRIER'])
    (barrier / str(os.getpid())).touch()
    deadline=time.monotonic()+10
    while len(list(barrier.iterdir()))<2:
        if time.monotonic()>deadline: sys.exit(9)
        time.sleep(.02)
Path(sys.argv[sys.argv.index('-o')+1]).write_text(os.environ.get('EK_FAKE_TEXT','더미 검토 결과'), encoding='utf-8')
''', encoding='utf-8', newline='\n')
(fakebin / 'codex.cmd').write_text('@"'+sys.executable+'" "%~dp0fake-codex.py" %*\r\n', encoding='utf-8')
fakeenv = {'PATH': str(fakebin)+os.pathsep+env['PATH'], 'EK_FAKE_ARGS': str(record), 'EK_FAKE_STDIN': str(prompt_record)}
brief, review_out = workspace / '검토/검토 요청.md', workspace / '검토/검토 결과.md'
brief.write_text('목표: 더미 문서 검토\n금지: 학생정보·비밀값\n', encoding='utf-8')
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', review_out, extra=fakeenv)
check(result.returncode == 0 and review_out.exists() and record.exists(), 'Codex 가짜 CLI 실행 성공', result)
arguments = json.loads(record.read_text(encoding='utf-8-sig'))
check(arguments[:10] == ['exec', '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral', '--color', 'never', '-C', str(workspace), '-o'] and
      Path(arguments[10]).parent.parent == workspace / '검토' and arguments[11:] == ['-'] and
      prompt_record.read_text(encoding='utf-8-sig').strip() == brief.read_text(encoding='utf-8-sig').strip(), 'Codex read-only 고정 인자·위험 옵션 0·한국어 stdin')
before = review_out.read_bytes()
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', review_out, extra=fakeenv).returncode != 0 and
      review_out.read_bytes() == before, 'Codex 결과 덮어쓰기 거부')
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '결과/밖.md', extra=fakeenv).returncode != 0, 'Codex 검토 밖 출력 거부')
outside_brief = workspace / '입력/밖.md'
outside_brief.write_text('범위 밖', encoding='utf-8')
check(tool('ek-codex-review', '-Workspace', workspace, '-Brief', outside_brief, '-Out', workspace / '검토/새.md', extra=fakeenv).returncode != 0, 'Codex 검토 밖 브리프 거부')
linked = workspace / '검토/연결'
r = execute(ps + ['-Command', 'New-Item -ItemType Junction -Path '+q(linked)+' -Target '+q(workspace / '결과')+' | Out-Null'])
check(r.returncode == 0 and tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', linked / '유출.md', extra=fakeenv).returncode != 0, 'Codex 실제 junction 경계 거부')
# npm 설치의 codex.ps1처럼 파이프 입력일 때만 stdin을 넘기는 실행기에서도 브리프가 전달되는지 확인한다.
shimbin = run / 'fake-shim-bin'
shimbin.mkdir()
(shimbin / 'codex.ps1').write_text('if ($args.Count -eq 1 -and $args[0] -is [array]) { exit 9 }\r\nif ($MyInvocation.ExpectingInput) { $input | & '+q(Path(sys.executable))+' '+q(stub)+' @args } else { & '+q(Path(sys.executable))+' '+q(stub)+' @args }\r\nexit $LASTEXITCODE\r\n', encoding='utf-8-sig')
shim_stdin = run / 'codex-shim-stdin.txt'
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/shim 결과.md',
              extra=dict(fakeenv, PATH=str(shimbin)+os.pathsep+env['PATH'], EK_FAKE_STDIN=str(shim_stdin)))
check(result.returncode == 0 and shim_stdin.exists() and
      shim_stdin.read_text(encoding='utf-8-sig').strip() == brief.read_text(encoding='utf-8-sig').strip(), 'Codex ps1 실행기(npm)에도 한국어 브리프 stdin 전달', result)
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/실패.md', extra=dict(fakeenv, EK_FAKE_EXIT='7'))
check(result.returncode == 7, 'Codex 종료 코드 7 전달', result)
result = tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', workspace / '검토/미설치.md', extra={'PATH': str(Path(ps[0]).parent)})
check(result.returncode == 2, 'Codex 미설치 종료 2', result)
barrier = run / 'race-barrier'
barrier.mkdir()
race_out = workspace / '검토/동시 결과.md'
def race(label):
    return tool('ek-codex-review', '-Workspace', workspace, '-Brief', brief, '-Out', race_out,
                extra=dict(fakeenv, EK_FAKE_BARRIER=str(barrier), EK_FAKE_TEXT=label,
                           EK_FAKE_ARGS=str(run / ('race-'+label+'.json')), EK_FAKE_STDIN=str(run / ('race-'+label+'.txt'))))
with ThreadPoolExecutor(max_workers=2) as pool:
    concurrent = list(pool.map(race, ('A', 'B')))
check(sorted(p.returncode for p in concurrent) == [0, 1] and race_out.read_text(encoding='utf-8-sig') in ('A','B') and
      not list((workspace / '검토').glob('.ek-review-*')), 'Codex 동시 실행 1개만 결과 생성·덮어쓰기 0·임시 정리')

for payload, expected in [
    ({'model': {'display_name': 'Opus 5.5'}, 'workspace': {'current_dir': 'D:/업무/AI작업실'},
      'context_window': {'used_percentage': 12}, 'rate_limits': {'five_hour': {'used_percentage': 23}}}, 'Opus 5.5 · AI작업실 · 대화 12% · 5시간 23%'),
    ({}, 'AI 작업실'), (b'{broken', 'AI 작업실'),
    ({'model': {'display_name': 'Opus 5.5'}, 'context_window': {'used_percentage': 0}}, 'Opus 5.5 · 대화 0%')]:
    result = tool('statusline', input=payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    check(result.returncode == 0 and result.stdout.decode('utf-8-sig').strip() == expected, '상태줄 전체/없음/깨짐/0% 기대 출력·종료0', result)

# 부트스트랩 공식 설치 호출을 가짜 다운로드로 바꾸고 exit 격리를 실제 하위 프로세스로 확인한다.
for fail in (False, True):
    fixture = run / ('bootstrap-fail' if fail else 'bootstrap-ok')
    fixture.mkdir()
    ready = fixture / 'ready'
    claude = fixture / 'claude.cmd'
    claude.write_text('@echo fake Claude\r\n', encoding='utf-8')
    codex = fixture / 'codex.cmd'
    codex.write_text('@echo codex 0.99.0\r\n@exit /b 0\r\n', encoding='utf-8')
    installer = fixture / 'installer.ps1'
    installer.write_text(('exit 7\n' if fail else "[IO.File]::WriteAllText("+q(ready)+",'ready'); exit 0\n"), encoding='utf-8-sig')
    runner = fixture / 'runner.ps1'
    runner.write_text('. '+q(root / 'bootstrap/bootstrap.ps1')+' -Library\n'+'''
function Get-Command { param($Name,$CommandType,$ErrorAction)
    if($Name -eq 'codex') { if(Test-Path -LiteralPath READY) { return [pscustomobject]@{Source=CODEX} }; return $null }
    Microsoft.PowerShell.Core\\Get-Command @PSBoundParameters
}
function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec)
    if($Uri -ne 'https://chatgpt.com/codex/install.ps1'){throw '잘못된 공식 URL'}
    Copy-Item -LiteralPath INSTALLER -Destination $OutFile
}
$ok=Invoke-EkCodexInstall -TargetHome FIXTURE -KitRoot FIXTURE
if($ok -ne EXPECTED){throw '예상 결과 불일치'}
if(-not(Test-Path -LiteralPath CLAUDE)){throw 'Claude 보존 실패'}
Write-Output 'PARENT_CONTINUED'
'''.replace('READY', q(ready)).replace('CODEX', q(codex)).replace('INSTALLER', q(installer)).replace('FIXTURE', q(fixture)).replace('EXPECTED', '$false' if fail else '$true').replace('CLAUDE', q(claude)), encoding='utf-8-sig', newline='\r\n')
    result = execute(ps + ['-File', str(runner)])
    check(result.returncode == 0 and b'PARENT_CONTINUED' in result.stdout and (ready.exists() != fail),
          'bootstrap Codex '+('실패 Claude 보존·exit 격리' if fail else '설치 성공·PATH/버전 확인·exit 격리'), result)

skills = sorted(p.parent.name for p in (root / 'plugins/ek-workroom/skills').glob('*/SKILL.md'))
expected = sorted(('ek-start ek-safety ek-mode ek-codex-link ek-flow ek-handoff cross-check worksheet-pdf lesson-slides hwpx-read parent-message spreadsheet-check korean-review explanation-draft question-draft blog-column').split())
check(skills == expected, '스킬 정확히 16개 정합')
blocked = ['offline'+'-spacing', 'scan'+'-cleanup', 'blog'+'-copy', 'director'+'-column', 'hwp'+'-convert',
           'kit/'+'ek-setup', 'Wa'+'rp', 'cs'+'wap', 'account'+'Label', 'selected'+'Skills', 'kor'+'doc', 'kiwi'+'piepy', 'Every'+'thing', 'VS'+' Code']
history = {'docs/review-v0.1-response.md', 'docs/validation-report.md', 'docs/validation-v0.1.1.md'}
listing = execute(['git', 'ls-files', '-co', '--exclude-standard', '-z']).stdout.decode('utf-8')
violations = []
for name in set(listing.split('\0')) - {''}:
    path = root / name
    if name in history or not path.is_file() or path.suffix not in ('.md', '.json', '.ps1', '.sh', '.py', '.txt'):
        continue
    text = path.read_text(encoding='utf-8-sig')
    for word in blocked:
        if word.lower() in text.lower():
            violations.append(name + ': ' + word)
check(not violations, '삭제 대상 참조 0 (이력 3개 제외): ' + ', '.join(violations))
print('v0.2.0 실행 도구 검사 완료')
