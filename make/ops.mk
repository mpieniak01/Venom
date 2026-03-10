# Workspace modules
modules-status:
	@bash scripts/modules_workspace.sh status

modules-pull:
	@bash scripts/modules_workspace.sh pull

modules-branches:
	@bash scripts/modules_workspace.sh branches

# Usage:
# make modules-exec CMD='git status -s'
modules-exec:
	@if [ -z "$${CMD:-}" ]; then \
		echo "Usage: make modules-exec CMD='git status -s'"; \
		exit 1; \
	fi
	@bash scripts/modules_workspace.sh exec "$${CMD}"

# Runtime maintenance
runtime-maintenance-cleanup:
	@$(ENV_RUN) $(PYTHON_BIN) scripts/dev/runtime_maintenance_cleanup.py

runtime-log-policy-audit:
	@echo "🔎 Runtime log policy audit..."
	@echo " - logger backend policy: daily rotation + 7 days retention (venom_core/utils/logger.py)"
	@if [ -f /etc/logrotate.d/venom ]; then \
		echo " - system logrotate: /etc/logrotate.d/venom [FOUND]"; \
	else \
		echo " - system logrotate: /etc/logrotate.d/venom [MISSING]"; \
		echo "   use: make runtime-logrotate-install-help"; \
	fi
	@echo " - runtime retention marker: .venom_runtime/runtime_retention.last_run"
	@cat .venom_runtime/runtime_retention.last_run 2>/dev/null || echo "   (missing marker)"

runtime-logrotate-install-help:
	@echo "📄 Install template for system logrotate policy:"
	@echo "  sudo cp scripts/systemd/venom.logrotate.example /etc/logrotate.d/venom"
	@echo "  sudo sed -i \"s|/path/to/Venom|$$(pwd)|g\" /etc/logrotate.d/venom"
	@echo "  sudo logrotate -d /etc/logrotate.d/venom"

# Monitoring
monitor:
	@if [ -f scripts/diagnostics/system_snapshot.sh ]; then \
		bash scripts/diagnostics/system_snapshot.sh; \
	else \
		echo "❌ Skrypt scripts/diagnostics/system_snapshot.sh nie istnieje"; \
		exit 1; \
	fi
