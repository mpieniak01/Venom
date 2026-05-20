#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACTION="${1:-status}"
BASHRC_PATH="${BASHRC_PATH:-$HOME/.bashrc}"
BLOCK_BEGIN="# >>> venom local-first profile >>>"
BLOCK_END="# <<< venom local-first profile <<<"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$HOME/.venom/profile_backups}"

read -r -d '' PROFILE_BLOCK <<'EOF' || true
# >>> venom local-first profile >>>
export ACTIVE_LLM_SERVER=ollama
export OLLAMA_CONTEXT_LENGTH=64000
export OLLAMA_KEEP_ALIVE=-1
export OLLAMA_NO_CLOUD=true
export VENOM_PAUSE_BACKGROUND_TASKS=true
# <<< venom local-first profile <<<
EOF

print_status() {
  echo "repo_root=${REPO_ROOT}"
  echo "bashrc=${BASHRC_PATH}"
  if [[ ! -f "${BASHRC_PATH}" ]]; then
    echo "status=missing_bashrc"
    return 0
  fi
  if grep -qF "${BLOCK_BEGIN}" "${BASHRC_PATH}"; then
    echo "status=installed"
  else
    echo "status=not_installed"
  fi
  if [[ -d "${SNAPSHOT_DIR}" ]]; then
    echo "snapshot_dir=${SNAPSHOT_DIR}"
    echo "snapshot_count=$(find "${SNAPSHOT_DIR}" -maxdepth 1 -type f -name 'bashrc.*.bak' | wc -l | tr -d ' ')"
  else
    echo "snapshot_dir=${SNAPSHOT_DIR}"
    echo "snapshot_count=0"
  fi
}

make_snapshot() {
  mkdir -p "${SNAPSHOT_DIR}"
  local ts out
  ts="$(date +%Y%m%d_%H%M%S)"
  out="${SNAPSHOT_DIR}/bashrc.${ts}.bak"
  if [[ -f "${BASHRC_PATH}" ]]; then
    cp "${BASHRC_PATH}" "${out}"
  else
    : > "${out}"
  fi
  echo "${out}"
}

install_profile() {
  mkdir -p "$(dirname "${BASHRC_PATH}")"
  touch "${BASHRC_PATH}"
  if grep -qF "${BLOCK_BEGIN}" "${BASHRC_PATH}"; then
    echo "ℹ️  Profil local-first już istnieje w ${BASHRC_PATH}."
    return 0
  fi
  local snap
  snap="$(make_snapshot)"
  echo "🗂️  Snapshot as-is: ${snap}"
  {
    echo ""
    echo "${PROFILE_BLOCK}"
  } >> "${BASHRC_PATH}"
  echo "✅ Dodano profil local-first do ${BASHRC_PATH}."
}

remove_profile() {
  if [[ ! -f "${BASHRC_PATH}" ]]; then
    echo "ℹ️  Brak ${BASHRC_PATH}, nic do usunięcia."
    return 0
  fi
  if ! grep -qF "${BLOCK_BEGIN}" "${BASHRC_PATH}"; then
    echo "ℹ️  Profil local-first nie jest zainstalowany."
    return 0
  fi
  local snap
  snap="$(make_snapshot)"
  echo "🗂️  Snapshot as-is: ${snap}"
  awk -v begin="${BLOCK_BEGIN}" -v end="${BLOCK_END}" '
    $0 == begin {skip=1; next}
    $0 == end {skip=0; next}
    !skip {print}
  ' "${BASHRC_PATH}" > "${BASHRC_PATH}.tmp"
  mv "${BASHRC_PATH}.tmp" "${BASHRC_PATH}"
  echo "✅ Usunięto profil local-first z ${BASHRC_PATH}."
}

backup_profile() {
  local snap
  snap="$(make_snapshot)"
  echo "✅ Snapshot utworzony: ${snap}"
}

list_backups() {
  if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
    echo "ℹ️  Brak katalogu snapshotów: ${SNAPSHOT_DIR}"
    return 0
  fi
  find "${SNAPSHOT_DIR}" -maxdepth 1 -type f -name 'bashrc.*.bak' | sort
}

restore_profile() {
  local source_file="${RESTORE_FILE:-}"
  if [[ ! -d "${SNAPSHOT_DIR}" ]]; then
    echo "❌ Brak katalogu snapshotów: ${SNAPSHOT_DIR}"
    exit 1
  fi
  if [[ -z "${source_file}" ]]; then
    source_file="$(find "${SNAPSHOT_DIR}" -maxdepth 1 -type f -name 'bashrc.*.bak' 2>/dev/null | sort | tail -n 1 || true)"
  fi
  if [[ -z "${source_file}" ]]; then
    echo "❌ Brak snapshotu do przywrócenia."
    exit 1
  fi
  if [[ ! -f "${source_file}" ]]; then
    echo "❌ Snapshot nie istnieje: ${source_file}"
    exit 1
  fi
  cp "${source_file}" "${BASHRC_PATH}"
  echo "✅ Przywrócono ${BASHRC_PATH} z: ${source_file}"
}

print_exports() {
  printf '%s\n' "${PROFILE_BLOCK}"
}

case "${ACTION}" in
  status) print_status ;;
  install) install_profile ;;
  remove) remove_profile ;;
  backup) backup_profile ;;
  list-backups) list_backups ;;
  restore) restore_profile ;;
  print) print_exports ;;
  *)
    echo "Usage: $0 {status|install|remove|backup|list-backups|restore|print}"
    exit 2
    ;;
esac
