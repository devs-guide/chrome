#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/chrome-check.XXXXXX")"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT

cd "${ROOT}"
bash actions/validate.repository.sh
bash actions/test.publication-manifest.sh

PUBLISH_DIR="${TEMP_DIR}/first" bash actions/www.pages.sh
STATIC_DIR="${TEMP_DIR}/first" bash actions/validate.pages.sh
PUBLISH_DIR="${TEMP_DIR}/second" bash actions/www.pages.sh

if ! diff -qr "${TEMP_DIR}/first" "${TEMP_DIR}/second"; then
  printf '[check][FAIL] two builds from unchanged source differ\n' >&2
  exit 1
fi
printf '[check][PASS] deterministic static artifact\n'

if [[ -d tests ]]; then
  python3 -m unittest discover -s tests -v
fi

printf '[check][PASS] all local checks\n'
