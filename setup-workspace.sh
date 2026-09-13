#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
command -v uv >/dev/null || { echo 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ and retry.' >&2; exit 2; }
exec uv run --project tools/workspace --locked python tools/setup_workspace.py "$@"
