#!/usr/bin/env bash
set -u

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        PYTHON=$candidate
        break
    fi
done
[[ -n "$PYTHON" ]] || { printf 'Cannot install yet: Python 3.10 or newer is required.\n'; exit 2; }
exec "$PYTHON" "$SOURCE_ROOT/.agents/zzzops/installer.py" "$@"
