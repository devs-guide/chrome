#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLICATION_LABEL="test.publication-manifest"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/chrome-manifest.XXXXXX")"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT

# shellcheck source=actions/lib/publication.sh
source "${ROOT}/actions/lib/publication.sh"

publication.manifest.validate "${ROOT}/actions/publication.manifest"

cp "${ROOT}/actions/publication.manifest" "${TEMP_DIR}/duplicate.manifest"
printf 'file|LICENSE|LICENSE-COPY\n' >> "${TEMP_DIR}/duplicate.manifest"
if publication.manifest.validate "${TEMP_DIR}/duplicate.manifest" >/dev/null 2>&1; then
  printf '[test.publication-manifest][FAIL] duplicate source was accepted\n' >&2
  exit 1
fi

printf 'file|../secret|secret\n' > "${TEMP_DIR}/unsafe.manifest"
if publication.manifest.validate "${TEMP_DIR}/unsafe.manifest" >/dev/null 2>&1; then
  printf '[test.publication-manifest][FAIL] unsafe source was accepted\n' >&2
  exit 1
fi

printf 'file|missing.file|missing.file\n' > "${TEMP_DIR}/missing.manifest"
if publication.manifest.validate "${TEMP_DIR}/missing.manifest" >/dev/null 2>&1; then
  printf '[test.publication-manifest][FAIL] missing source was accepted\n' >&2
  exit 1
fi

printf '[test.publication-manifest][PASS] manifest rejects unsafe input\n'
