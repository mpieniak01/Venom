# Makefile dla Venom – rozdzielony backend FastAPI + frontend Next.js

ENVIRONMENT ?= dev
PROFILE ?= full
VENV ?= .venv
REPO_ROOT ?= $(CURDIR)
PYTHON_BIN ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PYTEST_BIN ?= $(if $(wildcard $(VENV)/bin/pytest),$(VENV)/bin/pytest,pytest)
UVICORN ?= $(VENV)/bin/uvicorn
API_APP ?= venom_core.main:app
HOST ?= 0.0.0.0
HOST_DISPLAY ?= 127.0.0.1
PORT ?= $(if $(filter preprod,$(ENVIRONMENT)),8100,$(if $(filter prod,$(ENVIRONMENT)),8200,8000))
PID_FILE ?= .venom.pid
NPM ?= npm
WEB_DIR ?= web-next
WEB_PORT ?= $(if $(filter preprod,$(ENVIRONMENT)),3100,$(if $(filter prod,$(ENVIRONMENT)),3200,3000))
WEB_HOST ?= 0.0.0.0
WEB_DISPLAY ?= 127.0.0.1
WEB_API_PROXY_TARGET ?= $(if $(strip $(API_PROXY_TARGET)),$(API_PROXY_TARGET),http://$(HOST_DISPLAY):$(PORT))
WEB_PID_FILE ?= .web-next.pid
NEXT_DEV_ENV ?= NEXT_MODE=dev NEXT_DISABLE_TURBOPACK=1 NEXT_TELEMETRY_DISABLED=1
NEXT_PROD_ENV ?= NEXT_MODE=prod NEXT_TELEMETRY_DISABLED=1
NEXT_TURBO_WATCH_ENV ?= WATCHPACK_POLLING=true WATCHPACK_POLLING_INTERVAL=1000 CHOKIDAR_USEPOLLING=1
START_MODE ?= dev
START_WEB_MODE ?= turbo
ALLOW_DEGRADED_START ?= 0
BACKEND_RELOAD ?= 0
UVICORN_DEV_FLAGS ?= --reload --reload-dir venom_core --reload-dir scripts --reload-exclude logs/\* --reload-exclude data/\* --reload-exclude models/\* --reload-exclude web-next/\* --reload-exclude .venv/\* --reload-exclude .git/\*
UVICORN_PROD_FLAGS ?= --no-server-header
BACKEND_LOG ?= logs/backend.log
WEB_LOG ?= logs/web-next.log
WEB_NODE_PATH ?= $(abspath $(WEB_DIR)/node_modules)
WEB_START_RETRIES ?= 1
# Leave empty by default: start_stack.sh resolves from .env (VLLM_ENDPOINT)
# and falls back to http://127.0.0.1:8001/v1 when not configured.
VLLM_ENDPOINT ?=
VLLM_START_TIMEOUT_SEC ?= 240
ENV_FILE ?= .env.$(ENVIRONMENT)
ENV_EXAMPLE_FILE ?= .env.$(ENVIRONMENT).example
ENV_RUN ?= $(PYTHON_BIN) -m dotenv -f "$(ENV_FILE)" run --no-override --
ENV_RUN_ABS ?= $(abspath $(PYTHON_BIN)) -m dotenv -f "$(abspath $(ENV_FILE))" run --no-override --
WEB_APP_VERSION ?= $(shell node -p "require('./web-next/package.json').version" 2>/dev/null || echo unknown)
PREPROD_ENV_BASE := ENV_FILE=.env.preprod ENV_EXAMPLE_FILE=.env.preprod.example
PREPROD_ENV_READONLY := $(PREPROD_ENV_BASE) ENVIRONMENT_ROLE=preprod DB_SCHEMA=preprod CACHE_NAMESPACE=preprod QUEUE_NAMESPACE=preprod STORAGE_PREFIX=preprod ALLOW_DATA_MUTATION=0
PREPROD_ENV_MUTATION := $(PREPROD_ENV_BASE) ENVIRONMENT_ROLE=preprod DB_SCHEMA=preprod CACHE_NAMESPACE=preprod QUEUE_NAMESPACE=preprod STORAGE_PREFIX=preprod ALLOW_DATA_MUTATION=1
export ENV_FILE
export ENV_EXAMPLE_FILE

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

PORTS_TO_CLEAN := $(PORT) $(WEB_PORT)

.PHONY: lint format test test-data test-unit test-smoke test-perf test-all test-artifacts-cleanup install-hooks sync-sonar-new-code-group stack-plan start start-dev start-dev-webpack start-dev-turbo start-lowmem start-prod start-prod-confirm start-preprod stop restart status clean-ports \
		pytest e2e test-optimal test-ci-lite test-fast-coverage check-new-code-coverage check-new-code-coverage-diagnostics check-new-code-coverage-local sonar-reports-backend-new-code pr-fast agent-pr-fast pr-fast-local \
		ci-lite-preflight ci-lite-bootstrap audit-ci-lite agent-prep \
		test-intelligence-report \
		runtime-maintenance-cleanup \
		runtime-log-policy-audit runtime-logrotate-install-help \
		api api-dev api-preprod api-stop web web-dev web-dev-turbo web-dev-turbo-debug web-preprod web-stop \
		test-web-unit test-web-e2e test-web-turbo-smoke test-web-turbo-smoke-clean \
		test-202b-gate test-202b-web-gate test-202b-web-perf test-202b-global-p95 \
		test-202d-lora-onnx-deploy test-202d-lora-onnx-smoke test-202d-all \
		test-duration-audit test-light-coverage test-llm-manual test-group-plan test-group-fast test-group-long test-group-heavy \
		preprod-backup preprod-restore preprod-verify preprod-audit preprod-drill preprod-readiness-check \
		vllm-start vllm-stop vllm-restart ollama-start ollama-stop ollama-restart multi-runtime-start multi-runtime-stop multi-runtime-restart multi-runtime-hygiene voice-route-profile-show voice-route-profile-set \
		local-first-start local-first-status local-first-codex local-first-stop local-first-unload local-first-unload-all \
		local-repo-status local-repo-status-json \
		local-first-repo-truth-agent \
		local-first-pr240-orchestrator-routing-probe \
		local-first-pr240-full-agent-handoff-probe \
		local-first-pr241-selftest local-first-pr241-selftest-json \
		local-first-pr241b-probe local-first-pr241b-probe-json \
		local-first-feedback-probe local-first-tool-flake-probe local-first-operator-tool-profile-probe local-first-chat-diagnostics local-first-agent-config-validate \
		local-first-copilot-chat-output-probe local-first-copilot-agent-session-probe local-first-copilot-chat-output-gate \
		local-first-local-agent-tool-loop-probe local-first-local-agent-tool-loop-gate local-first-vscode-agent-log-probe local-first-vscode-terminal-tool-loop-probe local-first-local-model-tool-call-probe local-first-pr239-selftest local-first-git-status local-first-repo-truth-reply local-first-chat-tool-bridge \
		local-first-repo-truth-preflight-probe \
		local-first-vscode-agent-probe local-first-utility-models-probe local-first-workspace-context-probe local-first-decision-gate \
		local-first-full-agent-contract-probe local-first-full-agent-debug-probe local-first-full-agent-handoff-probe local-first-full-agent-tool-probe local-first-full-agent-gate \
		local-first-env-index-readiness-probe local-first-agent-decision-evidence-probe local-first-agent-state-registry-probe local-first-policy-enforcement-probe local-first-agent-decision-gate \
		local-first-help \
		local-first-profile-status local-first-profile-install local-first-profile-remove local-first-profile-print \
		local-first-profile-backup local-first-profile-list-backups local-first-profile-restore \
		monitor mcp-clean mcp-status sonar-reports sonar-reports-backend sonar-reports-frontend openapi-export openapi-codegen-types ensure-env-file \
		ensure-preprod-env-file \
		env-audit audit-dead-code audit-dead-code-vulture-install audit-dead-code-full make-targets-audit chat-operator-docs-drift-audit operator-manual-docs-drift-audit the-chat-docs-drift-audit security-delta-scan security-delta-scan-strict env-clean-safe env-clean-docker-safe env-clean-deep env-report-diff stack-stability-audit llm-runtime-stability-audit llm-runtime-stability-cycle-start llm-runtime-stability-cycle-start2 test-preprod-readonly-smoke help \
		modules-status modules-pull modules-branches modules-exec architecture-drift-check architecture-sonar-export optional-modules-contracts-check test-lane-contracts-check test-catalog-sync test-catalog-check test-groups-sync test-groups-check test-dynamic-preview check-file-coverage-floor \
		test-202c-diagnostics-contract test-202c-diagnostics-runtime test-202c-diagnostics-perf test-202c-diagnostics-report test-202c-diagnostics-all \
		test-202c1-parity-semantic test-202c1-perf-warm test-202c1-model-selection test-202c1-lora-path test-202c1-all \
		test-202c2-parity-judge test-202c2-perf-tuning test-202c2-all \
		test-202c3-perf-profile test-202c3-all \
		test-202c4-automation-matrix test-202c4-decision-refined test-202c4-all \
		test-202c5-lora-runtime-gap test-202c6-signature-contract-smoke test-202c7-signed-activation-success \
		test-env-contracts-ollama test-env-contracts-vllm test-env-contracts-multi-runtime test-223e-slo-gate test-223e-slo-consecutive

lint:
	pre-commit run --all-files

format:
	black . && isort .

-include make/tests.mk
-include make/maintenance.mk
-include make/preprod.mk
-include make/runtime.mk
-include make/ops.mk
-include make/help.mk
-include make/legacy.mk

define ensure_process_not_running
	@if [ -f $(2) ]; then \
		PID=$$(cat $(2)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⚠️  $(1) już działa (PID $$PID). Użyj 'make stop' lub 'make restart'."; \
			exit 1; \
		else \
			rm -f $(2); \
		fi; \
	fi
endef

define handle_pytest_no_tests
	if [ $$rc -eq 5 ]; then \
		echo ""; \
		echo "⚠️  make $(1): pytest zakończył się kodem 5 (brak zebranych testów)."; \
		echo "   Sprawdź grupy testowe i katalog testów:"; \
		echo "   - make test-groups-check"; \
		echo "   - make test-catalog-check"; \
		exit $$rc; \
	fi;
endef

define run_web_lifecycle
	@WEB_DIR="$(abspath $(WEB_DIR))" WEB_PID_FILE="$(abspath $(WEB_PID_FILE))" WEB_LOG="$(abspath $(WEB_LOG))" WEB_HOST="$(WEB_HOST)" WEB_PORT="$(WEB_PORT)" NPM="$(NPM)" API_PROXY_TARGET="$(WEB_API_PROXY_TARGET)" NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="${ENVIRONMENT_ROLE:-dev}" $(ENV_RUN_ABS) node "$(abspath web-next/scripts/web-lifecycle.mjs)" $(1)
endef

# Public contract: make start PROFILE=full|light ENVIRONMENT=dev|preprod
start: ensure-env-file _start

# Compatibility aliases, scheduled for removal after the next release.
start-dev start-dev-turbo: ENVIRONMENT=dev
start-dev start-dev-turbo: start

start-dev-webpack: START_WEB_MODE=webpack
start-dev-webpack: start

start-lowmem: PROFILE=light
start-lowmem: start

start-prod: ENVIRONMENT=prod
start-prod: start-prod-confirm start

stack-plan:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" PORT="$(PORT)" WEB_PORT="$(WEB_PORT)" $(PYTHON_BIN) scripts/dev/stack_profile.py plan

start-prod-confirm:
	@echo "⚠️  OSTRZEŻENIE: tryb 'prod' nie jest jeszcze oficjalnie zwalidowany/rekomendowany operacyjnie."
	@echo "⚠️  Zalecane środowiska: 'dev' (testy/prace) oraz 'preprod' (UAT + smoke read-only)."
	@if [ "$${PROD_START_CONFIRM:-ask}" = "yes" ] || [ "$${PROD_START_CONFIRM:-ask}" = "1" ]; then \
		echo "✅ Potwierdzenie start-prod przez PROD_START_CONFIRM."; \
	elif [ ! -t 0 ]; then \
		echo "❌ Brak interaktywnego terminala. Użyj: PROD_START_CONFIRM=yes make start-prod"; \
		exit 1; \
	else \
		read -r -p "Czy na pewno uruchomić start-prod? [tak/nie]: " _prod_answer; \
		case "$$_prod_answer" in \
			tak|t|yes|y) echo "✅ Potwierdzono start-prod."; ;; \
			*) echo "❌ Przerwano start-prod."; exit 1 ;; \
		esac; \
	fi


