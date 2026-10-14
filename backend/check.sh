#!/bin/sh
# Run every backend check: formatting, lint, type checks and tests.
set -eu
echo "== ruff format" && ruff format --check .
echo "== ruff check" && ruff check .
echo "== mypy" && mypy .
echo "== pytest" && pytest "$@"
