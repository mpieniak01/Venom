# =============================================================================
# Kontrola LLM Runtime (vLLM, Ollama, Multi-Runtime)
# =============================================================================

vllm-start:
	@echo "🚀 Uruchamiam vLLM..."
	@bash scripts/llm/vllm_service.sh start

vllm-stop:
	@echo "⏹️  Zatrzymuję vLLM..."
	@bash scripts/llm/vllm_service.sh stop

vllm-restart:
	@echo "🔄 Restartuję vLLM..."
	@bash scripts/llm/vllm_service.sh restart

ollama-start:
	@echo "🚀 Uruchamiam Ollama..."
	@bash scripts/llm/ollama_service.sh start

ollama-stop:
	@echo "⏹️  Zatrzymuję Ollama..."
	@bash scripts/llm/ollama_service.sh stop

ollama-restart:
	@echo "🔄 Restartuję Ollama..."
	@bash scripts/llm/ollama_service.sh restart

multi-runtime-start:
	@echo "🚀 Uruchamiam Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh start

multi-runtime-stop:
	@echo "⏹️  Zatrzymuję Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh stop

multi-runtime-restart:
	@echo "🔄 Restartuję Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh restart

multi-runtime-hygiene:
	@echo "🧹 Higiena Multi-Runtime (stop + cleanup daemon state)..."
	@bash scripts/llm/multi_runtime_service.sh stop

local-first-start:
	@echo "🚀 Local-first start (Ollama + preload modelu)"
	@MODEL="$${MODEL:-qwen2.5-coder:7b}" KEEPALIVE="$${KEEPALIVE:--1}" bash scripts/dev/233a_local_first_runtime.sh start

local-first-status:
	@echo "📊 Local-first status"
	@bash scripts/dev/233a_local_first_runtime.sh status

local-repo-status:
	@echo "📊 Local repo truth (no LLM/API)"
	@bash scripts/dev/239_local_repo_status.sh text

local-repo-status-json:
	@echo "📊 Local repo truth JSON (no LLM/API)"
	@bash scripts/dev/239_local_repo_status.sh json

local-first-codex:
	@echo "🤖 Local-first Codex (provider=ollama)"
	@MODEL="$${MODEL:-qwen2.5-coder:7b}" PROMPT="$${PROMPT:-}" bash scripts/dev/233a_local_first_runtime.sh run-codex

local-first-repo-truth-agent:
	@echo "🤖 Local-first repo-truth-first agent run"
	@MODEL="$${MODEL:-qwen2.5-coder:7b}" PROMPT="$${PROMPT:-Przeanalizuj stan repo i podaj kolejny krok.}" bash scripts/dev/236b_repo_truth_agent_run.sh

local-first-pr240-orchestrator-routing-probe:
	@echo "🧪 PR240 probe: orchestrator subagent routing for repo-truth"
	@$(PYTHON_BIN) scripts/dev/240_orchestrator_subagent_routing_probe.py

local-first-pr240-full-agent-handoff-probe:
	@echo "🧪 PR240 probe: full agent handoff contract for repo-truth"
	@$(PYTHON_BIN) scripts/dev/240_full_agent_handoff_probe.py

local-first-unload:
	@echo "🧠 Unload modelu z pamięci"
	@MODEL="$${MODEL:-qwen2.5-coder:7b}" bash scripts/dev/233a_local_first_runtime.sh unload

local-first-unload-all:
	@echo "🧠 Unload wszystkich modeli z pamięci"
	@bash scripts/dev/233a_local_first_runtime.sh unload-all

local-first-stop:
	@echo "⏹️  Local-first stop (Ollama service)"
	@bash scripts/dev/233a_local_first_runtime.sh stop

local-first-feedback-probe:
	@echo "🧪 Probe modeli lokalnych pod analizę feedbacku"
	@$(PYTHON_BIN) scripts/dev/233a_feedback_probe.py

local-first-tool-flake-probe:
	@echo "🧪 Phase 2 probe: tool flake matrix"
	@$(PYTHON_BIN) scripts/dev/233b_tool_flake_probe.py

local-first-operator-tool-profile-probe:
	@echo "🧪 PR238B probe: operator tool profile contract"
	@$(PYTHON_BIN) scripts/dev/238b_operator_tool_profile_probe.py

