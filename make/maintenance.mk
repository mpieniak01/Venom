# =============================================================================
# Odchudzanie środowiska (Repo + Docker)
# =============================================================================

env-audit:
	@$(PYTHON_BIN) scripts/dev/env_audit.py

make-targets-audit:
	@$(PYTHON_BIN) scripts/dev/make_targets_audit.py --makefile Makefile --modules-dir make

audit-dead-code:
	@$(PYTHON_BIN) scripts/dev/dead_code_audit.py

audit-dead-code-vulture-install:
	@$(PYTHON_BIN) -m pip install "vulture==2.14"

audit-dead-code-full:
	@$(PYTHON_BIN) scripts/dev/dead_code_audit.py --with-vulture

security-delta-scan:
	@$(PYTHON_BIN) scripts/dev/security_delta_scan.py --out-json logs/security-delta-latest.json

security-delta-scan-strict:
	@$(PYTHON_BIN) scripts/dev/security_delta_scan.py --out-json logs/security-delta-latest.json --strict

env-clean-safe:
	@bash scripts/dev/env_cleanup.sh safe

env-clean-docker-safe:
	@bash scripts/dev/docker_cleanup.sh safe

env-clean-deep:
	@bash scripts/dev/env_cleanup.sh deep
	@bash scripts/dev/docker_cleanup.sh deep

env-report-diff:
	@$(PYTHON_BIN) scripts/dev/env_report_diff.py

stack-stability-audit:
	@$(PYTHON_BIN) scripts/dev/stack_stability_audit.py --env-file "$(ENV_FILE)" --backend-port "$(PORT)" --web-port "$(WEB_PORT)"

llm-runtime-stability-audit:
	@$(PYTHON_BIN) scripts/dev/llm_runtime_stability_audit.py --env-file "$(ENV_FILE)" --fail-on-errors

llm-runtime-stability-cycle-start:
	@$(PYTHON_BIN) scripts/dev/llm_runtime_stability_audit.py --env-file "$(ENV_FILE)" --stack-cycle start --fail-on-errors

llm-runtime-stability-cycle-start2:
	@$(PYTHON_BIN) scripts/dev/llm_runtime_stability_audit.py --env-file "$(ENV_FILE)" --stack-cycle start2 --fail-on-errors

# =============================================================================
# Konserwacja MCP
# =============================================================================

mcp-clean:
	@echo "🧹 Czyszczenie repozytoriów i venv MCP..."
	@rm -rf venom_core/skills/mcp/_repos/*
	@rm -f venom_core/skills/custom/mcp_*.py
	@echo "✅ Wyczyszczono."

mcp-status:
	@echo "📋 Zaimportowane narzędzia MCP (katalogi _repos):"
	@ls -1 venom_core/skills/mcp/_repos 2>/dev/null || echo "Brak."
	@echo "📝 Wygenerowane wrappery (.py):"
	@ls -1 venom_core/skills/custom/mcp_*.py 2>/dev/null || echo "Brak."