_start:
	@MAKE_BIN="$${MAKE:-make}" \
		PYTHON_BIN="$(PYTHON_BIN)" \
		UVICORN="$(UVICORN)" API_APP="$(API_APP)" HOST="$(HOST)" HOST_DISPLAY="$(HOST_DISPLAY)" PORT="$(PORT)" \
		$(if $(filter command line environment environment override,$(origin PID_FILE)),PID_FILE="$(PID_FILE)") WEB_DIR="$(WEB_DIR)" WEB_PORT="$(WEB_PORT)" WEB_HOST="$(WEB_HOST)" WEB_DISPLAY="$(WEB_DISPLAY)" $(if $(filter command line environment environment override,$(origin WEB_PID_FILE)),WEB_PID_FILE="$(WEB_PID_FILE)") \
		ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" $(if $(filter prod,$(ENVIRONMENT)),START_MODE=prod) START_WEB_MODE="$(START_WEB_MODE)" ALLOW_DEGRADED_START="$(ALLOW_DEGRADED_START)" BACKEND_RELOAD="$(BACKEND_RELOAD)" \
		UVICORN_DEV_FLAGS="$(UVICORN_DEV_FLAGS)" UVICORN_PROD_FLAGS="$(UVICORN_PROD_FLAGS)" $(if $(filter command line environment environment override,$(origin BACKEND_LOG)),BACKEND_LOG="$(BACKEND_LOG)") $(if $(filter command line environment environment override,$(origin WEB_LOG)),WEB_LOG="$(WEB_LOG)") \
		API_PROXY_TARGET="$(WEB_API_PROXY_TARGET)" WEB_NODE_PATH="$(WEB_NODE_PATH)" WEB_APP_VERSION="$(WEB_APP_VERSION)" WEB_START_RETRIES="$(WEB_START_RETRIES)" \
		$(if $(VLLM_ENDPOINT),VLLM_ENDPOINT="$(VLLM_ENDPOINT)") VLLM_START_TIMEOUT_SEC="$(VLLM_START_TIMEOUT_SEC)" \
		ENV_FILE="$(ENV_FILE)" ENV_EXAMPLE_FILE="$(ENV_EXAMPLE_FILE)" NPM="$(NPM)" \
		$(PYTHON_BIN) scripts/dev/stack_profile.py start

