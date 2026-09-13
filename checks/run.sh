#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/code/llama-receipts/.venv/bin/python}"
if [ -n "${API_PYTHON:-}" ]; then
    "$API_PYTHON" -c 'import fastapi, python_multipart' || { echo 'API_PYTHON must name a Python runtime with fastapi and python-multipart installed.' >&2; exit 2; }
    API_RUN=("$API_PYTHON")
elif "$PYTHON" -c 'import fastapi, python_multipart' 2>/dev/null; then
    API_RUN=("$PYTHON")
elif command -v uv >/dev/null; then
    echo 'Running API checks with temporary uv dependencies (fastapi, python-multipart).'
    API_RUN=(uv run --no-project --with fastapi --with python-multipart python)
else
    echo 'Install uv for automatic API dependencies, or set API_PYTHON to a runtime with fastapi and python-multipart.' >&2
    exit 2
fi
"$PYTHON" -m pytest -q code/llama-receipts
node checks/check_groth16.cjs
"$PYTHON" checks/check_core.py
"${API_RUN[@]}" checks/check_api.py
"${API_RUN[@]}" checks/check_workspace.py

"$PYTHON" checks/check_setup.py
"$PYTHON" checks/check_site_supply.py
node research/complete-operation/check_package.cjs research/complete-operation/results/2026-09-13/operation.proof.json research/complete-operation/results/2026-09-13/registry
