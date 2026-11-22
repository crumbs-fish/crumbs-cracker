#!/usr/bin/env bash
# crumbs 启动器（Linux/macOS）
set -euo pipefail
HERE="$(cd "$(dirname "$BASH_SOURCE")" && pwd)"
exec python3 "$HERE/crumbs_cracker.py" "$@"
