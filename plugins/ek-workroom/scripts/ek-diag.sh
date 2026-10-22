#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
source "$script_dir/common.sh"
if ! ek_require_python; then
  printf '%s\n' 'python3: 없음(설치 필요)'
  exit 4
fi
exec "$EK_PYTHON" "$script_dir/ek_engine.py" ek-diag "$@"
