#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
TS="${2:-}"
BACKUP_DIR="${BACKUP_DIR:-backups/preprod}"
FILES_ARCHIVE_PREFIX="${FILES_ARCHIVE_PREFIX:-preprod-files}"
REDIS_DUMP_PREFIX="${REDIS_DUMP_PREFIX:-preprod-redis}"
REDIS_PATTERN="${REDIS_PATTERN:-preprod:*}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/preprod/backup_restore.sh backup
  bash scripts/preprod/backup_restore.sh restore <timestamp>
  bash scripts/preprod/backup_restore.sh verify <timestamp>

Notes:
  - restore requires ALLOW_DATA_MUTATION=1
  - backup/verify require ENVIRONMENT_ROLE=preprod
EOF
}

require_preprod_role() {
  if [ "${ENVIRONMENT_ROLE:-}" != "preprod" ]; then
    echo "❌ ENVIRONMENT_ROLE musi być ustawione na 'preprod'."
    exit 1
  fi
}

require_mutation_override() {
  if [ "${ALLOW_DATA_MUTATION:-0}" != "1" ]; then
    echo "❌ Restore wymaga ALLOW_DATA_MUTATION=1."
    exit 1
  fi
}

create_files_backup() {
  local ts="$1"
  local archive="${BACKUP_DIR}/${FILES_ARCHIVE_PREFIX}-${ts}.tar.gz"
  mkdir -p "${BACKUP_DIR}"
  mkdir -p \
    data/memory/preprod \
    data/training/preprod \
    data/timelines/preprod \
    data/synthetic_training/preprod \
    workspace/preprod

  tar -czf "${archive}" \
    data/memory/preprod \
    data/training/preprod \
    data/timelines/preprod \
    data/synthetic_training/preprod \
    workspace/preprod

  sha256sum "${archive}" > "${archive}.sha256"
  echo "✅ Files backup: ${archive}"
}

backup_redis_namespace() {
  local ts="$1"
  local outfile="${BACKUP_DIR}/${REDIS_DUMP_PREFIX}-${ts}.tsv"

  if ! command -v redis-cli >/dev/null 2>&1; then
    echo "⚠️ Brak redis-cli, pomijam backup Redis namespace ${REDIS_PATTERN}."
    return 0
  fi

  : > "${outfile}"

  while IFS= read -r key; do
    [ -n "${key}" ] || continue
    local pttl raw_ttl ttl dump_b64
    pttl="$(redis-cli --raw PTTL "${key}" 2>/dev/null || echo -1)"
    raw_ttl="${pttl%%$'\r'*}"
    if [ "${raw_ttl}" -lt 0 ] 2>/dev/null; then
      ttl=0
    else
      ttl="${raw_ttl}"
    fi
    dump_b64="$(redis-cli --raw DUMP "${key}" | base64 -w0)"
    if [ -z "${dump_b64}" ]; then
      echo "⚠️ Pomijam klucz bez payload DUMP: ${key}" >&2
      continue
    fi
    printf '%s\t%s\t%s\n' "${key}" "${ttl}" "${dump_b64}" >> "${outfile}"
  done < <(redis-cli --scan --pattern "${REDIS_PATTERN}" || true)

  sha256sum "${outfile}" > "${outfile}.sha256"
  echo "✅ Redis namespace backup: ${outfile}"
}

restore_files_backup() {
  local ts="$1"
  local archive="${BACKUP_DIR}/${FILES_ARCHIVE_PREFIX}-${ts}.tar.gz"
  local checksum="${archive}.sha256"
  [ -f "${archive}" ] || { echo "❌ Brak archiwum: ${archive}"; exit 1; }
  [ -f "${checksum}" ] || { echo "❌ Brak checksum: ${checksum}"; exit 1; }

  sha256sum -c "${checksum}"
  tar -xzf "${archive}" -C .
  echo "✅ Files restore: ${archive}"
}

restore_redis_namespace() {
  local ts="$1"
  local infile="${BACKUP_DIR}/${REDIS_DUMP_PREFIX}-${ts}.tsv"
  local checksum="${infile}.sha256"
  [ -f "${infile}" ] || { echo "⚠️ Brak dumpa Redis: ${infile} (pomijam)."; return 0; }
  [ -f "${checksum}" ] || { echo "❌ Brak checksum: ${checksum}"; exit 1; }
  command -v redis-cli >/dev/null 2>&1 || { echo "❌ Brak redis-cli dla restore."; exit 1; }

  sha256sum -c "${checksum}"

  while IFS=$'\t' read -r key ttl dump_b64; do
    [ -n "${key}" ] || continue
    printf '%s' "${dump_b64}" | base64 -d | redis-cli -x RESTORE "${key}" "${ttl}" REPLACE >/dev/null
  done < "${infile}"

  echo "✅ Redis namespace restore: ${infile}"
}

verify_backup() {
  local ts="$1"
  local archive="${BACKUP_DIR}/${FILES_ARCHIVE_PREFIX}-${ts}.tar.gz"
  local checksum="${archive}.sha256"
  [ -f "${archive}" ] || { echo "❌ Brak archiwum: ${archive}"; exit 1; }
  [ -f "${checksum}" ] || { echo "❌ Brak checksum: ${checksum}"; exit 1; }

  sha256sum -c "${checksum}"
  tar -tzf "${archive}" >/dev/null
  echo "✅ Archiwum plików zweryfikowane: ${archive}"

  local redis_file="${BACKUP_DIR}/${REDIS_DUMP_PREFIX}-${ts}.tsv"
  if [ -f "${redis_file}" ]; then
    sha256sum -c "${redis_file}.sha256"
    echo "✅ Dump Redis zweryfikowany: ${redis_file}"
  else
    echo "ℹ️ Brak dumpa Redis dla TS=${ts}."
  fi
}

main() {
  case "${MODE}" in
    backup)
      require_preprod_role
      TS="$(date +%Y%m%d-%H%M%S)"
      create_files_backup "${TS}"
      backup_redis_namespace "${TS}"
      echo "Backup timestamp: ${TS}"
      ;;
    restore)
      require_preprod_role
      require_mutation_override
      [ -n "${TS}" ] || { echo "❌ Podaj timestamp restore."; usage; exit 1; }
      restore_files_backup "${TS}"
      restore_redis_namespace "${TS}"
      ;;
    verify)
      require_preprod_role
      [ -n "${TS}" ] || { echo "❌ Podaj timestamp verify."; usage; exit 1; }
      verify_backup "${TS}"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
