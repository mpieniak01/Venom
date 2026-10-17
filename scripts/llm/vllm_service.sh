#!/usr/bin/env bash
# Explicit component lifecycle; never discover/stop arbitrary services by name.
set -euo pipefail
ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT_DIR/scripts/lib/env_contract.sh"
ENV_FILE="$(env_contract_resolve_file "${ENV_FILE:-.env.dev}" "$ROOT_DIR")"

case "$ACTION" in start|stop|restart|status) ;; *)
  echo "Usage: $0 {start|stop|restart|status}" >&2; exit 1 ;;
esac

# Existing unit names do not authorize touching systemd. It is an explicit mode.
USE_SYSTEMD="$(env_contract_get VLLM_USE_SYSTEMD "false" "$ENV_FILE")"
if [[ "${USE_SYSTEMD,,}" =~ ^(1|true|yes|on)$ ]]; then
  UNIT="$(env_contract_get VLLM_SYSTEMD_UNIT "vllm.service" "$ENV_FILE")"
  SCOPE="$(env_contract_get VLLM_SYSTEMD_SCOPE "user" "$ENV_FILE")"
  [[ "$UNIT" =~ ^[[:alnum:]_][[:alnum:]_.@-]*$ ]] || { echo "Invalid systemd unit" >&2; exit 1; }
  case "$SCOPE" in user) scope_args=(--user) ;; system) scope_args=() ;; *) echo "Invalid systemd scope" >&2; exit 1 ;; esac
  exec systemctl "${scope_args[@]}" "$ACTION" -- "$UNIT"
fi

COMPONENTS="${VENOM_COMPONENTS_DIR:-$ROOT_DIR/.venv-components}"
PYTHON="$(env_contract_get VLLM_COMPONENT_PYTHON "$COMPONENTS/vllm/bin/python" "$ENV_FILE")"
MODEL="$(env_contract_get VLLM_MODEL_PATH "$ROOT_DIR/models/gemma-3-4b-it" "$ENV_FILE")"
STATE="$(env_contract_get VLLM_COMPONENT_STATE_DIR "$ROOT_DIR/.venom_runtime/components" "$ENV_FILE")"
OWNER="$(env_contract_get VLLM_COMPONENT_OWNER "vllm" "$ENV_FILE")"
HOST="$(env_contract_get VLLM_HOST "127.0.0.1" "$ENV_FILE")"
PORT="$(env_contract_get VLLM_PORT "8001" "$ENV_FILE")"
NAME="$(env_contract_get VLLM_SERVED_MODEL_NAME "$(basename "$MODEL")" "$ENV_FILE")"
MEMORY="$(env_contract_get VLLM_GPU_MEMORY_UTILIZATION "0.8" "$ENV_FILE")"
BATCH="$(env_contract_get VLLM_MAX_BATCHED_TOKENS "512" "$ENV_FILE")"
CONTEXT="$(env_contract_get VLLM_MAX_MODEL_LEN "512" "$ENV_FILE")"
TEMPLATE="$(env_contract_get VLLM_CHAT_TEMPLATE "" "$ENV_FILE")"
args=("$ACTION" --engine vllm --python "$PYTHON" --model "$MODEL"
      --state-dir "$STATE" --owner "$OWNER" --host "$HOST" --port "$PORT"
      --model-name "$NAME" --gpu-memory-utilization "${MEMORY:-0.8}"
      --max-num-batched-tokens "${BATCH:-512}" --max-model-len "${CONTEXT:-512}")
for flag in ENFORCE_EAGER TEXT_ONLY; do
  value="$(env_contract_get "VLLM_$flag" "false" "$ENV_FILE")"
  if [[ "${value,,}" =~ ^(1|true|yes|on)$ ]]; then
    case "$flag" in ENFORCE_EAGER) args+=(--enforce-eager) ;; TEXT_ONLY) args+=(--text-only) ;; esac
  fi
done
if [[ -n "$TEMPLATE" ]]; then args+=(--chat-template "$TEMPLATE"); fi
# Stdlib controller is deliberately independent of application/model interpreters.
cd "$ROOT_DIR"
exec python3 -m scripts.llm.component_runtime "${args[@]}"
