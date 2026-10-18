#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
RUN_RELEASE="$ROOT_DIR/scripts/docker/run-release.sh"
INSTALL_SCRIPT="$ROOT_DIR/scripts/docker/install.sh"
UNINSTALL_SCRIPT="$ROOT_DIR/scripts/docker/uninstall.sh"

LANG_CODE="${VENOM_INSTALL_LANG:-}"
PROFILE_RAW="${VENOM_RUNTIME_PROFILE:-}"
ADDONS_RAW="${VENOM_RUNTIME_ADDONS:-none}"
ACTION="auto"
QUICK=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --lang <code>      Installer language: pl|en|de
  --profile <name>   Runtime profile: light|api_ollama|api|api_only|llm_off
  --addons <name>    Runtime addons: none (default: none)
  --action <name>    Action: auto|start|install|reinstall|uninstall|status
  --quick            Non-interactive mode
  -h, --help         Show this help
USAGE
  return 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --lang)
      shift
      LANG_CODE=${1:-}
      if [[ -z "$LANG_CODE" ]]; then
        echo "[ERROR] --lang requires a value." >&2
        exit 1
      fi
      ;;
    --profile)
      shift
      PROFILE_RAW=${1:-}
      if [[ -z "$PROFILE_RAW" ]]; then
        echo "[ERROR] --profile requires a value." >&2
        exit 1
      fi
      ;;
    --addons)
      shift
      ADDONS_RAW=${1:-}
      if [[ -z "$ADDONS_RAW" ]]; then
        echo "[ERROR] --addons requires a value." >&2
        exit 1
      fi
      ;;
    --action)
      shift
      ACTION=${1:-}
      if [[ -z "$ACTION" ]]; then
        echo "[ERROR] --action requires a value." >&2
        exit 1
      fi
      ;;
    --quick)
      QUICK=1
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

normalize_lang() {
  local raw=$1
  raw=$(echo "$raw" | tr '[:upper:]' '[:lower:]')
  case "$raw" in
    pl|en|de) echo "$raw" ;;
    "") echo "" ;;
    *)
      echo "[ERROR] Unsupported language: $raw (expected: pl|en|de)." >&2
      exit 1
      ;;
  esac
}

normalize_profile() {
  local raw=$1
  raw=$(echo "$raw" | tr '[:upper:]' '[:lower:]')
  case "$raw" in
    light|api_ollama) echo "light" ;;
    api|llm_off) echo "llm_off" ;;
    api_only) echo "llm_off" ;;
    full|full-ci|onnx-cpu|onnx-extras|onnx-gpu|vllm|academy)
      echo "[ERROR] Deferred profile unavailable in this Light/API release: $raw" >&2
      exit 1
      ;;
    "") echo "" ;;
    *)
      echo "[ERROR] Unsupported profile: $raw (expected: light|api_ollama|api|api_only|llm_off)." >&2
      exit 1
      ;;
  esac
}

normalize_addons() {
  local cleaned
  cleaned=$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -d ' ')
  if [[ "$cleaned" == "none" ]]; then
    echo "none"
    return 0
  fi
  echo "[ERROR] Runtime addons are deferred in this Light/API release: $cleaned" >&2
  exit 1
}

map_profile_label() {
  local profile=$1
  case "$profile" in
    light) echo "API+OLLAMA" ;;
    llm_off) echo "API" ;;
    *) echo "$profile" ;;
  esac
}

validate_action() {
  case "$ACTION" in
    auto|start|install|reinstall|uninstall|status) ;;
    *)
      echo "[ERROR] Unsupported action: $ACTION (expected: auto|start|install|reinstall|uninstall|status)." >&2
      exit 1
      ;;
  esac
}

read_profile_from_menu() {
  case "$LANG_CODE" in
    pl)
      echo "Wybierz architekturę Venom:" >&2
      echo "  1) API+OLLAMA (lokalnie: API + Ollama + Next.js) - rekomendowane minimum" >&2
      echo "  2) API   (cloud: OpenAI/Anthropic + Next.js) - Low Hardware Req" >&2
      read -r -p "Wybór [1/2] (domyślnie 1): " p
      ;;
    de)
      echo "Waehle deine Venom-Architektur:" >&2
      echo "  1) API+OLLAMA (lokal: API + Ollama + Next.js) - empfohlenes Minimum" >&2
      echo "  2) API   (cloud: OpenAI/Anthropic + Next.js) - Low Hardware Req" >&2
      read -r -p "Auswahl [1/2] (Standard 1): " p
      ;;
    *)
      echo "Select your Venom architecture:" >&2
      echo "  1) API+OLLAMA (Local: API + Ollama + Next.js) - recommended minimum" >&2
      echo "  2) API   (Cloud: OpenAI/Anthropic + Next.js) - Low Hardware Req" >&2
      read -r -p "Choice [1/2] (default 1): " p
      ;;
  esac

  p=${p:-1}
  case "$p" in
    1) echo "light" ;;
    2) echo "llm_off" ;;
    *)
      echo "[ERROR] Invalid architecture choice: $p" >&2
      exit 1
      ;;
  esac
}

read_lang_from_menu() {
  echo "Select installer language / Wybierz jezyk instalatora / Sprache waehlen:" >&2
  echo "  1) English" >&2
  echo "  2) Polski" >&2
  echo "  3) Deutsch" >&2
  read -r -p "Choice [1/2/3] (default 1): " l
  l=${l:-1}
  case "$l" in
    1) echo "en" ;;
    2) echo "pl" ;;
    3) echo "de" ;;
    *)
      echo "[ERROR] Invalid language choice: $l" >&2
      exit 1
      ;;
  esac
}

