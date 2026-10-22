#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
source "$script_dir/common.sh"
ek_require_python || exit 4
exec "$EK_PYTHON" "$script_dir/ek_engine.py" apply-workspace "$@"
