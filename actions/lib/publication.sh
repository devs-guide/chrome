#!/usr/bin/env bash

if [[ -z "${ROOT:-}" ]]; then
  printf '[publication][error] ROOT must be set before sourcing publication.sh\n' >&2
  return 1 2>/dev/null || exit 1
fi

: "${PUBLICATION_LABEL:=publication}"

publication.error() {
  printf '[%s][error] %s\n' "${PUBLICATION_LABEL}" "$*" >&2
}

publication.relative.is_safe() {
  local path="${1:-}"
  local segment=""
  local -a segments=()

  [[ -n "${path}" && "${path}" != /* && "${path}" != */ && "${path}" != *'//'* \
    && "${path}" != *$'\n'* && "${path}" != *$'\r'* && "${path}" != *'|'* \
    && "${path}" != *[[:space:]]* ]] || return 1

  IFS='/' read -r -a segments <<< "${path}"
  ((${#segments[@]} > 0)) || return 1
  for segment in "${segments[@]}"; do
    [[ "${segment}" =~ ^[A-Za-z0-9][A-Za-z0-9._+@-]*$ ]] || return 1
    [[ "${segment}" != . && "${segment}" != .. ]] || return 1
  done
}

publication.manifest.validate() {
  local manifest="${1:-}"
  local line_number=0 kind="" source="" destination="" extra=""
  local source_path="" seen_sources='|' seen_destinations='|'

  [[ -s "${manifest}" ]] || {
    publication.error "manifest is missing or empty: ${manifest:-unset}"
    return 1
  }

  while IFS='|' read -r kind source destination extra || [[ -n "${kind}${source}${destination}${extra}" ]]; do
    line_number=$((line_number + 1))
    destination="${destination%$'\r'}"
    [[ -n "${kind}${source}${destination}${extra}" && "${kind}" != \#* ]] || continue

    [[ -z "${extra}" && -n "${kind}" && -n "${source}" && -n "${destination}" ]] || {
      publication.error "invalid field count at ${manifest}:${line_number}"
      return 1
    }
    case "${kind}" in
      file|tree|docs) ;;
      *) publication.error "unsupported type at ${manifest}:${line_number}: ${kind}"; return 1 ;;
    esac
    publication.relative.is_safe "${source}" || {
      publication.error "unsafe source at ${manifest}:${line_number}: ${source}"
      return 1
    }
    if [[ "${destination}" != . ]]; then
      publication.relative.is_safe "${destination}" || {
        publication.error "unsafe destination at ${manifest}:${line_number}: ${destination}"
        return 1
      }
    elif [[ "${kind}|${source}" != 'tree|www' ]]; then
      publication.error "only tree|www may publish to the artifact root"
      return 1
    fi
    [[ "${seen_sources}" != *"|${source}|"* ]] || {
      publication.error "duplicate source at ${manifest}:${line_number}: ${source}"
      return 1
    }
    [[ "${seen_destinations}" != *"|${destination}|"* ]] || {
      publication.error "duplicate destination at ${manifest}:${line_number}: ${destination}"
      return 1
    }

    source_path="${ROOT}/${source}"
    case "${kind}" in
      file)
        [[ -f "${source_path}" && -s "${source_path}" && ! -L "${source_path}" ]] || {
          publication.error "file source is missing, empty, or a symlink: ${source}"
          return 1
        }
        ;;
      tree|docs)
        [[ -d "${source_path}" && ! -L "${source_path}" ]] || {
          publication.error "directory source is missing or a symlink: ${source}"
          return 1
        }
        [[ -z "$(find "${source_path}" -type l -print -quit)" ]] || {
          publication.error "source contains a symlink: ${source}"
          return 1
        }
        [[ -z "$(find "${source_path}" -type f ! -size +0 -print -quit)" ]] || {
          publication.error "source contains an empty file: ${source}"
          return 1
        }
        ;;
    esac
    seen_sources="${seen_sources}${source}|"
    seen_destinations="${seen_destinations}${destination}|"
  done < "${manifest}"

  [[ "${seen_sources}" != '|' ]] || {
    publication.error 'manifest contains no entries'
    return 1
  }
}

publication.manifest.each() {
  local manifest="${1:-}" callback="${2:-}"
  local kind="" source="" destination="" extra=""

  publication.manifest.validate "${manifest}" || return 1
  [[ "${callback}" =~ ^[A-Za-z_][A-Za-z0-9_.]*$ ]] && declare -F "${callback}" >/dev/null || {
    publication.error "callback is unavailable: ${callback:-unset}"
    return 1
  }

  while IFS='|' read -r kind source destination extra || [[ -n "${kind}${source}${destination}${extra}" ]]; do
    destination="${destination%$'\r'}"
    [[ -n "${kind}${source}${destination}${extra}" && "${kind}" != \#* ]] || continue
    "${callback}" "${kind}" "${source}" "${destination}"
  done < "${manifest}"
}

publication.output.resolve() {
  local requested="${1:-}" base="${2:-${ROOT}}"
  python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[2], sys.argv[1]).resolve() if not pathlib.Path(sys.argv[1]).is_absolute() else pathlib.Path(sys.argv[1]).resolve())' "${requested}" "${base}"
}

publication.output.is_safe() {
  local output="${1:-}" root_real="" home_real=""
  [[ "${output}" == /* ]] || return 1
  root_real="$(cd "${ROOT}" && pwd -P)"
  if [[ -n "${HOME:-}" && -d "${HOME}" ]]; then
    home_real="$(cd "${HOME}" && pwd -P)"
  fi
  [[ "${output}" != / && "${output}" != /tmp && "${output}" != /private/tmp \
    && "${output}" != "${root_real}" && "${output}" != "${root_real}/.git" \
    && "${output}" != "${root_real}/.github" ]] || return 1
  [[ -z "${home_real}" || "${output}" != "${home_real}" ]] || return 1
  case "${output}" in
    "${root_real}"/*) [[ "${output}" == "${root_real}/static" ]] || return 1 ;;
  esac
}
