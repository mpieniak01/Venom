# =============================================================================
# Odchudzanie środowiska (Repo + Docker)
# =============================================================================

env-audit:
	@python3 scripts/dev/env_audit.py

make-targets-audit:
	@$(PYTHON_BIN) scripts/dev/make_targets_audit.py --makefile Makefile --modules-dir make

audit-dead-code:
	@python3 scripts/dev/dead_code_audit.py

security-delta-scan:
	@python3 scripts/dev/security_delta_scan.py --out-json logs/security-delta-latest.json

security-delta-scan-strict:
	@python3 scripts/dev/security_delta_scan.py --out-json logs/security-delta-latest.json --strict

env-clean-safe:
	@bash scripts/dev/env_cleanup.sh safe

env-clean-docker-safe:
	@bash scripts/dev/docker_cleanup.sh safe

env-clean-deep:
	@bash scripts/dev/env_cleanup.sh deep
	@bash scripts/dev/docker_cleanup.sh deep

env-report-diff:
	@python3 scripts/dev/env_report_diff.py

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
