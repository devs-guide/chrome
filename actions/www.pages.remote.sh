#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://devs-guide.github.io/chrome}"
EXPECTED_SHA="${EXPECTED_SHA:?EXPECTED_SHA is required}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/chrome-pages-remote.XXXXXX")"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT

BASE_URL="${BASE_URL%/}"
curl -fsSL "${BASE_URL}/meta/publication.json" -o "${TEMP_DIR}/publication.json"
curl -fsSL "${BASE_URL}/meta/checksums.sha256" -o "${TEMP_DIR}/checksums.sha256"
curl -fsSL "${BASE_URL}/index.html" -o "${TEMP_DIR}/index.html"
curl -fsSL "${BASE_URL}/web/touch/index.html" -o "${TEMP_DIR}/touch.html"

python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); expected=sys.argv[2]; actual=data.get("sourceSha"); raise SystemExit(0 if actual == expected else f"expected sourceSha {expected}, found {actual}")' "${TEMP_DIR}/publication.json" "${EXPECTED_SHA}"

grep -Fq 'meta/publication.json' "${TEMP_DIR}/checksums.sha256"
grep -Fq 'index.html' "${TEMP_DIR}/checksums.sha256"
grep -Fq 'web/touch/index.html' "${TEMP_DIR}/checksums.sha256"
printf '[www.pages.remote][PASS] %s represents %s\n' "${BASE_URL}" "${EXPECTED_SHA}"
