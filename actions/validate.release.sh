#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

[[ -z "$(git status --short)" ]] || { printf '[validate.release][FAIL] working tree is not clean\n' >&2; exit 1; }
[[ -s RELEASE_NOTES.md ]] || { printf '[validate.release][FAIL] missing release notes\n' >&2; exit 1; }
[[ ! -e static ]] || { printf '[validate.release][FAIL] generated static/ must not be tracked or retained for release review\n' >&2; exit 1; }
git diff --check HEAD
bash actions/check.sh
printf '[validate.release][PASS] release source contract\n'
