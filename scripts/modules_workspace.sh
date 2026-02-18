#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(pwd)}"
MODULES_DIR="${MODULES_DIR:-$ROOT_DIR/modules}"
COMMAND="${1:-status}"
shift || true

if [[ ! -d "$ROOT_DIR/.git" ]]; then
  echo "ERROR: ROOT_DIR must point to the Venom git repository root."
  exit 1
fi

ensure_modules_dir() {
  if [[ ! -d "$MODULES_DIR" ]]; then
    echo "INFO: modules directory does not exist yet: $MODULES_DIR"
    return 1
  fi
  return 0
}

list_module_repos() {
  ensure_modules_dir || return 0
  while IFS= read -r -d '' dir; do
    if git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      echo "$dir"
    fi
  done < <(find "$MODULES_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
}

print_repo_status() {
  local repo="$1"
  local name branch dirty
  name="$(basename "$repo")"
  branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached")"
  dirty="$(git -C "$repo" status --porcelain | wc -l | tr -d ' ')"
  echo "- $name | branch=$branch | dirty_files=$dirty"
}

status_all() {
  echo "Workspace root: $ROOT_DIR"
  echo "Modules dir:    $MODULES_DIR"
  echo
  echo "[core]"
  print_repo_status "$ROOT_DIR"
  echo
  echo "[modules]"
  local found=0
  while IFS= read -r repo; do
    found=1
    print_repo_status "$repo"
  done < <(list_module_repos)
  if [[ "$found" -eq 0 ]]; then
    echo "- none"
  fi
}

pull_all() {
  echo "[core] git pull --ff-only"
  git -C "$ROOT_DIR" pull --ff-only
  while IFS= read -r repo; do
    echo "[$(basename "$repo")] git pull --ff-only"
    git -C "$repo" pull --ff-only
  done < <(list_module_repos)
}

branches_all() {
  echo "[core]"
  git -C "$ROOT_DIR" branch --show-current
  while IFS= read -r repo; do
    echo "[$(basename "$repo")]"
    git -C "$repo" branch --show-current
  done < <(list_module_repos)
}

exec_all() {
  if [[ "$#" -eq 0 ]]; then
    echo "ERROR: provide command for exec, e.g. scripts/modules_workspace.sh exec \"git status -s\""
    exit 1
  fi
  local cmd="$*"
  echo "[core] $cmd"
  bash -lc "cd \"$ROOT_DIR\" && $cmd"
  while IFS= read -r repo; do
    echo "[$(basename "$repo")] $cmd"
    bash -lc "cd \"$repo\" && $cmd"
  done < <(list_module_repos)
}

case "$COMMAND" in
  status)
    status_all
    ;;
  pull)
    pull_all
    ;;
  branches)
    branches_all
    ;;
  exec)
    exec_all "$@"
    ;;
  *)
    echo "Usage: $0 {status|pull|branches|exec <cmd>}"
    exit 1
    ;;
esac
