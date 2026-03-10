# Makefile dla Venom – rozdzielony backend FastAPI + frontend Next.js

VENV ?= .venv
REPO_ROOT ?= $(CURDIR)
PYTHON_BIN ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PYTEST_BIN ?= $(if $(wildcard $(VENV)/bin/pytest),$(VENV)/bin/pytest,pytest)
UVICORN ?= $(VENV)/bin/uvicorn
API_APP ?= venom_core.main:app
HOST ?= 0.0.0.0
HOST_DISPLAY ?= 127.0.0.1
PORT ?= 8000
PID_FILE ?= .venom.pid
NPM ?= npm
WEB_DIR ?= web-next
WEB_PORT ?= 3000
WEB_HOST ?= 0.0.0.0
WEB_DISPLAY ?= 127.0.0.1
WEB_PID_FILE ?= .web-next.pid
NEXT_DEV_ENV ?= NEXT_MODE=dev NEXT_DISABLE_TURBOPACK=1 NEXT_TELEMETRY_DISABLED=1
NEXT_PROD_ENV ?= NEXT_MODE=prod NEXT_TELEMETRY_DISABLED=1
NEXT_TURBO_WATCH_ENV ?= WATCHPACK_POLLING=true WATCHPACK_POLLING_INTERVAL=1000 CHOKIDAR_USEPOLLING=1
START_MODE ?= dev
START_WEB_MODE ?= webpack
ALLOW_DEGRADED_START ?= 0
BACKEND_RELOAD ?= 0
UVICORN_DEV_FLAGS ?= --reload --reload-dir venom_core --reload-dir scripts --reload-exclude logs/\* --reload-exclude data/\* --reload-exclude models/\* --reload-exclude web-next/\* --reload-exclude .venv/\* --reload-exclude .git/\*
UVICORN_PROD_FLAGS ?= --no-server-header
BACKEND_LOG ?= logs/backend.log
WEB_LOG ?= logs/web-next.log
WEB_NODE_PATH ?= $(abspath $(WEB_DIR)/node_modules)
# Leave empty by default: start_stack.sh resolves from .env (VLLM_ENDPOINT)
# and falls back to http://127.0.0.1:8001/v1 when not configured.
VLLM_ENDPOINT ?=
VLLM_START_TIMEOUT_SEC ?= 240
ENV_FILE ?= .env.dev
ENV_EXAMPLE_FILE ?= .env.dev.example
ENV_RUN ?= $(PYTHON_BIN) -m dotenv -f "$(ENV_FILE)" run --
ENV_RUN_ABS ?= $(abspath $(PYTHON_BIN)) -m dotenv -f "$(abspath $(ENV_FILE))" run --
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

.PHONY: lint format test test-data test-unit test-smoke test-perf test-all test-artifacts-cleanup install-hooks sync-sonar-new-code-group start start2 start-dev start-dev-webpack start-dev-turbo start-prod start-preprod stop restart status clean-ports \
		pytest e2e test-optimal test-ci-lite test-fast-coverage test-light-coverage check-new-code-coverage check-new-code-coverage-diagnostics check-new-code-coverage-local sonar-reports-backend-new-code pr-fast agent-pr-fast pr-fast-local \
		ci-lite-preflight ci-lite-bootstrap audit-ci-lite \
		test-intelligence-report \
		runtime-maintenance-cleanup \
		runtime-log-policy-audit runtime-logrotate-install-help \
		api api-dev api-preprod api-stop web web-dev web-dev-turbo web-dev-turbo-debug web-preprod web-stop \
		test-web-unit test-web-e2e test-web-turbo-smoke test-web-turbo-smoke-clean \
		startpre stoppre restartpre statuspre apipre webpre testpre ensurepreenv \
		preprod-backup preprod-restore preprod-verify preprod-audit preprod-drill preprod-readiness-check prebackup prerestore preverify preaudit predrill prereadiness \
		vllm-start vllm-stop vllm-restart ollama-start ollama-stop ollama-restart \
		monitor mcp-clean mcp-status sonar-reports sonar-reports-backend sonar-reports-frontend openapi-export openapi-codegen-types ensure-env-file \
		ensure-preprod-env-file \
		env-audit audit-dead-code make-targets-audit security-delta-scan security-delta-scan-strict env-clean-safe env-clean-docker-safe env-clean-deep env-report-diff test-preprod-readonly-smoke help \
		modules-status modules-pull modules-branches modules-exec architecture-drift-check architecture-sonar-export optional-modules-contracts-check test-lane-contracts-check test-catalog-sync test-catalog-check test-groups-sync test-groups-check test-dynamic-preview check-file-coverage-floor

