#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC_DIR="${STATIC_DIR:-${ROOT}/static}"

python3 "${ROOT}/actions/validate_site.py" --root "${STATIC_DIR}"
