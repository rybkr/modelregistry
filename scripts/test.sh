#!/usr/bin/env bash

set -e

mkdir -p test

JUNIT="test/_junit.xml"
COV="test/_coverage.xml"
echo "[test] running: python3 -m pytest --junitxml=$JUNIT --cov=src --cov-report=xml:$COV -q"

set +e
python3 -m pytest "--junitxml=$JUNIT" --cov=src "--cov-report=xml:$COV" -q
PYTEST_RC=$?
set -e

SCRIPTS_DIR="$(dirname "$0")"
python3 "$SCRIPTS_DIR/print_test_summary.py" "$PYTEST_RC" "$JUNIT" "$COV"
