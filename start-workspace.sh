#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
command -v uv >/dev/null || { echo 'Install uv, then run ./start-workspace.sh again.' >&2; exit 2; }
uv run --no-project python site/build_site.py
exec uv run --no-project --with fastapi --with uvicorn --with numpy python site/local_prover.py "$@"
