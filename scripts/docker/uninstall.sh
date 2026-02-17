#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MINIMAL_COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"
RELEASE_COMPOSE_FILE="$ROOT_DIR/compose/compose.release.yml"
STACK="both"
PURGE_VOLUMES=0
PURGE_IMAGES=0
YES=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --stack <name>       Which stack to uninstall: minimal|release|both (default: both)
  --purge-volumes      Remove volumes created by the stack (deletes Ollama models and app data)
  --purge-images       Remove service images used by the stack
  --yes, --quick       Non-interactive mode (skip confirmation)
  -h, --help           Show this help
USAGE
  return 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --stack)
      shift
      STACK=${1:-}
      if [[ -z "$STACK" ]]; then
        echo "[ERROR] --stack requires a value." >&2
        exit 1
      fi
      ;;
    --purge-volumes)
      PURGE_VOLUMES=1
      ;;
    --purge-images)
      PURGE_IMAGES=1
      ;;
    --yes|--quick)
      YES=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

case "$STACK" in
  minimal|release|both) ;;
  *)
    echo "[ERROR] Unsupported --stack value: $STACK (expected: minimal|release|both)." >&2
    exit 1
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker Compose plugin ('docker compose') is not available." >&2
  exit 1
fi

compose_down() {
  local compose_file=$1
  local label=$2

  if [[ ! -f "$compose_file" ]]; then
    echo "[WARN] Skipping $label uninstall; compose file not found: $compose_file"
    return 0
  fi

  local args=(down --remove-orphans)
  if [[ "$PURGE_VOLUMES" -eq 1 ]]; then
    args+=(--volumes)
  fi
  if [[ "$PURGE_IMAGES" -eq 1 ]]; then
    args+=(--rmi all)
  fi

  echo "[INFO] Uninstalling stack: $label"
  docker compose -f "$compose_file" "${args[@]}"
}

if [[ "$YES" -eq 0 ]]; then
  echo "This will stop and remove Docker resources for stack: $STACK"
  if [[ "$PURGE_VOLUMES" -eq 1 ]]; then
    echo "- Volumes will be deleted (includes Ollama models and Venom data)."
  fi
  if [[ "$PURGE_IMAGES" -eq 1 ]]; then
    echo "- Service images will be removed."
  fi
  if [[ "$PURGE_VOLUMES" -eq 0 ]]; then
    echo "- Volumes will be kept (use --purge-volumes for full data cleanup)."
  fi

  read -r -p "Continue uninstall? [y/N]: " ans
  ans=${ans:-N}
  case "$ans" in
    [Yy]*) ;;
    *)
      echo "[INFO] Uninstall canceled."
      exit 0
      ;;
  esac
fi

case "$STACK" in
  minimal)
    compose_down "$MINIMAL_COMPOSE_FILE" "minimal"
    ;;
  release)
    compose_down "$RELEASE_COMPOSE_FILE" "release"
    ;;
  both)
    compose_down "$MINIMAL_COMPOSE_FILE" "minimal"
    compose_down "$RELEASE_COMPOSE_FILE" "release"
    ;;
esac

echo "[OK] Uninstall finished for stack: $STACK"
if [[ "$PURGE_VOLUMES" -eq 0 ]]; then
  echo "[INFO] Data volumes were kept. Use --purge-volumes to remove all local data."
fi
