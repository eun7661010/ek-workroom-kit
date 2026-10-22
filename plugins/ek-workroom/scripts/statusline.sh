#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
source "$script_dir/common.sh"
if ! ek_detect_python; then
  printf '%s\n' 'AI 작업실'
  exit 0
fi
exec "$EK_PYTHON" "$script_dir/ek_engine.py" statusline "$@"
