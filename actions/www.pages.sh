#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLICATION_MANIFEST="${ROOT}/actions/publication.manifest"
PUBLICATION_LABEL="www.pages"
PUBLISH_REQUESTED="${DIR_PUBLISH:-${PUBLISH_DIR:-static}}"
PUBLISH_DIR=""

# shellcheck source=actions/lib/publication.sh
source "${ROOT}/actions/lib/publication.sh"

log() { printf '[www.pages] %s\n' "$*" >&2; }

publish.entry() {
  local kind="$1" source="$2" destination="$3"
  local source_path="${ROOT}/${source}" destination_path="${PUBLISH_DIR}/${destination}"
  [[ "${destination}" == . ]] && destination_path="${PUBLISH_DIR}"

  case "${kind}" in
    file)
      mkdir -p "$(dirname "${destination_path}")"
      install -m 0644 "${source_path}" "${destination_path}"
      ;;
    tree)
      mkdir -p "${destination_path}"
      rsync -a --delete "${source_path}/" "${destination_path}/"
      ;;
    docs)
      mkdir -p "${destination_path}"
      bash "${ROOT}/actions/build.docs.sh" \
        --source "${source_path}" \
        --output "${destination_path}" \
        --site-output-root "${PUBLISH_DIR}"
      ;;
  esac
  log "published ${source} -> ${destination} (${kind})"
}

main() {
  publication.manifest.validate "${PUBLICATION_MANIFEST}"
  PUBLISH_DIR="$(publication.output.resolve "${PUBLISH_REQUESTED}" "${ROOT}")"
  publication.output.is_safe "${PUBLISH_DIR}" || {
    log "refusing unsafe output: ${PUBLISH_DIR}"
    exit 1
  }

  rm -rf -- "${PUBLISH_DIR}"
  mkdir -p "${PUBLISH_DIR}"
  publication.manifest.each "${PUBLICATION_MANIFEST}" publish.entry

  bash "${ROOT}/actions/build.docs.sh" \
    --source "${ROOT}/web" \
    --output "${PUBLISH_DIR}/web" \
    --site-output-root "${PUBLISH_DIR}" \
    --readmes-only \
    --preserve-index

  : > "${PUBLISH_DIR}/.nojekyll"

  local source_ref source_sha source_epoch catalog_version
  source_ref="${SOURCE_REF:-$(git -C "${ROOT}" branch --show-current 2>/dev/null || printf unknown)}"
  source_sha="${SOURCE_SHA:-$(git -C "${ROOT}" rev-parse HEAD 2>/dev/null || printf uncommitted)}"
  source_epoch="${SOURCE_DATE_EPOCH:-$(git -C "${ROOT}" show -s --format=%ct HEAD 2>/dev/null || printf 0)}"
  catalog_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["catalogVersion"])' "${ROOT}/web/touch/data/catalog.json")"

  python3 "${ROOT}/actions/write_publication.py" \
    --root "${PUBLISH_DIR}" \
    --repository devs-guide/chrome \
    --source-ref "${source_ref:-unknown}" \
    --source-sha "${source_sha}" \
    --source-date-epoch "${source_epoch}" \
    --release 0.0.1-dev \
    --catalog-version "${catalog_version}"

  log "built deterministic artifact at ${PUBLISH_DIR}"
}

main "$@"
