#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' '상태줄: Python 3 없음. /status에서 모델과 계정을 확인하세요.'
  exit 0
fi
exec python3 "$script_dir/ek_engine.py" statusline "$@"
