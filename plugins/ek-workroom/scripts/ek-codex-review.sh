#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3이 없어 이 Mac 스크립트를 실행할 수 없습니다. 설치하지 않고 멈춥니다. 판매자와 대안을 확인하세요.' >&2
  exit 1
fi
exec python3 "$script_dir/ek_engine.py" ek-codex-review "$@"
