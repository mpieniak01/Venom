#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
usage() {
  echo "Usage: $0 start|stop|restart|status|pull"
  echo "PROFILE=full|light ENVIRONMENT=dev|preprod (Docker recipe; prod remains unused)"
  echo "ACTIVE_LLM_SERVER, model and GPU selection are independent of PROFILE."
  echo "VENOM_DOCKER_PULL_POLICY=missing|always|never (default missing; never for explicit offline start)"
}
cmd=${1:-help}
case "$cmd" in help|-h|--help) usage; exit 0;; start|stop|restart|status|pull) ;; *) usage >&2; exit 1;; esac
recipe="${VENOM_DOCKER_RECIPE:-minimal}"
case "$recipe" in minimal|release) ;; *) echo 'Unknown Docker recipe' >&2; exit 1;; esac
role="${ENVIRONMENT:-${ENVIRONMENT_ROLE:-dev}}"
case "$role" in dev|preprod) ;; *) echo 'Docker ENVIRONMENT must be dev|preprod; prod is unused' >&2; exit 1;; esac
profile="${PROFILE:-${VENOM_RUNTIME_PROFILE:-light}}"
case "$profile" in
  full|light) ;;
  llm_off)
    echo '[deprecated] llm_off -> PROFILE=light ACTIVE_LLM_SERVER=none; remove alias after A10 migration.' >&2
    profile=light
    export ACTIVE_LLM_SERVER=none LLM_WARMUP_ON_STARTUP=false
    ;;
  *) echo 'PROFILE must be full|light' >&2; exit 1;;
esac
export VENOM_RUNTIME_PROFILE="$profile" ENVIRONMENT_ROLE="$role"
# Keep old dev project/volumes untouched; another environment gets another project.
if [[ "$role" == preprod ]]; then
  export COMPOSE_PROJECT_NAME="venom-${recipe}-preprod"
  export VENOM_CONTAINER_PREFIX="venom-preprod"
  export VENOM_API_HOST_PORT=8810 VENOM_WEB_HOST_PORT=3310 VENOM_OLLAMA_HOST_PORT=11435
  export DB_SCHEMA=preprod CACHE_NAMESPACE=preprod QUEUE_NAMESPACE=preprod STORAGE_PREFIX=preprod ALLOW_DATA_MUTATION=0
else
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-venom-${recipe}}"
  export VENOM_CONTAINER_PREFIX="${VENOM_CONTAINER_PREFIX:-venom}"
  export VENOM_API_HOST_PORT="${VENOM_API_HOST_PORT:-8000}" VENOM_WEB_HOST_PORT="${VENOM_WEB_HOST_PORT:-3000}" VENOM_OLLAMA_HOST_PORT="${VENOM_OLLAMA_HOST_PORT:-11434}"
  export DB_SCHEMA="${DB_SCHEMA:-dev}" CACHE_NAMESPACE="${CACHE_NAMESPACE:-venom}" QUEUE_NAMESPACE="${QUEUE_NAMESPACE:-venom}" STORAGE_PREFIX="${STORAGE_PREFIX:-}" ALLOW_DATA_MUTATION="${ALLOW_DATA_MUTATION:-0}"
fi
export ACTIVE_LLM_SERVER="${ACTIVE_LLM_SERVER:-ollama}" LLM_WARMUP_ON_STARTUP="${LLM_WARMUP_ON_STARTUP:-false}"
if [[ "$profile" == light ]]; then
  export LLM_WARMUP_ON_STARTUP=false
  export VENOM_PAUSE_BACKGROUND_TASKS=true ENABLE_AUTO_DOCUMENTATION=false ENABLE_AUTO_GARDENING=false
fi
if [[ "$recipe" == release && -z "${VENOM_RELEASE_VERSION:-}" ]]; then
  VENOM_RELEASE_VERSION=$(awk -F '"' '/^version = "/ {print $2; exit}' "$ROOT_DIR/pyproject.toml")
  export VENOM_RELEASE_VERSION
fi
COMPOSE_ARGS=(-f "$ROOT_DIR/compose/compose.${recipe}.yml")
command -v docker >/dev/null || { echo 'Docker is not installed' >&2; exit 1; }
docker compose version >/dev/null
# GPU acceleration is technical configuration, never a third application profile.
case "${VENOM_ENABLE_GPU:-auto}" in
  0|false|off|no) ;;
  1|true|on|yes|auto)
    if [[ "$ACTIVE_LLM_SERVER" == ollama ]] && docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
      COMPOSE_ARGS+=(-f "$ROOT_DIR/compose/compose.internal.gpu-override.yml")
    fi
    ;;
  *) echo 'Invalid VENOM_ENABLE_GPU' >&2; exit 1;;
esac
compose_cmd() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }
start_stack() {
  local pull_policy="${VENOM_DOCKER_PULL_POLICY:-missing}"
  case "$pull_policy" in always|missing|never) ;; *) echo 'Invalid VENOM_DOCKER_PULL_POLICY' >&2; return 1;; esac
  local args=(up -d --pull "$pull_policy")
  if [[ "$recipe" == minimal ]]; then args+=(--build); else args+=(--no-build); fi
  # Only the selected local engine can be started. No implicit model pull or warmup.
  if [[ "$ACTIVE_LLM_SERVER" != ollama ]]; then args+=(--no-deps backend frontend); fi
  compose_cmd "${args[@]}"
}
case "$cmd" in
  start) start_stack;;
  restart) compose_cmd down --remove-orphans; start_stack;;
  stop) compose_cmd down --remove-orphans;;
  status) compose_cmd ps;;
  pull) compose_cmd pull;;
esac