lint:
	pre-commit run --all-files

format:
	black . && isort .

-include make/tests.mk
-include make/maintenance.mk
-include make/preprod.mk
-include make/runtime.mk
-include make/ops.mk

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

define start_web_turbo_target
	@mkdir -p logs
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@echo "▶️  Uruchamiam UI ($(1), host $(WEB_HOST), port $(WEB_PORT))"
	cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev $(NEXT_TURBO_WATCH_ENV) $(4) $(ENV_RUN_ABS) setsid $(NPM) run $(2) -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI ($(1)) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"
	@echo "$(3)"
endef

start: start-dev

start-dev:
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=dev START_WEB_MODE=webpack _start

start2: start-dev-turbo

start-dev-webpack:
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=dev START_WEB_MODE=webpack _start

start-dev-turbo:
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=dev START_WEB_MODE=turbo _start

start-prod:
	@echo "⚠️  OSTRZEŻENIE: tryb 'prod' nie jest jeszcze oficjalnie zwalidowany/rekomendowany operacyjnie."
	@echo "⚠️  Zalecane środowiska: 'dev' (testy/prace) oraz 'preprod' (UAT + smoke read-only)."
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=prod _start


_start:
	@MAKE_BIN="$(MAKE)" \
		PYTHON_BIN="$(PYTHON_BIN)" \
		UVICORN="$(UVICORN)" API_APP="$(API_APP)" HOST="$(HOST)" HOST_DISPLAY="$(HOST_DISPLAY)" PORT="$(PORT)" \
		PID_FILE="$(PID_FILE)" WEB_DIR="$(WEB_DIR)" WEB_PORT="$(WEB_PORT)" WEB_HOST="$(WEB_HOST)" WEB_DISPLAY="$(WEB_DISPLAY)" WEB_PID_FILE="$(WEB_PID_FILE)" \
		START_MODE="$(START_MODE)" START_WEB_MODE="$(START_WEB_MODE)" ALLOW_DEGRADED_START="$(ALLOW_DEGRADED_START)" BACKEND_RELOAD="$(BACKEND_RELOAD)" \
		UVICORN_DEV_FLAGS="$(UVICORN_DEV_FLAGS)" UVICORN_PROD_FLAGS="$(UVICORN_PROD_FLAGS)" BACKEND_LOG="$(BACKEND_LOG)" WEB_LOG="$(WEB_LOG)" \
		WEB_NODE_PATH="$(WEB_NODE_PATH)" WEB_APP_VERSION="$(WEB_APP_VERSION)" \
		VLLM_ENDPOINT="$(VLLM_ENDPOINT)" VLLM_START_TIMEOUT_SEC="$(VLLM_START_TIMEOUT_SEC)" \
		ENV_FILE="$(ENV_FILE)" ENV_EXAMPLE_FILE="$(ENV_EXAMPLE_FILE)" NPM="$(NPM)" \
		bash scripts/dev/start_stack.sh

stop:
	@bash scripts/stop_venom.sh

restart: stop start

status:
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "✅ Venom działa (PID $$PID)"; \
		else \
			echo "⚠️  PID_FILE istnieje, ale proces $$PID nie żyje"; \
		fi; \
	else \
		echo "ℹ️  Venom nie jest uruchomiony"; \
	fi
	@if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			echo "✅ UI (Next.js) działa (PID $$WPID)"; \
		else \
			echo "⚠️  WEB_PID_FILE istnieje, ale proces $$WPID nie żyje"; \
		fi; \
	else \
		EXT_UI_PIDS=$$(bash scripts/dev/port_pids.sh "$(WEB_PORT)" || true); \
		if [ -n "$$EXT_UI_PIDS" ]; then \
			echo "⚠️  UI zajmuje port $(WEB_PORT), ale bez $(WEB_PID_FILE) (PID: $$EXT_UI_PIDS)"; \
			echo "    Użyj: make web-stop"; \
		else \
			echo "ℹ️  UI (Next.js) nie jest uruchomione"; \
		fi; \
	fi

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

