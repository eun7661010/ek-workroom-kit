#!/usr/bin/env bash
# 먼저 메신저 붙여넣기 블록에서 이 파일의 SHA256을 확인합니다.
set -euo pipefail
source_value=''; expected=''; target_home="${HOME:-}"; version='0.2.1'; apply=0; dry_run=0; prepare_only=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) source_value=$2; shift 2 ;;
    --expected-sha256) expected=$2; shift 2 ;;
    --home) target_home=$2; shift 2 ;;
    --version) version=$2; shift 2 ;;
    --apply) apply=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    --prepare-only) prepare_only=1; shift ;;
    *) printf '%s\n' '알 수 없는 옵션입니다.'; exit 2 ;;
  esac
done
[ -n "$source_value" ] && [ -n "$expected" ] && [ -n "$target_home" ] || { printf '%s\n' '키트 위치·SHA256·홈 경로를 확인하세요.'; exit 2; }
command -v python3 >/dev/null 2>&1 || { printf '%s\n' '안전한 압축 검증에 필요한 기존 python3가 없습니다. 설치하지 말고 판매자에게 알려 주세요.'; exit 1; }
[ "$dry_run" -eq 0 ] || apply=0
prepare=$apply; [ "$prepare_only" -eq 0 ] || prepare=1
[ "$dry_run" -eq 0 ] || prepare=0
python3 - "$source_value" "$expected" "$prepare" "$target_home" "$version" "$0" <<'PY'
import hashlib, os, pathlib, re, shutil, stat, sys, tempfile, urllib.request, zipfile
source_value, expected, prepare, home, version, script = sys.argv[1:]
expected = expected.lower(); prepare = prepare == '1'
def stop(message):
    print(message); raise SystemExit(1)
def file_sha(path):
    with open(path, 'rb') as stream:
        return stream_sha(stream)
