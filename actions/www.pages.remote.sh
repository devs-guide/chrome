#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://devs-guide.github.io/chrome}"
EXPECTED_SHA="${EXPECTED_SHA:?EXPECTED_SHA is required}"
CACHE_BUSTER="${CACHE_BUSTER:-$(date +%s)}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/chrome-pages-remote.XXXXXX")"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT

BASE_URL="${BASE_URL%/}"
mkdir -p "${TEMP_DIR}/meta" "${TEMP_DIR}/web/touch"
curl -fsSL "${BASE_URL}/meta/publication.json?v=${CACHE_BUSTER}" -o "${TEMP_DIR}/meta/publication.json"
curl -fsSL "${BASE_URL}/meta/checksums.sha256?v=${CACHE_BUSTER}" -o "${TEMP_DIR}/meta/checksums.sha256"
curl -fsSL "${BASE_URL}/index.html?v=${CACHE_BUSTER}" -o "${TEMP_DIR}/index.html"
curl -fsSL "${BASE_URL}/web/touch/index.html?v=${CACHE_BUSTER}" -o "${TEMP_DIR}/web/touch/index.html"

python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); expected=sys.argv[2]; actual=data.get("sourceSha"); raise SystemExit(0 if actual == expected else f"expected sourceSha {expected}, found {actual}")' "${TEMP_DIR}/meta/publication.json" "${EXPECTED_SHA}"

python3 - "${TEMP_DIR}" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
checksums = {}
for line in (root / "meta/checksums.sha256").read_text(encoding="utf-8").splitlines():
    digest, relative = line.split("  ", 1)
    checksums[relative] = digest
for relative in ("meta/publication.json", "index.html", "web/touch/index.html"):
    path = root / relative
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = checksums.get(relative)
    if observed != expected:
        raise SystemExit(f"checksum mismatch for {relative}: {observed} != {expected}")
PY
printf '[www.pages.remote][PASS] %s represents %s\n' "${BASE_URL}" "${EXPECTED_SHA}"