stop:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" $(PYTHON_BIN) scripts/dev/stack_profile.py stop

restart:
	@$(MAKE) --no-print-directory stop ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)"
	@$(MAKE) --no-print-directory start ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)"

status:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" $(PYTHON_BIN) scripts/dev/stack_profile.py status

clean-ports:
	@for PORT_TO_CHECK in $(PORTS_TO_CLEAN); do \
		PIDS=$$(bash scripts/dev/port_pids.sh "$$PORT_TO_CHECK" || true); \
		if [ -n "$$PIDS" ]; then \
			echo "⚠️  Port $$PORT_TO_CHECK zajęty przez $$PIDS – kończę procesy"; \
			kill $$PIDS 2>/dev/null || true; \
		fi; \
	done

# =============================================================================
# Profil lekki (Light Profile) - komponenty do uruchamiania osobno
# =============================================================================

# Backend API (tylko) - produkcyjny (bez autoreload)
api:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" PORT="$(PORT)" WEB_PORT="$(WEB_PORT)" $(PYTHON_BIN) scripts/dev/stack_profile.py component api

_api:
	@if [ ! -x "$(UVICORN)" ]; then \
		echo "❌ Nie znaleziono uvicorn w $(UVICORN). Czy środowisko .venv jest zainstalowane?"; \
		exit 1; \
	fi
	@mkdir -p logs
	$(call ensure_process_not_running,Venom backend,$(PID_FILE))
	@echo "▶️  Uruchamiam Venom API (produkcyjny, bez --reload) na $(HOST):$(PORT)"
	: > $(BACKEND_LOG)
	$(ENV_RUN) setsid $(UVICORN) $(API_APP) --host $(HOST) --port $(PORT) $(UVICORN_PROD_FLAGS) >> $(BACKEND_LOG) 2>&1 & \
	echo $$! > $(PID_FILE)
	@echo "✅ Venom API wystartował z PID $$(cat $(PID_FILE))"
	@echo "📡 Backend: http://$(HOST):$(PORT)"

