#!/usr/bin/env bash
# code-checks.sh - lint, security scan and unit tests for ONE app component.
#
#   bash ci/code-checks.sh backend
#   bash ci/code-checks.sh frontend
#
# Runs inside a throwaway python:3.12-slim container: the same Python as the
# app images, and nothing installed on the CI server itself.
#   - the source code is mounted READ-ONLY (the checks can't change it)
#   - the container runs as the calling user (no root-owned files left behind)
#   - test results go to reports/<component>-tests.xml (shown by Jenkins)
set -euo pipefail

COMPONENT="${1:?usage: code-checks.sh <backend|frontend>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/reports"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env COMPONENT="$COMPONENT" \
  --volume "$ROOT/app:/src:ro" \
  --volume "$ROOT/reports:/reports" \
  --workdir "/src/$COMPONENT" \
  python:3.12-slim \
  bash -euo pipefail -c '
    python -m venv /tmp/venv
    . /tmp/venv/bin/activate
    pip install --quiet --disable-pip-version-check \
      -r requirements.txt -r ../requirements-dev.txt

    echo "=== [$COMPONENT] Ruff - lint ==="
    ruff check --no-cache --config ../ruff.toml .

    echo "=== [$COMPONENT] Bandit - security scan of the code ==="
    bandit -q -r . -x ./tests

    echo "=== [$COMPONENT] pytest - unit tests ==="
    python -m pytest -q -p no:cacheprovider \
      --junitxml="/reports/$COMPONENT-tests.xml" tests
  '

