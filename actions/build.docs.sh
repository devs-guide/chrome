#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE=""
OUTPUT=""
SITE_OUTPUT_ROOT=""
EXTRA_ARGS=()

while (($#)); do
  case "$1" in
    --source) SOURCE="${2:?--source requires a directory}"; shift 2 ;;
    --output) OUTPUT="${2:?--output requires a directory}"; shift 2 ;;
    --site-output-root) SITE_OUTPUT_ROOT="${2:?--site-output-root requires a directory}"; shift 2 ;;
    --readmes-only|--preserve-index) EXTRA_ARGS+=("$1"); shift ;;
    *) printf '[build.docs][error] unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ -n "${SOURCE}" && -n "${OUTPUT}" && -n "${SITE_OUTPUT_ROOT}" ]] || {
  printf '[build.docs][error] --source, --output, and --site-output-root are required\n' >&2
  exit 2
}

if ((${#EXTRA_ARGS[@]})); then
  python3 "${ROOT}/actions/render_docs.py" \
    --source "${SOURCE}" \
    --output "${OUTPUT}" \
    --site-output-root "${SITE_OUTPUT_ROOT}" \
    "${EXTRA_ARGS[@]}"
else
  python3 "${ROOT}/actions/render_docs.py" \
    --source "${SOURCE}" \
    --output "${OUTPUT}" \
    --site-output-root "${SITE_OUTPUT_ROOT}"
fi