local-first-chat-diagnostics:
	@echo "🧪 PR234 probe: local Copilot Chat truth/tool matrix"
	@set -euo pipefail; \
	args=(); \
	[ -n "$(MODELS)" ] && args+=(--models $(MODELS)); \
	[ -n "$(CHANNELS)" ] && args+=(--channels $(CHANNELS)); \
	[ -n "$(PROMPT_VARIANTS)" ] && args+=(--prompt-variants $(PROMPT_VARIANTS)); \
	[ -n "$(IGNORE_RULES)" ] && args+=(--ignore-rules); \
	[ -n "$(SHELL_ONLY)" ] && args+=(--shell-only); \
	args+=(--ollama-url "$(if $(OLLAMA_URL),$(OLLAMA_URL),http://127.0.0.1:11434)"); \
	$(PYTHON_BIN) scripts/dev/234_local_copilot_chat_probe.py "$${args[@]}"

local-first-copilot-chat-output-probe:
	@echo "🧪 PR239 probe: raw tool-call JSON leakage in Copilot assistant output"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/copilot_chat_output_contract.json)"); \
	args+=(--chat-report "$(if $(CHAT_REPORT),$(CHAT_REPORT),test-results/234/chat_diagnostics.json)"); \
	$(PYTHON_BIN) scripts/dev/239_copilot_chat_output_probe.py "$${args[@]}"

local-first-copilot-agent-session-probe:
	@echo "🧪 PR239 probe: Copilot Agent session/model contract"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/copilot_agent_session_contract.json)"); \
	args+=(--settings-file "$(if $(SETTINGS_FILE),$(SETTINGS_FILE),.vscode/settings.json)"); \
	$(PYTHON_BIN) scripts/dev/239_copilot_agent_session_probe.py "$${args[@]}"

local-first-local-agent-tool-loop-probe:
	@echo "🧪 PR239 probe: local agent tool-loop health"
	@set -euo pipefail; \
	$(MAKE) local-first-chat-diagnostics MODELS="$(if $(MODEL),$(MODEL),qwen2.5-coder:7b)" CHANNELS=agent PROMPT_VARIANTS=status; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/local_agent_tool_loop_contract.json)"); \
	args+=(--chat-report "$(if $(CHAT_REPORT),$(CHAT_REPORT),test-results/234/chat_diagnostics.json)"); \
	$(PYTHON_BIN) scripts/dev/239_local_agent_tool_loop_probe.py "$${args[@]}"

local-first-copilot-chat-output-gate:
	@echo "🧪 PR239 gate: enforce clean assistant output (no raw tool-call JSON)"
	@set -euo pipefail; \
	$(MAKE) local-first-copilot-agent-session-probe; \
	$(MAKE) local-first-chat-diagnostics; \
	$(MAKE) local-first-copilot-chat-output-probe

local-first-local-agent-tool-loop-gate:
	@echo "🧪 PR239 gate: local-agent-first tool loop + clean assistant output"
	@set -euo pipefail; \
	$(MAKE) local-first-local-agent-tool-loop-probe MODEL="$(if $(MODEL),$(MODEL),qwen2.5-coder:7b)"; \
	$(MAKE) local-first-copilot-chat-output-probe CHAT_REPORT="$(if $(CHAT_REPORT),$(CHAT_REPORT),test-results/234/chat_diagnostics.json)"



local-first-local-model-tool-call-probe:
	@echo "🧪 PR239 probe: local model structured tool-calling capability"
	@set -euo pipefail; \
	args=(); \
	args+=(--model "$(if $(MODEL),$(MODEL),qwen2.5-coder:7b)"); \
	args+=(--ollama-url "$(if $(OLLAMA_URL),$(OLLAMA_URL),http://127.0.0.1:11434)"); \
	$(PYTHON_BIN) scripts/dev/239_local_model_tool_call_probe.py "$${args[@]}"




local-first-pr239-selftest:
	@echo "🧪 PR239 selftest: runtime + model + session + execution lane + extension contract"
	@$(PYTHON_BIN) scripts/dev/239_pr239_selftest.py

local-first-git-status:
	@echo "📌 PR239 execution lane: exact git status"
	@bash scripts/dev/239_local_first_git_status.sh "$(if $(REPO_ROOT),$(REPO_ROOT),$(CURDIR))"

local-first-repo-truth-reply:
	@echo "📌 PR239 repo-truth reply (exact status + deterministic counts)"
	@bash scripts/dev/239_repo_truth_reply.sh "$(if $(REPO_ROOT),$(REPO_ROOT),$(CURDIR))"