api-preprod:
	$(PREPROD_ENV_READONLY) \
		$(MAKE) --no-print-directory api

# Zatrzymaj tylko backend
api-stop:
	@trap '' TERM INT
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⏹️  Zatrzymuję Venom API (PID $$PID)"; \
			kill $$PID 2>/dev/null || true; \
			for attempt in {1..20}; do \
				if kill -0 $$PID 2>/dev/null; then \
					sleep 0.2; \
				else \
					break; \
				fi; \
			done; \
		else \
			echo "⚠️  Proces ($$PID) już nie działa"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		echo "ℹ️  Venom API nie jest uruchomiony"; \
	fi
	@pkill -f "uvicorn[[:space:]]+$(API_APP)" 2>/dev/null || true
	@echo "✅ Venom API zatrzymany"

# Frontend Web (tylko) - produkcyjny (build + start)
web:
	@mkdir -p logs
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@echo "🛠  Buduję Next.js (npm run build)..."
	cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(NPM) run build >/dev/null 2>&1
	@echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"
	cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(ENV_RUN_ABS) setsid $(NPM) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"

# Frontend Web (tylko) - developerski (next dev)
web-dev:
	@mkdir -p logs
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"
	cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_DEV_ENV) $(ENV_RUN_ABS) setsid $(NPM) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"
	@echo "🔄 Hot Reload: aktywny (zmiana plików → przeładowanie)"

web-dev-turbo:
	$(call start_web_turbo_target,Next.js dev:turbo,dev:turbo,⚡ Turbopack: aktywny (opt-in),NEXT_TELEMETRY_DISABLED=1)

web-dev-turbo-debug:
	$(call start_web_turbo_target,Next.js dev:turbo:debug,dev:turbo:debug,🧪 Debug turbo: NEXT_DEBUG + --trace-warnings,)

web-preprod:
	$(PREPROD_ENV_READONLY) \
		$(MAKE) --no-print-directory web

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


help:
	@echo "Venom Makefile - najczęściej używane komendy"
	@echo ""
	@echo "Start/Stop (dev):"
	@echo "  make start                    - start backend + frontend (webpack-safe dev) + runtime LLM"
	@echo "  make start2                   - start backend + frontend (turbopack) + runtime LLM"
	@echo "  make stop                     - stop backend + frontend + runtime LLM"
	@echo "  make status                   - status procesów"
	@echo "  make web-dev                  - frontend dev (webpack, fallback)"
	@echo "  make web-dev-turbo            - frontend dev (turbopack, opt-in)"
	@echo "  make web-dev-turbo-debug      - frontend dev turbopack + debug logi"
	@echo ""
	@echo "Testy:"
	@echo "  make test                     - backend testy (clean artifacts)"
	@echo "  make test-data                - backend testy (preserve artifacts)"
	@echo "  make test-web-unit            - frontend unit"
	@echo "  make test-web-e2e             - frontend e2e"
	@echo "  make test-web-turbo-smoke     - smoke dev:turbo"
	@echo "  make test-web-turbo-smoke-clean - smoke dev:turbo + clean .next"
	@echo ""
	@echo "Preprod:"
	@echo "  make startpre                 - start stacka preprod (readonly profile)"
	@echo "  make preprod-backup           - backup danych preprod"
	@echo "  make preprod-verify TS=...    - verify + smoke readonly po backupie"
	@echo "  make preprod-readiness-check  - check gotowości preprod"
	@echo ""
	@echo "Runtime LLM:"
	@echo "  make vllm-start|stop|restart  - kontrola usługi vLLM"
	@echo "  make ollama-start|stop|restart - kontrola usługi Ollama"
	@echo ""
	@echo "Jakość:"
	@echo "  make pr-fast                  - hard gate (wymagane przed zakończeniem)"
	@echo "  make make-targets-audit       - audyt .PHONY vs zdefiniowane targety"
	@echo "  make audit-dead-code          - heurystyczny audyt ślepego kodu (Python)"
	@echo "  make test-groups-check        - weryfikacja grup testów"
	@echo "  make test-catalog-check       - weryfikacja katalogu testów"