# Backend API (tylko) - developerski (z autoreload)
api-dev:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" PORT="$(PORT)" WEB_PORT="$(WEB_PORT)" $(PYTHON_BIN) scripts/dev/stack_profile.py component api-dev

_api-dev:
	@if [ ! -x "$(UVICORN)" ]; then \
		echo "❌ Nie znaleziono uvicorn w $(UVICORN). Czy środowisko .venv jest zainstalowane?"; \
		exit 1; \
	fi
	@mkdir -p logs
	$(call ensure_process_not_running,Venom backend,$(PID_FILE))
	@echo "▶️  Uruchamiam Venom API (developerski, z --reload) na $(HOST):$(PORT)"
	: > $(BACKEND_LOG)
	$(ENV_RUN) setsid $(UVICORN) $(API_APP) --host $(HOST) --port $(PORT) $(UVICORN_DEV_FLAGS) >> $(BACKEND_LOG) 2>&1 & \
	echo $$! > $(PID_FILE)
	@echo "✅ Venom API wystartował z PID $$(cat $(PID_FILE))"
	@echo "📡 Backend: http://$(HOST):$(PORT)"
	@echo "🔄 Autoreload: aktywny (zmiana plików → restart)"

api-preprod: ENVIRONMENT=preprod
api-preprod: ENV_FILE=.env.preprod
api-preprod: ENV_EXAMPLE_FILE=.env.preprod.example
api-preprod: export ENVIRONMENT_ROLE=preprod
api-preprod: export DB_SCHEMA=preprod
api-preprod: export CACHE_NAMESPACE=preprod
api-preprod: export QUEUE_NAMESPACE=preprod
api-preprod: export STORAGE_PREFIX=preprod
api-preprod: export ALLOW_DATA_MUTATION=0
api-preprod: api