local-first-chat-tool-bridge:
	@echo "🧪 PR239 run: local bridge for chat tool-call JSON"
	@set -euo pipefail; 	args=(); 	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/local_tool_bridge_contract.json)"); 	args+=(--repo-root "$(if $(REPO_ROOT),$(REPO_ROOT),$(CURDIR))"); 	[ -n "$(PAYLOAD_FILE)" ] && args+=(--payload-file "$(PAYLOAD_FILE)"); 	[ -n "$(PAYLOAD)" ] && args+=(--payload "$(PAYLOAD)"); 	[ -n "$(MODEL)" ] && args+=(--model "$(MODEL)"); 	[ -n "$(NO_ANALYSIS)" ] && args+=(--no-analysis); 	$(PYTHON_BIN) scripts/dev/239_local_agent_tool_bridge.py "$${args[@]}"

local-first-vscode-agent-log-probe:
	@echo "🧪 PR239 probe: VS Code Agent Debug Log evidence (local tool-loop)"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/vscode_agent_log_contract.json)"); \
	args+=(--log-file "$(LOG_FILE)"); \
	$(PYTHON_BIN) scripts/dev/239_vscode_agent_log_probe.py "$${args[@]}"

local-first-vscode-terminal-tool-loop-probe:
	@echo "🧪 PR239 probe: VS Code terminal tool-loop settings contract"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/vscode_terminal_tool_loop_contract.json)"); \
	args+=(--settings-file "$(if $(SETTINGS_FILE),$(SETTINGS_FILE),.vscode/settings.json)"); \
	$(PYTHON_BIN) scripts/dev/239_vscode_terminal_tool_loop_probe.py "$${args[@]}"

local-first-repo-truth-preflight-probe:
	@echo "🧪 PR236A probe: repo-truth preflight before agent response"
	@set -euo pipefail; \
	args=(); \
	args+=(--model "$(if $(MODEL),$(MODEL),qwen2.5-coder:7b)"); \
	$(PYTHON_BIN) scripts/dev/236_repo_truth_preflight_probe.py "$${args[@]}"

local-first-env-index-readiness-probe:
	@echo "🧪 PR237 probe: environment and repo-index readiness"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/venom_agent_decision_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/237_env_index_readiness_probe.py "$${args[@]}"

local-first-agent-decision-evidence-probe:
	@echo "🧪 PR237 probe: decision evidence schema from repo-truth-first lane"
	@$(PYTHON_BIN) scripts/dev/237_agent_decision_evidence_probe.py

local-first-agent-state-registry-probe:
	@echo "🧪 PR238G probe: canonical agent state registry snapshot"
	@$(PYTHON_BIN) scripts/dev/238g_agent_state_registry_probe.py

local-first-policy-enforcement-probe:
	@echo "🧪 PR237 probe: policy enforcement hook wiring"
	@$(PYTHON_BIN) scripts/dev/237_policy_enforcement_probe.py

local-first-agent-decision-gate:
	@echo "🧪 PR237 final gate: env/index readiness + decision evidence + state registry"
	@set -euo pipefail; \
	args=(); \
	args+=(--state-registry-report "$(if $(STATE_REGISTRY_REPORT),$(STATE_REGISTRY_REPORT),test-results/238g/agent_state_registry_probe.json)"); \
	args+=(--env-index-report "$(if $(ENV_INDEX_REPORT),$(ENV_INDEX_REPORT),test-results/237/env_index_readiness_probe.json)"); \
	args+=(--decision-evidence-report "$(if $(DECISION_EVIDENCE_REPORT),$(DECISION_EVIDENCE_REPORT),test-results/237/agent_decision_evidence_probe.json)"); \
	args+=(--policy-report "$(if $(POLICY_REPORT),$(POLICY_REPORT),test-results/237/policy_enforcement_probe.json)"); \
	$(PYTHON_BIN) scripts/dev/238g_agent_state_registry_probe.py --json-output "$(if $(STATE_REGISTRY_REPORT),$(STATE_REGISTRY_REPORT),test-results/238g/agent_state_registry_probe.json)" --md-output test-results/238g/agent_state_registry_probe.md; \
	$(PYTHON_BIN) scripts/dev/237_agent_decision_gate.py "$${args[@]}"

local-first-agent-config-validate:
	@echo "🧪 Walidacja konfiguracji agentow, promptow i instrukcji"
	@$(PYTHON_BIN) scripts/dev/233c_agent_config_validate.py

local-first-vscode-agent-probe:
	@echo "🧪 PR235 probe: kontrakt terminala VSCODE_AGENT"
	@$(PYTHON_BIN) scripts/dev/235_vscode_agent_probe.py

