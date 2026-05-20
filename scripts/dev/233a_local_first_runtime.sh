#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DEFAULT_MODEL="qwen2.5-coder:7b"
ACTION="${1:-help}"
MODEL="${MODEL:-$DEFAULT_MODEL}"
PROMPT="${PROMPT:-}"
KEEPALIVE="${KEEPALIVE:--1}"

activate_venv() {
  if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.venv/bin/activate"
  fi
}

resolve_codex_bin() {
  if command -v codex >/dev/null 2>&1; then
    command -v codex
    return 0
  fi

  local ext_root="${HOME}/.vscode-server/extensions"
  if [[ ! -d "${ext_root}" ]]; then
    ext_root="${HOME}/.vscode/extensions"
  fi
  local latest
  latest="$(ls -1d "${ext_root}"/openai.chatgpt-* 2>/dev/null | tail -n 1 || true)"
  if [[ -n "${latest}" ]] && [[ -x "${latest}/bin/linux-x86_64/codex" ]]; then
    echo "${latest}/bin/linux-x86_64/codex"
    return 0
  fi

  return 1
}

ensure_ollama_cli() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Brak 'ollama' w PATH."
    exit 1
  fi
}

ensure_codex_cli() {
  if ! resolve_codex_bin >/dev/null 2>&1; then
    echo "❌ Brak 'codex' w PATH oraz w VS Code extension."
    exit 1
  fi
}

start_stack() {
  ensure_ollama_cli
  echo "▶️  Start lokalnego runtime Ollama..."
  bash "${REPO_ROOT}/scripts/llm/ollama_service.sh" start

  local ready_attempts=30
  local ready_delay_sec=1
  local ready_url="http://127.0.0.1:11434/api/tags"
  echo "⏳ Czekam na gotowość Ollama (${ready_attempts} prób, ${ready_delay_sec}s odstępu)..."
  while (( ready_attempts > 0 )); do
    if curl -fsS "${ready_url}" >/dev/null 2>&1; then
      break
    fi
    sleep "${ready_delay_sec}"
    ((ready_attempts--))
  done

  if ! curl -fsS "${ready_url}" >/dev/null 2>&1; then
    echo "❌ Ollama nie odpowiedziała na ${ready_url} po oczekiwaniu."
    exit 1
  fi

  local payload response_file http_code keepalive_json
  response_file="$(mktemp)"
  keepalive_json=""
  if [[ -n "${KEEPALIVE}" ]] && [[ "${KEEPALIVE}" != "-1" ]]; then
    keepalive_json=",\"keep_alive\":\"${KEEPALIVE}\""
  elif [[ "${KEEPALIVE}" == "-1" ]]; then
    echo "ℹ️  KEEPALIVE=-1 nie jest akceptowane przez API per-request, pomijam keep_alive w preload."
  fi
  payload="{\"model\":\"${MODEL}\",\"prompt\":\"local-first preload\",\"stream\":false,\"options\":{\"num_predict\":1}${keepalive_json}}"

  echo "▶️  Preload modelu: ${MODEL} (HTTP /api/generate)"
  http_code="$(
    curl -sS -o "${response_file}" -w "%{http_code}" \
      -H "Content-Type: application/json" \
      -X POST "http://127.0.0.1:11434/api/generate" \
      -d "${payload}" || true
  )"

  if [[ "${http_code}" != "200" ]]; then
    echo "❌ Preload nieudany: HTTP ${http_code}"
    cat "${response_file}" || true
    rm -f "${response_file}"
    exit 1
  fi

  if ! jq -e '.done == true' "${response_file}" >/dev/null 2>&1; then
    echo "❌ Preload niepotwierdzony (brak done=true w odpowiedzi)"
    cat "${response_file}" || true
    rm -f "${response_file}"
    exit 1
  fi

  rm -f "${response_file}"
  echo "✅ Runtime gotowy. Model aktywny: ${MODEL}"
}

status_stack() {
  ensure_ollama_cli
  echo "## Status Ollama"
  ollama --version || true
  echo
  echo "## Modele załadowane (ollama ps)"
  ollama ps || true
  echo
  echo "## Modele lokalne (ollama list)"
  ollama list || true
  echo
  echo "## Codex"
  if codex_bin="$(resolve_codex_bin 2>/dev/null)"; then
    echo "codex_bin=${codex_bin}"
    "${codex_bin}" --version || true
  else
    echo "codex: not found"
  fi
}

run_codex_local() {
  ensure_ollama_cli
  ensure_codex_cli
  local codex_bin
  codex_bin="$(resolve_codex_bin)"
  local prompt_text="${PROMPT:-Powiedz tylko OK.}"
  echo "▶️  Uruchamiam Codex lokalnie (provider=ollama, model=${MODEL})"
  "${codex_bin}" exec \
    --oss \
    --local-provider ollama \
    --model "${MODEL}" \
    --cd "${REPO_ROOT}" \
    --sandbox workspace-write \
    "${prompt_text}"
}

unload_model() {
  ensure_ollama_cli
  echo "▶️  Unload modelu: ${MODEL}"
  ollama stop "${MODEL}"
  echo "✅ Model zatrzymany: ${MODEL}"
}

unload_all_models() {
  ensure_ollama_cli
  local running_models
  running_models="$(ollama ps | awk 'NR>1 {print $1}')"
  if [[ -z "${running_models}" ]]; then
    echo "ℹ️  Brak aktywnych modeli do unload."
    return 0
  fi
  echo "▶️  Unload wszystkich modeli z pamięci..."
  while IFS= read -r model; do
    [[ -z "${model}" ]] && continue
    ollama stop "${model}" || true
  done <<< "${running_models}"
  echo "✅ Wszystkie aktywne modele zatrzymane."
}

stop_stack() {
  ensure_ollama_cli
  echo "▶️  Zatrzymuję runtime Ollama..."
  bash "${REPO_ROOT}/scripts/llm/ollama_service.sh" stop
  echo "✅ Runtime zatrzymany."
}

print_help() {
  cat <<'EOF'
Usage:
  scripts/dev/233a_local_first_runtime.sh <action>

Actions:
  start         Start Ollama service and preload MODEL
  status        Show Ollama/Codex status
  run-codex     Run Codex with local Ollama provider on MODEL
  unload        Unload MODEL from memory (ollama stop MODEL)
  unload-all    Unload all running models from memory
  stop          Stop Ollama service
  help          Show this help

Env vars:
  MODEL=qwen2.5-coder:7b      Selected local model
  KEEPALIVE=-1                Ollama keepalive used during preload
  PROMPT="..."                Optional prompt for run-codex mode
EOF
}

cd "${REPO_ROOT}"
activate_venv

case "${ACTION}" in
  start) start_stack ;;
  status) status_stack ;;
  run-codex) run_codex_local ;;
  unload) unload_model ;;
  unload-all) unload_all_models ;;
  stop) stop_stack ;;
  help|-h|--help) print_help ;;
  *)
    echo "❌ Nieznana akcja: ${ACTION}"
    print_help
    exit 2
    ;;
esac