# Zatrzymaj tylko backend
api-stop:
	@ENVIRONMENT="$(ENVIRONMENT)" PROFILE="$(PROFILE)" ENV_FILE="$(ENV_FILE)" $(PYTHON_BIN) scripts/dev/stack_profile.py component api-stop

# Frontend: build explicitly, then start only a compatible prepared artifact.
web-build:
	$(call run_web_lifecycle,build)

web:
	$(call run_web_lifecycle,start)

# Diagnostic Webpack shares the lifecycle; the daily stack uses Turbo.
web-dev:
	$(call run_web_lifecycle,dev webpack)

web-dev-turbo:
	$(call run_web_lifecycle,dev turbo)

web-dev-turbo-debug:
	$(call run_web_lifecycle,dev turbo-debug)

web-preprod: ENV_FILE=.env.preprod
web-preprod: ENV_EXAMPLE_FILE=.env.preprod.example
web-preprod: export ENVIRONMENT_ROLE=preprod
web-preprod: export DB_SCHEMA=preprod
web-preprod: export CACHE_NAMESPACE=preprod
web-preprod: export QUEUE_NAMESPACE=preprod
web-preprod: export STORAGE_PREFIX=preprod
web-preprod: export ALLOW_DATA_MUTATION=0
web-preprod: web
# Zatrzymaj tylko frontend
web-stop:
	@trap '' TERM INT
	@if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			echo "⏹️  Zatrzymuję UI (PID $$WPID)"; \
			kill $$WPID 2>/dev/null || true; \
			for attempt in {1..20}; do \
				if kill -0 $$WPID 2>/dev/null; then \
					sleep 0.2; \
				else \
					break; \
				fi; \
			done; \
		else \
			echo "⚠️  Proces UI ($$WPID) już nie działa"; \
		fi; \
		rm -f $(WEB_PID_FILE); \
	else \
		echo "ℹ️  UI (Next.js) nie jest uruchomione"; \
	fi
	@pkill -f "next dev" 2>/dev/null || true
	@pkill -f "next start" 2>/dev/null || true
	@echo "✅ UI (Next.js) zatrzymany"
