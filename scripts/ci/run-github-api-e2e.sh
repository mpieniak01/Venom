#!/usr/bin/env bash
# Only a GitHub-hosted runner in a fresh network and mount namespace may run this.
set -euo pipefail
if [[ "${CI:-}" != true || "${GITHUB_ACTIONS:-}" != true || "${RUNNER_ENVIRONMENT:-}" != github-hosted || "$(id -u)" == 0 ]]; then
  echo 'This harness requires an unprivileged GitHub-hosted runner.' >&2; exit 1
fi
repo=$(cd "$(dirname "$0")/../.." && pwd)
python3 "$repo/scripts/ci/verify_github_e2e_namespace.py"
for socket in /run/docker.sock /var/run/docker.sock /run/containerd/containerd.sock /run/dbus/system_bus_socket "/run/user/$(id -u)/bus"; do
  if [[ -S "$socket" ]]; then echo "Host socket is visible: $socket" >&2; exit 1; fi
done
python3 - <<'PY'
import socket
sockets = []
try:
    for port in (13300, 18800, 11434):
        sock = socket.socket()
        sock.bind(("127.0.0.1", port))
        sockets.append(sock)
finally:
    for sock in sockets:
        sock.close()
PY
scratch=$(mktemp -d "$repo/.github-e2e-tmp.XXXXXX")
touch "$scratch/empty.env"
export ENV_FILE="$scratch/empty.env" PYTHONPATH="$repo" WORKSPACE_ROOT="$scratch/workspace" MEMORY_ROOT="$scratch/memory"
export HF_HOME="$scratch/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=-1
export LLM_SERVICE_TYPE=local ACTIVE_LLM_SERVER=ollama LLM_LOCAL_ENDPOINT=http://127.0.0.1:11434/v1 LLM_MODEL_NAME=ci-fake-llm
export LLM_WARMUP_ON_STARTUP=false OLLAMA_START_COMMAND='' OLLAMA_STOP_COMMAND='' OLLAMA_RESTART_COMMAND='' ONNX_START_COMMAND='' ONNX_RESTART_COMMAND='' OLLAMA_BASE_URL=http://127.0.0.1:11434
export ENABLE_AUTO_DOCUMENTATION=false ENABLE_AUTO_GARDENING=false ENABLE_CHRONOS=false ENABLE_HF_INTEGRATION=false ENABLE_IMAGE_GENERATION=false ENABLE_META_LEARNING=false API_OPTIONAL_MODULES=''
export API_PROXY_TARGET=http://127.0.0.1:18800 NEXT_TELEMETRY_DISABLED=1 NEXT_PLAYWRIGHT_DISABLE_SSR_API=1 NEXT_DISABLE_TURBOPACK=1
pids=()
cleanup() {
  status=$?
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
  if (( status != 0 )); then
    for log in "$scratch"/*.log; do [[ -f "$log" ]] && { echo "--- $log ---"; tail -100 "$log"; }; done
  fi
  if [[ "$scratch" == "$repo"/.github-e2e-tmp.* && -d "$scratch" ]]; then rm -rf -- "$scratch"; fi
}
trap cleanup EXIT
cd "$scratch"
python3 "$repo/scripts/ci/github_e2e_fake_llm.py" >fake.log 2>&1 & pids+=("$!")
python3 -m uvicorn venom_core.main:app --host 127.0.0.1 --port 18800 >backend.log 2>&1 & pids+=("$!")
(cd "$repo/web-next" && node scripts/serve-with-proxy.mjs dev --hostname 127.0.0.1 --port 13300) >frontend.log 2>&1 & pids+=("$!")
ready() {
  python3 - "$1" <<'PY'
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
}
for url in http://127.0.0.1:11434/api/tags http://127.0.0.1:18800/healthz http://127.0.0.1:13300/api/v1/system/llm-servers/active http://127.0.0.1:13300/; do
  ok=0
  for ((i=0; i<180; i++)); do
    for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null || { echo "A test process exited." >&2; exit 1; }; done
    if ready "$url"; then ok=1; break; fi
    sleep 1
  done
  (( ok )) || { echo "Timed out waiting for $url" >&2; exit 1; }
done
cd "$repo/web-next"
./node_modules/.bin/playwright test --config playwright.github-api-e2e.config.ts