def stream_sha(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()
def folder_sha(source):
    entries = []; seen = set()
    if source.is_symlink(): stop('연결 폴더는 키트 원본으로 사용할 수 없습니다.')
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if pathlib.Path(root, name).is_symlink(): stop('연결 파일·폴더가 있어 중단합니다.')
        for name in files:
            item = pathlib.Path(root, name); relative = item.relative_to(source).as_posix()
            if not item.is_file() or re.search(r'[\r\n:\\]', relative) or relative.casefold() in seen:
                stop('지원하지 않거나 겹치는 파일 이름입니다.')
            seen.add(relative.casefold()); entries.append((relative, item))
    entries.sort(key=lambda row: row[0].encode('utf-16-be', 'surrogatepass'))
    manifest = ''.join(file_sha(item) + '  ' + name + '\n' for name, item in entries)
    return hashlib.sha256(manifest.encode('utf-8')).hexdigest()
try:
    if not re.fullmatch(r'[a-f0-9]{64}', expected) or not re.fullmatch(r'[A-Za-z0-9._-]+', version):
        stop('SHA256 또는 버전 형식을 확인하세요.')
    # macOS /var·/tmp와 같은 시스템 별칭은 홈 경계에서 정규화합니다.
    base = pathlib.Path(home).resolve() / 'ek-workroom'; destination = base / ('kit-' + version)
    if base.is_symlink(): stop('연결된 설치 경로에는 쓰지 않습니다.')
    if destination.exists() or destination.is_symlink():
        stop('같은 버전의 키트 폴더가 이미 있습니다. 덮어쓰지 않습니다. 기존 경로를 사용하고 판매자에게 문의하세요.')
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.staging-', dir=base) as staging:
        staging = pathlib.Path(staging); snapshot = staging / 'kit.zip'; folder = staging / 'content'; cached_source = source_value
        remote = source_value.startswith('https://')
        source = pathlib.Path(source_value)
        if remote:
            # curl의 HTTPS 전용 리다이렉트 제한을 사용하고 원시 응답은 출력하지 않습니다.
            import subprocess
            result = subprocess.run(['curl', '--proto', '=https', '--proto-redir', '=https', '-fsSL', '--max-time', '60', '--max-filesize', '104857600', source_value, '-o', str(snapshot)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode: stop('키트를 받지 못했습니다. 판매자와 확인하세요.')
        elif '://' in source_value: stop('다운로드 주소는 https만 사용할 수 있습니다.')
        elif source.is_symlink(): stop('연결 파일·폴더는 사용할 수 없습니다.')
        elif source.is_dir():
            if source.resolve() == base or source.resolve() in base.parents:
                stop('키트 원본 폴더 안에 설치 폴더를 만들 수 없습니다. 받은 키트 폴더만 Source로 지정하세요.')
            if folder_sha(source) != expected: stop('SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.')
            shutil.copytree(source, folder)
            if folder_sha(folder) != expected: stop('SHA256이 다릅니다. 복사 중 원본이 바뀌었습니다.')
        elif source.is_file(): shutil.copyfile(source, snapshot)
        else: stop('받은 키트 파일이나 폴더가 없습니다.')
        if snapshot.exists():
            # 같은 열린 snapshot으로 검증하고 추출합니다. 원본은 다시 열지 않습니다.
            with snapshot.open('rb') as stream:
                if stream_sha(stream) != expected: stop('SHA256이 다릅니다. 실행하지 말고 판매자에게 다시 확인하세요.')
                stream.seek(0)
                with zipfile.ZipFile(stream) as archive:
                    infos = archive.infolist(); seen = set()
                    if len(infos) > 10000 or sum(info.file_size for info in infos) > 100 * 1024 * 1024:
                        stop('압축 파일의 항목 수나 압축 해제 크기가 너무 큽니다.')
                    for info in infos:
                        name = info.filename.replace('\\', '/'); key = name.rstrip('/').casefold()
                        mode = (info.external_attr >> 16) & 0xF000
                        if (not name or name.startswith('/') or re.search(r'[:\r\n]', name)
                                or any(part in ('.', '..') for part in name.split('/'))
                                or key in seen or mode == stat.S_IFLNK or info.external_attr & 0x400):
                            stop('안전하지 않거나 중복된 압축 경로입니다.')
                        seen.add(key)
                    if prepare:
                        folder.mkdir()
                        for info in infos:
                            item = folder.joinpath(*info.filename.replace('\\', '/').split('/'))
                            if info.is_dir() or info.filename.endswith(('\\', '/')): item.mkdir(parents=True, exist_ok=True)
                            else:
                                item.parent.mkdir(parents=True, exist_ok=True)
                                with archive.open(info) as src, item.open('xb') as dst: shutil.copyfileobj(src, dst)
                if remote and not prepare:
                    cache = base / ('download-' + expected + '.zip')
                    if cache.exists() or cache.is_symlink():
                        if cache.is_symlink() or file_sha(cache) != expected: stop('SHA256이 다릅니다. 기존 다운로드 파일을 판매자와 확인하세요.')
                    else:
                        stream.seek(0)
                        with cache.open('xb') as out: shutil.copyfileobj(stream, out)
                    cached_source = str(cache)
        print('SHA256 일치: 받은 키트를 확인했습니다.')
        print('키트 고정 위치: ' + str(destination))
        print('세션 플러그인 경로: /plugin marketplace add "' + str(destination) + '"')
        if prepare:
            if not (folder / 'plugins/ek-workroom/scripts/ek-diag.sh').is_file(): stop('키트 구조가 맞지 않습니다. 판매자에게 다시 요청하세요.')
            folder.rename(destination)
        else:
            import shlex
            print('아래 명령은 설치 동의 후에만 실행하세요. 같은 검증 파일을 사용합니다.')
            print('bash ' + shlex.quote(str(pathlib.Path(script).resolve())) + ' --source ' + shlex.quote(cached_source) + ' --expected-sha256 ' + expected + ' --home ' + shlex.quote(home) + ' --version ' + version + ' --apply')
except SystemExit: raise
except Exception:
    stop('검증 또는 준비를 마치지 못했습니다. 설치하지 말고 판매자와 확인하세요.')
PY
printf '%s\n' '[계획 1/4] 받은 키트를 검증하고 버전별 고정 위치에 준비합니다.' \
  '[계획 2/4] Claude Code가 없을 때만 공식 HTTPS 설치 파일을 받아 별도 bash로 실행합니다.' \
  '[계획 3/4] Codex CLI가 없을 때만 공식 HTTPS 설치 파일을 별도 bash로 실행하고 버전을 확인합니다.' \
  '[계획 4/4] 고객 본인이 직접 로그인하고 읽기 전용 진단 파일을 확인합니다. 비밀번호·인증 코드를 전달하지 마세요.' \
  'Node·Python 설치와 업그레이드, 사용자 settings 변경은 하지 않습니다.'
if [ "$prepare_only" -eq 1 ] && [ "$dry_run" -eq 0 ]; then exit 0; fi
if [ "$apply" -ne 1 ]; then printf '%s\n' '[DryRun] 검증과 계획만 마쳤습니다. 설치·압축 해제·설정 변경 없음.'; exit 0; fi
verified_root="$target_home/ek-workroom/kit-$version"
export PATH="$target_home/.local/bin:$PATH"
if ! command -v claude >/dev/null 2>&1; then
  installer=$(mktemp "$verified_root/.claude-install-XXXXXXXX")
  trap 'rm -f -- "$installer"' EXIT
  curl --proto '=https' --proto-redir '=https' -fsSL https://claude.ai/install.sh -o "$installer"
  bash "$installer"
  export PATH="$target_home/.local/bin:$PATH"
else
  printf '%s\n' 'Claude Code가 이미 있어 그대로 사용합니다.'
fi
install_codex() {
  if ! command -v codex >/dev/null 2>&1; then
    installer=$(mktemp "$verified_root/.codex-install-XXXXXXXX") || return 1
    if curl --proto '=https' --proto-redir '=https' -fsSL https://chatgpt.com/codex/install.sh -o "$installer" >/dev/null 2>&1; then
      if bash "$installer" >/dev/null 2>&1; then result=0; else result=$?; fi
    else result=1; fi
    rm -f -- "$installer"
    [ "$result" -eq 0 ] || return "$result"
    export PATH="$target_home/.local/bin:$PATH"
    hash -r
  else
    printf '%s\n' 'Codex CLI가 이미 있어 그대로 사용합니다.'
  fi
  codex --version
}
if install_codex; then
  printf '%s\n' 'Codex CLI 설치 확인 완료. 고객 본인 계정으로 로그인하세요.'
else
  printf '%s\n' 'Codex 설치 미완료: Claude Code는 유지합니다. 판매자와 설치·로그인을 확인하세요.'
fi
printf '%s\n' '새 터미널에서 claude를 열고 고객 본인이 로그인하세요. 브라우저가 안 열리면 표시된 URL을 직접 열고 나온 코드는 본인 Claude 터미널에 붙여 넣으세요. 판매자는 화면 공유를 잠시 멈춥니다.'
bash "$verified_root/plugins/ek-workroom/scripts/ek-diag.sh" --home "$target_home" --output "$target_home/ek-diag.txt"
printf '%s\n' '진단 파일을 직접 읽고 필요한 마스킹을 확인한 뒤 전달하세요. 자동 전송하지 않습니다.'
