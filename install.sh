#!/usr/bin/env bash
set -u

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if command -v python3 >/dev/null 2>&1; then PYTHON=python3
elif command -v python >/dev/null 2>&1; then PYTHON=python
else printf 'Cannot install yet: Python 3 is required.\n'; exit 2
fi
exec "$PYTHON" "$SOURCE_ROOT/.agents/zzzops/installer.py" "$@"
