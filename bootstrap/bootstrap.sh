#!/usr/bin/env bash
# 먼저 이 파일의 SHA256을 별도로 전달받은 값과 비교하세요.
set -euo pipefail
source_value=''
expected=''
target_home="${HOME:-}"
apply=0
dry_run=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) [ "$#" -ge 2 ] || exit 2; source_value=$2; shift 2 ;;
    --expected-sha256) [ "$#" -ge 2 ] || exit 2; expected=$2; shift 2 ;;
    --home) [ "$#" -ge 2 ] || exit 2; target_home=$2; shift 2 ;;
    --apply) apply=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    *) printf '%s\n' '알 수 없는 옵션입니다. --source, --expected-sha256, --home, --apply, --dry-run을 사용하세요.'; exit 2 ;;
  esac
done
[ -n "$source_value" ] && [ -n "$expected" ] && [ -n "$target_home" ] || { printf '%s\n' '키트 위치·SHA256·홈 경로를 확인하세요.'; exit 2; }
command -v python3 >/dev/null 2>&1 || { printf '%s\n' '안전한 압축 검증에 필요한 기존 python3가 없습니다. 설치하지 말고 판매자에게 알려 주세요.'; exit 1; }
kit_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
staging=''
source_path=$source_value
case "$source_value" in
  https://*)
    mkdir -p "$kit_root/.tmp"
    staging=$(mktemp -d "$kit_root/.tmp/bootstrap-XXXXXXXX")
    source_path="$staging/kit.zip"
    curl --proto '=https' --proto-redir '=https' -fsSL --max-time 60 --max-filesize 104857600 "$source_value" -o "$source_path" 2>/dev/null || { printf '%s\n' '키트를 받지 못했습니다. 설치하지 말고 판매자와 확인하세요.'; exit 1; }
    ;;
  *://*) printf '%s\n' '다운로드 주소는 https만 사용할 수 있습니다.'; exit 1 ;;
esac
if [ "$dry_run" -eq 1 ]; then apply=0; fi
verified_root=$source_path
if [ "$apply" -eq 1 ] && [ ! -d "$source_path" ]; then
  if [ -z "$staging" ]; then
    mkdir -p "$kit_root/.tmp"
    staging=$(mktemp -d "$kit_root/.tmp/bootstrap-XXXXXXXX")
  fi
  verified_root="$staging/kit"
fi
python3 - "$source_path" "$expected" "$apply" "$verified_root" <<'PY'
import hashlib, os, pathlib, re, stat, sys, zipfile
source = pathlib.Path(sys.argv[1])
expected = sys.argv[2].lower()
apply = sys.argv[3] == '1'
destination = pathlib.Path(sys.argv[4])
def stop(message):
    print(message)
    raise SystemExit(1)
def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()
try:
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        stop('SHA256 형식이 올바르지 않습니다.')
    if source.is_symlink():
        stop('연결 파일·폴더는 사용할 수 없습니다.')
    if source.is_dir():
        entries = []
        seen = set()
        for root, dirs, files in os.walk(source, followlinks=False):
            for name in dirs + files:
                item = pathlib.Path(root, name)
                if item.is_symlink():
                    stop('연결 파일·폴더가 있어 중단합니다.')
            for name in files:
                item = pathlib.Path(root, name)
                if not item.is_file():
                    stop('일반 파일이 아닌 항목이 있습니다.')
                relative = item.relative_to(source).as_posix()
                if re.search(r'[\r\n:\\]', relative) or relative.casefold() in seen:
                    stop('지원하지 않거나 겹치는 파일 이름입니다.')
                seen.add(relative.casefold())
                entries.append((relative, item))
        # UTF-16 코드 단위 순서로 .NET StringComparer.Ordinal과 맞춥니다.
        entries.sort(key=lambda row: row[0].encode('utf-16-be', 'surrogatepass'))
        manifest = ''.join(file_sha(item) + '  ' + name + '\n' for name, item in entries)
        actual = hashlib.sha256(manifest.encode('utf-8')).hexdigest()
    elif source.is_file():
        actual = file_sha(source)
    else:
        stop('받은 키트 파일이나 폴더가 없습니다.')
    if actual != expected:
        stop('SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.')
    if source.is_file():
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(info.file_size for info in infos) > 100 * 1024 * 1024:
                stop('압축 파일의 항목 수나 압축 해제 크기가 너무 큽니다.')
            seen = set()
            for info in infos:
                name = info.filename.replace('\\', '/')
                parts = name.split('/')
                mode = (info.external_attr >> 16) & 0xF000
                key = name.rstrip('/').casefold()
                if (not name or name.startswith('/') or re.search(r'[:\r\n]', name)
                        or any(part in ('.', '..') for part in parts)
                        or key in seen or mode == stat.S_IFLNK or info.external_attr & 0x400):
                    stop('안전하지 않거나 중복된 압축 경로입니다.')
                seen.add(key)
            if apply:
                if destination.exists():
                    stop('압축을 풀 폴더가 이미 있습니다. 새 폴더에서 다시 시작하세요.')
                destination.mkdir(parents=True)
                for info in infos:
                    item = destination.joinpath(*info.filename.replace('\\', '/').split('/'))
                    if info.is_dir() or info.filename.endswith(('\\', '/')):
                        item.mkdir(parents=True, exist_ok=True)
                    else:
                        item.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(info) as stream, item.open('xb') as out:
                            import shutil
                            shutil.copyfileobj(stream, out)
    print('SHA256 일치: 받은 키트를 확인했습니다.')
except Exception:
    stop('검증 또는 준비를 마치지 못했습니다. 설치하지 말고 판매자와 확인하세요.')
PY
printf '%s\n' '[계획 1/3] Claude Code가 없을 때만 공식 설치: curl -fsSL https://claude.ai/install.sh | bash' \
  '[계획 2/3] 고객 본인의 유료 계정으로 claude를 열고 직접 로그인합니다. 비밀번호·인증 코드를 전달하지 마세요.' \
  '[계획 3/3] 읽기 전용 진단으로 ek-diag.txt를 만듭니다. 보내기 전에 직접 읽어 보세요.' \
  'Node·Python 설치와 업그레이드, 사용자 settings 변경은 하지 않습니다.'
if [ "$apply" -ne 1 ]; then printf '%s\n' '[DryRun] 검증과 계획만 마쳤습니다. 설치·압축 해제·설정 변경 없음.'; exit 0; fi
[ -f "$verified_root/plugins/ek-workroom/scripts/ek-diag.sh" ] || { printf '%s\n' '키트 구조가 맞지 않습니다. 판매자에게 다시 요청하세요.'; exit 1; }
if ! command -v claude >/dev/null 2>&1; then
  curl --proto '=https' --proto-redir '=https' -fsSL https://claude.ai/install.sh | bash
else
  printf '%s\n' 'Claude Code가 이미 있어 그대로 사용합니다.'
fi
printf '%s\n' '새 터미널에서 claude를 열고 고객 본인이 로그인하세요. 판매자는 자리를 비우거나 화면 공유를 잠시 멈춥니다.'
bash "$verified_root/plugins/ek-workroom/scripts/ek-diag.sh" --home "$target_home" --output "$target_home/ek-diag.txt"
printf '%s\n' '진단 파일을 직접 읽고 필요한 마스킹을 확인한 뒤 전달하세요. 자동 전송하지 않습니다.'
