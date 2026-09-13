#!/bin/bash
# Model-free checks: native integration is a separate required CI job.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p test-results
UV=(uv run --project tools/workspace --locked --group dev)
node checks/check_groth16.cjs
node checks/check_adversarial.cjs > test-results/adversarial.json
"${UV[@]}" python -m pytest -q checks/check_api.py checks/check_workspace.py checks/check_matrix_api.py checks/check_setup.py checks/check_site_supply.py checks/check_measure.py checks/check_core.py::CoreChecks::test_execution_and_shapes_fail_closed checks/check_core.py::CoreChecks::test_registry_only_site_and_missing_key checks/check_core.py::CoreChecks::test_signed_max_and_zero_quantization --cov=site --cov=tools --cov-branch --cov-report=term-missing --cov-report=xml:test-results/coverage.xml --cov-report=json:test-results/coverage.json --junitxml=test-results/portable.xml
node research/complete-operation/check_package.cjs research/complete-operation/results/2026-09-13/operation.proof.json research/complete-operation/results/2026-09-13/registry
