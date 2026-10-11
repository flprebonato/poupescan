#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
    echo 'O deploy requer Python 3.10+ no host (além de Bash e Docker Compose).' >&2
    exit 1
fi
exec python3 -m scripts.deploy "$@"
