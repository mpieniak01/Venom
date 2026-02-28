#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-safe}"
DRY_RUN="${DRY_RUN:-0}"
CONFIRM_DEEP_CLEAN="${CONFIRM_DEEP_CLEAN:-0}"
ENVIRONMENT_ROLE="${ENVIRONMENT_ROLE:-dev}"
ALLOW_DATA_MUTATION="${ALLOW_DATA_MUTATION:-0}"

run_cmd() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "⚠️  docker not installed"
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "⚠️  docker daemon unavailable"
    return 1
  fi
  return 0
}

check_preprod_guard() {
  local role
  role="$(echo "$ENVIRONMENT_ROLE" | tr '[:upper:]' '[:lower:]')"
  if [[ "$role" =~ ^(preprod|pre-prod|pre_prod|staging|stage)$ ]] && [[ "$ALLOW_DATA_MUTATION" != "1" ]]; then
    echo "❌ Docker cleanup blocked for pre-prod (ALLOW_DATA_MUTATION=0)."
    exit 3
  fi
}

cleanup_safe() {
  echo "🧹 Docker safe cleanup (dangling/build cache)"
  run_cmd docker image prune -f
  run_cmd docker builder prune -f

  local volume_ids
  volume_ids="$(docker volume ls -qf dangling=true || true)"
  if [[ -n "$volume_ids" ]]; then
    while IFS= read -r vid; do
      [[ -z "$vid" ]] && continue
      run_cmd docker volume rm "$vid"
    done <<< "$volume_ids"
  else
    echo "ℹ️  No dangling volumes"
  fi

  local exited_venom
  exited_venom="$(docker ps -a --filter status=exited --format '{{.ID}} {{.Names}}' | awk '$2 ~ /venom|web-next|academy/ {print $1}' || true)"
  if [[ -n "$exited_venom" ]]; then
    while IFS= read -r cid; do
      [[ -z "$cid" ]] && continue
      run_cmd docker rm "$cid"
    done <<< "$exited_venom"
  else
    echo "ℹ️  No exited Venom-related containers"
  fi
}

cleanup_deep() {
  if [[ "$CONFIRM_DEEP_CLEAN" != "1" ]]; then
    echo "❌ Deep clean blocked. Use CONFIRM_DEEP_CLEAN=1"
    exit 1
  fi
  cleanup_safe
  echo "🧨 Docker deep cleanup"
  run_cmd docker system prune -f
}

case "$MODE" in
  safe)
    check_preprod_guard
    if ! ensure_docker; then
      exit 0
    fi
    cleanup_safe
    ;;
  deep)
    check_preprod_guard
    if ! ensure_docker; then
      exit 0
    fi
    cleanup_deep
    ;;
  *)
    echo "Usage: scripts/dev/docker_cleanup.sh [safe|deep]"
    exit 2
    ;;
esac

echo "✅ docker_cleanup completed (mode=$MODE, dry_run=$DRY_RUN)"
