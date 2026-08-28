#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

required=(
  readme.md LICENSE SECURITY.md RELEASE_NOTES.md .gitignore
  www/index.html www/assets/site.css web/readme.md web/touch/readme.md
  web/touch/index.html web/touch/data/catalog.json web/touch/schema/report.schema.json
  web/touch/schema/catalog.schema.json web/touch/manifest.webmanifest
  web/touch/service-worker.js web/touch/css/app.css web/touch/js/app.js
  web/app/readme.md web/extension/readme.md web/pwa/readme.md web/rtc/readme.md
  web/wasm/readme.md build/readme.md build/source/readme.md docs/readme.md
  actions/publication.manifest actions/www.pages.sh actions/validate.pages.sh
)
for path in "${required[@]}"; do
  [[ -s "${path}" ]] || { printf '[validate.repository][FAIL] missing or empty: %s\n' "${path}" >&2; exit 1; }
done

unexpected_symlink="$(find . -path './.git' -prune -o -path './prompt' -prune -o -path './prompts' -prune -o -path './static' -prune -o -path './.local' -prune -o -type l -print -quit)"
[[ -z "${unexpected_symlink}" ]] || { printf '[validate.repository][FAIL] unexpected symlink: %s\n' "${unexpected_symlink}" >&2; exit 1; }

while IFS= read -r -d '' candidate; do
  if [[ "${candidate}" =~ (^|/)(root-ca|server).*\.key(\.pem)?$ || "${candidate}" =~ \.key(\.pem)?$ ]]; then
    printf '[validate.repository][FAIL] private-key-like tracked/source path found: %s\n' "${candidate}" >&2
    exit 1
  fi
  if grep -Iq . "${candidate}" 2>/dev/null \
    && grep -qE -- '-----BEGIN (RSA |EC )?PRIVATE[[:space:]]KEY-----' "${candidate}"; then
    printf '[validate.repository][FAIL] private-key material found: %s\n' "${candidate}" >&2
    exit 1
  fi
done < <(git ls-files -z --cached --others --exclude-standard)

if grep -RInE --include='*.html' --include='*.js' --include='*.css' \
  "(<script[^>]+src|<link[^>]+stylesheet|@import|from[[:space:]]+['\"])[^[:cntrl:]]*(https?:)?//" \
  web www >/dev/null 2>&1; then
  printf '[validate.repository][FAIL] external runtime dependency found under web/ or www/\n' >&2
  exit 1
fi

while IFS= read -r script; do bash -n "${script}"; done < <(find actions -type f -name '*.sh' | sort)
while IFS= read -r module; do python3 -m py_compile "${module}"; done < <(find actions tools tests -type f -name '*.py' 2>/dev/null | sort)
while IFS= read -r document; do python3 -m json.tool "${document}" >/dev/null; done < <(find web -type f -name '*.json' | sort)
python3 actions/validate_touch.py

printf '[validate.repository][PASS] repository contract\n'
