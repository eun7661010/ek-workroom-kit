"""읽기 전용 지문. 파일 내용과 경로는 stdout에 출력하지 않는다."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys

home = Path(sys.argv[1])
codex = home / '.codex'
# 설정·인증 파일만 비교한다. ~/.codex 전체(sessions·logs)는 다른 Codex 작업이 계속 써서
# 테스트와 무관하게 바뀐다(2026-10-22 재실행에서 오탐).
files = [home / '.claude/settings.json', home / '.claude.json',
         codex / 'config.toml', codex / 'auth.json', codex / 'AGENTS.md']

def fingerprint(path):
    if not path.exists():
        return str(path.relative_to(home)), 'ABSENT'
    digest = hashlib.sha256()
    try:
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    except OSError as exc:
        # 실행 중인 Codex 잠금·소켓·클라우드 파일을 강제로 열지 않는다.
        # 설정/인증 자체는 지문을 확보하지 못하면 실패시킨다.
        if path in (home / '.claude/settings.json', home / '.claude.json', codex / 'config.toml', codex / 'auth.json'):
            raise
        if not isinstance(exc, PermissionError) and path.suffix != '.sock':
            raise
        stat = path.stat()
        return str(path.relative_to(home)), f'LOCKED-METADATA:{stat.st_size}:{stat.st_mtime_ns}'
    return str(path.relative_to(home)), digest.hexdigest()

with ThreadPoolExecutor(max_workers=8) as pool:
    values = dict(pool.map(fingerprint, files))
Path(sys.argv[2]).write_text(json.dumps(values, sort_keys=True), encoding='utf-8')
print('보호 대상 설정과 Codex 파일 SHA256 기록: ' + str(len(values)) + '개')
locked = sum(x.startswith('LOCKED-METADATA:') for x in values.values())
if locked:
    print('OS가 읽기를 막은 파일·소켓 ' + str(locked) + '개는 크기·수정 시각만 대조합니다. 잠금을 해제하지 않았습니다.')

# 살아 있는 Codex 프로세스의 SQLite WAL/SHM은 테스트 중에도 자체 갱신됩니다.
# 기록은 남기되 설정 불변 판정과 분리합니다. 데이터베이스를 중지하거나 잠그지 않습니다.
# .claude.json은 실행 중인 부모 Claude의 시작 횟수 등 런타임 상태도 저장합니다.
# 명세의 보호 대상 .claude/settings.json은 반드시 protected에 남깁니다.
runtime = {name: value for name, value in values.items()
           if name == '.claude.json' or name.endswith(('.sqlite-wal', '.sqlite-shm'))}
protected = {name: value for name, value in values.items() if name not in runtime}
Path(sys.argv[2] + '.protected').write_text(json.dumps(protected, sort_keys=True), encoding='utf-8')
Path(sys.argv[2] + '.runtime').write_text(json.dumps(runtime, sort_keys=True), encoding='utf-8')