has_nonempty_env_or_file_key() {
  local key=$1
  local env_file="${ENV_FILE:-$ROOT_DIR/.env.dev}"
  if [[ "$env_file" != /* ]]; then
    env_file="$ROOT_DIR/$env_file"
  fi
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi
  if [[ -f "$env_file" ]]; then
    local value
    value=$(awk -F '=' -v k="$key" '$1==k {sub(/^[ "]+/,"",$2); sub(/[ "]+$/, "", $2); print $2; exit}' "$env_file")
    if [[ -n "$value" ]]; then
      return 0
    fi
  fi
  return 1
}

preflight_api_profile() {
  if has_nonempty_env_or_file_key "OPENAI_API_KEY"; then return 0; fi
  if has_nonempty_env_or_file_key "ANTHROPIC_API_KEY"; then return 0; fi
  if has_nonempty_env_or_file_key "GOOGLE_API_KEY"; then return 0; fi
  if has_nonempty_env_or_file_key "GEMINI_API_KEY"; then return 0; fi

  echo "[WARN] API profile selected, but no external provider API key detected."
  echo "[HINT] Configure one of: OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY / GEMINI_API_KEY"
  if [[ "$QUICK" -eq 1 ]]; then
    echo "[ERROR] QUICK mode cannot continue without API key preflight for API profile." >&2
    exit 1
  fi
  read -r -p "Continue anyway? [y/N]: " ans
  ans=${ans:-N}
  case "$ans" in
    [Yy]*) ;;
    *)
      echo "[INFO] Aborted."
      exit 0
      ;;
  esac
}

stack_running_release() {
  if docker compose -f "$ROOT_DIR/compose/compose.release.yml" ps -q | grep -q .; then
    return 0
  fi
  return 1
}

select_action_auto() {
  if ! stack_running_release; then
    echo "start"
    return 0
  fi

  if [[ "$QUICK" -eq 1 ]]; then
    echo "start"
    return 0
  fi

  case "$LANG_CODE" in
    pl)
      echo "[INFO] Wykryto istniejący stack release." >&2
      echo "  1) Start/Update" >&2
      echo "  2) Reinstall (odtworzenie kontenerów)" >&2
      echo "  3) Uninstall" >&2
      echo "  4) Anuluj" >&2
      read -r -p "Wybór [1/2/3/4] (domyślnie 1): " a
      ;;
    de)
      echo "[INFO] Vorhandener Release-Stack erkannt." >&2
      echo "  1) Start/Update" >&2
      echo "  2) Reinstall (Container neu erstellen)" >&2
      echo "  3) Uninstall" >&2
      echo "  4) Abbrechen" >&2
      read -r -p "Auswahl [1/2/3/4] (Standard 1): " a
      ;;
    *)
      echo "[INFO] Existing release stack detected." >&2
      echo "  1) Start/Update" >&2
      echo "  2) Reinstall (recreate containers)" >&2
      echo "  3) Uninstall" >&2
      echo "  4) Cancel" >&2
      read -r -p "Choice [1/2/3/4] (default 1): " a
      ;;
  esac

  a=${a:-1}
  case "$a" in
    1) echo "start" ;;
    2) echo "reinstall" ;;
    3) echo "uninstall" ;;
    4)
      echo "[INFO] Aborted."
      exit 0
      ;;
    *)
      echo "[ERROR] Invalid action choice: $a" >&2
      exit 1
      ;;
  esac
}

LANG_CODE=$(normalize_lang "$LANG_CODE")
PROFILE_RAW=$(normalize_profile "$PROFILE_RAW")
ADDONS_RAW=$(normalize_addons "$ADDONS_RAW")
validate_action

if [[ -z "$LANG_CODE" ]]; then
  if [[ "$QUICK" -eq 1 || ! -t 0 ]]; then
    LANG_CODE="en"
  else
    LANG_CODE=$(read_lang_from_menu)
  fi
fi

if [[ -z "$PROFILE_RAW" ]]; then
  if [[ "$QUICK" -eq 1 || ! -t 0 ]]; then
    PROFILE_RAW="light"
  else
    PROFILE_RAW=$(read_profile_from_menu)
  fi
fi

if [[ "$ACTION" == "auto" ]]; then
  ACTION=$(select_action_auto)
fi

if [[ "$PROFILE_RAW" == "llm_off" ]]; then
  preflight_api_profile
fi

export VENOM_RUNTIME_PROFILE="$PROFILE_RAW"
export VENOM_RUNTIME_ADDONS="$ADDONS_RAW"

case "$ACTION" in
  start)
    "$RUN_RELEASE" start
    ;;
  install)
    "$INSTALL_SCRIPT" --quick --profile "$PROFILE_RAW"
    ;;
  reinstall)
    "$UNINSTALL_SCRIPT" --stack release --yes
    "$RUN_RELEASE" start
    ;;
  uninstall)
    "$UNINSTALL_SCRIPT" --stack release
    ;;
  status)
    "$RUN_RELEASE" status
    ;;
esac

echo "[OK] Launcher completed: profile=$(map_profile_label "$PROFILE_RAW"), action=$ACTION, addons=$ADDONS_RAW, lang=$LANG_CODE"