local-first-utility-models-probe:
	@echo "🧪 PR235 probe: kontrakt utility modeli czatu"
	@set -euo pipefail; \
	args=(); \
	args+=(--settings-file "$(if $(SETTINGS_FILE),$(SETTINGS_FILE),config/chat_operator/vscode_chat_models_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/235_utility_models_probe.py "$${args[@]}"

local-first-workspace-context-probe:
	@echo "🧪 PR235 probe: kontrakt workspace context (AGENTS.md/#codebase/index)"
	@set -euo pipefail; \
	args=(); \
	args+=(--settings-file "$(if $(SETTINGS_FILE),$(SETTINGS_FILE),config/chat_operator/vscode_workspace_context_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/235_workspace_context_probe.py "$${args[@]}"

local-first-decision-gate:
	@echo "🧪 PR235 decision gate: finalny kontrakt modeli i routingu"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/decision_gate_contract.json)"); \
	[ -n "$(STRICT_REPO_TRUTH)" ] && args+=(--strict-repo-truth); \
	$(PYTHON_BIN) scripts/dev/235_decision_gate.py "$${args[@]}"

local-first-full-agent-contract-probe:
	@echo "🧪 PR236 probe: kontrakt pelnego agenta Venom"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/venom_full_agent_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/236_full_agent_contract_probe.py "$${args[@]}"

local-first-full-agent-debug-probe:
	@echo "🧪 PR236 probe: debug loop pelnego agenta Venom"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/venom_full_agent_debug_contract.json)"); \
	args+=(--settings-file "$(if $(SETTINGS_FILE),$(SETTINGS_FILE),.vscode/settings.json)"); \
	$(PYTHON_BIN) scripts/dev/236_full_agent_debug_probe.py "$${args[@]}"

local-first-full-agent-handoff-probe:
	@echo "🧪 PR236 probe: handoff implementation pelnego agenta Venom"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/venom_full_agent_handoff_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/236_full_agent_handoff_probe.py "$${args[@]}"

local-first-full-agent-tool-probe:
	@echo "🧪 PR236 probe: tool-loop pelnego agenta Venom"
	@set -euo pipefail; \
	args=(); \
	args+=(--contract "$(if $(CONTRACT_FILE),$(CONTRACT_FILE),config/chat_operator/venom_full_agent_tool_contract.json)"); \
	$(PYTHON_BIN) scripts/dev/236_full_agent_tool_probe.py "$${args[@]}"

local-first-full-agent-gate:
	@echo "🧪 PR236 final gate: persona, tools, debug i handoff pelnego agenta Venom"
	@set -euo pipefail; \
	args=(); \
	args+=(--persona-report "$(if $(PERSONA_REPORT),$(PERSONA_REPORT),test-results/236/full_agent_contract.json)"); \
	args+=(--tool-report "$(if $(TOOL_REPORT),$(TOOL_REPORT),test-results/236/full_agent_tool.json)"); \
	args+=(--debug-report "$(if $(DEBUG_REPORT),$(DEBUG_REPORT),test-results/236/full_agent_debug.json)"); \
	args+=(--handoff-report "$(if $(HANDOFF_REPORT),$(HANDOFF_REPORT),test-results/236/full_agent_handoff.json)"); \
	$(PYTHON_BIN) scripts/dev/236_full_agent_gate.py "$${args[@]}"

local-first-profile-status:
	@echo "📄 Status profilu local-first w shellu"
	@bash scripts/dev/233a_local_first_profile.sh status

local-first-profile-install:
	@echo "📄 Instalacja profilu local-first do ~/.bashrc"
	@bash scripts/dev/233a_local_first_profile.sh install

local-first-profile-remove:
	@echo "📄 Usunięcie profilu local-first z ~/.bashrc"
	@bash scripts/dev/233a_local_first_profile.sh remove

local-first-profile-print:
	@echo "📄 Podgląd exportów local-first"
	@bash scripts/dev/233a_local_first_profile.sh print

local-first-profile-backup:
	@echo "🗂️  Snapshot profilu as-is"
	@bash scripts/dev/233a_local_first_profile.sh backup

local-first-profile-list-backups:
	@echo "🗂️  Lista snapshotów profilu"
	@bash scripts/dev/233a_local_first_profile.sh list-backups

local-first-profile-restore:
	@echo "♻️  Przywracanie profilu z backupu (domyślnie ostatni)"
	@RESTORE_FILE="$${RESTORE_FILE:-}" bash scripts/dev/233a_local_first_profile.sh restore
