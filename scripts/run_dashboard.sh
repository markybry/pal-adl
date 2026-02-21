#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-local}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

case "$MODE" in
  local)
    ENV_FILE=.env python -m streamlit run streamlit_app.py
    ;;
  staging)
    ENV_FILE=.env.staging python -m streamlit run streamlit_app.py
    ;;
  *)
    echo "Usage: ./scripts/run_dashboard.sh [local|staging]"
    exit 1
    ;;
esac
