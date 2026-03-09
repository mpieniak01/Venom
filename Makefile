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
VLLM_ENDPOINT ?= http://127.0.0.1:8001
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

.PHONY: lint format test test-data test-artifacts-cleanup install-hooks sync-sonar-new-code-group start start2 start-dev start-dev-turbo start-prod start-preprod stop restart status clean-ports \
		pytest e2e test-optimal test-ci-light test-fast-coverage test-light-coverage check-new-code-coverage check-new-code-coverage-diagnostics check-new-code-coverage-local sonar-reports-backend-new-code pr-fast agent-pr-fast pr-fast-local \
		ci-lite-preflight ci-lite-bootstrap \
		test-intelligence-report \
		runtime-maintenance-cleanup \
		runtime-log-policy-audit runtime-logrotate-install-help \
		api api-dev api-preprod api-stop web web-dev web-dev-turbo web-dev-turbo-debug web-preprod web-stop \
		test-web-turbo-smoke test-web-turbo-smoke-clean \
		startpre stoppre restartpre statuspre apipre webpre testpre ensurepreenv \
		preprod-backup preprod-restore preprod-verify preprod-audit preprod-drill preprod-readiness-check prebackup prerestore preverify preaudit predrill prereadiness \
		vllm-start vllm-stop vllm-restart ollama-start ollama-stop ollama-restart \
		monitor mcp-clean mcp-status sonar-reports sonar-reports-backend sonar-reports-frontend openapi-export openapi-codegen-types ensure-env-file \
		ensure-preprod-env-file \
		env-audit env-clean-safe env-clean-docker-safe env-clean-deep env-report-diff test-preprod-readonly-smoke help \
		modules-status modules-pull modules-branches modules-exec architecture-drift-check architecture-sonar-export optional-modules-contracts-check test-lane-contracts-check test-catalog-sync test-catalog-check test-groups-sync test-groups-check test-dynamic-preview check-file-coverage-floor

lint:
	pre-commit run --all-files

format:
	black . && isort .

-include make/tests.mk
-include make/maintenance.mk
-include make/preprod.mk
-include make/runtime.mk


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

_start:
	@if [ ! -x "$(UVICORN)" ]; then \
		echo "❌ Nie znaleziono uvicorn w $(UVICORN). Czy środowisko .venv jest zainstalowane?"; \
		exit 1; \
	fi
	@mkdir -p logs
	@active_server=""; \
	if [ -f "$(ENV_FILE)" ]; then \
		active_server=$$(awk -F= '/^ACTIVE_LLM_SERVER=/{print $$2}' "$(ENV_FILE)" 2>/dev/null | tr -d '\r' | tr '[:upper:]' '[:lower:]' || true); \
	elif [ -f "$(ENV_EXAMPLE_FILE)" ]; then \
		active_server=$$(awk -F= '/^ACTIVE_LLM_SERVER=/{print $$2}' "$(ENV_EXAMPLE_FILE)" 2>/dev/null | tr -d '\r' | tr '[:upper:]' '[:lower:]' || true); \
	fi; \
	if [ -z "$$active_server" ]; then active_server="ollama"; fi; \
	start_ollama() { \
		echo "▶️  Uruchamiam Ollama..."; \
		$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
		if command -v timeout >/dev/null 2>&1; then \
			if ! timeout 25s $(MAKE) --no-print-directory ollama-start >/dev/null; then \
				echo "❌ 'ollama-start' nie zakończył się poprawnie w limicie czasu (25s)."; \
				return 1; \
			fi; \
		else \
			if ! $(MAKE) --no-print-directory ollama-start >/dev/null; then \
				echo "❌ Nie udało się wywołać 'ollama-start' (sprawdź instalację/usługę Ollama)."; \
				return 1; \
			fi; \
		fi; \
		echo "⏳ Czekam na Ollama (/api/tags)..."; \
		ollama_fatal=""; \
		for attempt in {1..90}; do \
			if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then \
				echo "✅ Ollama gotowy"; \
				return 0; \
			fi; \
			if [ -f "logs/ollama.log" ] && grep -Eiq "Error: listen tcp .*:11434|operation not permitted|address already in use" "logs/ollama.log"; then \
				echo "❌ Ollama zakończyła start błędem (sprawdź logs/ollama.log)"; \
				ollama_fatal="yes"; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ -z "$$ollama_fatal" ]; then echo "❌ Ollama nie wystartowała w czasie (brak odpowiedzi z /api/tags)"; fi; \
		if [ -f "logs/ollama.log" ]; then \
			echo "ℹ️  Ostatnie logi Ollama:"; \
			tail -n 40 "logs/ollama.log" || true; \
		fi; \
		$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
		return 1; \
	}; \
	start_vllm() { \
		echo "▶️  Uruchamiam vLLM..."; \
		$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
		if ! $(MAKE) --no-print-directory vllm-start; then \
			echo "❌ Nie udało się uruchomić vLLM (sprawdź logi wyżej)."; \
			return 1; \
		fi; \
		echo "⏳ Czekam na vLLM (/v1/models)..."; \
		for attempt in $$(seq 1 $(VLLM_START_TIMEOUT_SEC)); do \
			if curl -fsS "$(VLLM_ENDPOINT)/v1/models" >/dev/null 2>&1; then \
				echo "✅ vLLM gotowy"; \
				return 0; \
			fi; \
			if [ -f "logs/vllm.pid" ]; then \
				VPID=$$(cat "logs/vllm.pid"); \
				if ! kill -0 $$VPID 2>/dev/null; then \
					echo "❌ vLLM proces $$VPID zakończył się przed gotowością endpointu."; \
					if [ -f "logs/vllm.log" ]; then \
						echo "ℹ️  Ostatnie logi vLLM:"; \
						tail -n 40 "logs/vllm.log" || true; \
					fi; \
					return 1; \
				fi; \
			fi; \
			sleep 1; \
		done; \
		echo "❌ vLLM nie wystartował w czasie ($(VLLM_START_TIMEOUT_SEC)s, brak odpowiedzi z /v1/models)"; \
		if [ -f "logs/vllm.log" ]; then \
			echo "ℹ️  Ostatnie logi vLLM:"; \
			tail -n 40 "logs/vllm.log" || true; \
		fi; \
		$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
		return 1; \
	}; \
	llm_ready=""; \
	if [ "$$active_server" = "onnx" ]; then \
		echo "▶️  Aktywny runtime: ONNX (in-process)"; \
		$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
		$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
		llm_ready="onnx"; \
	elif [ "$$active_server" = "ollama" ]; then \
		$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
		if start_ollama; then llm_ready="ollama"; fi; \
	elif [ "$$active_server" = "vllm" ]; then \
		$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
		if start_vllm; then llm_ready="vllm"; fi; \
	elif [ "$$active_server" = "none" ]; then \
		echo "▶️  ACTIVE_LLM_SERVER=none (start bez lokalnego serwera LLM)"; \
		$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
		$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
		llm_ready="none"; \
	else \
		echo "❌ Nieznany ACTIVE_LLM_SERVER='$$active_server' (dozwolone: ollama|vllm|onnx|none)"; \
		exit 1; \
	fi; \
	if [ -z "$$llm_ready" ]; then \
		if [ "$$active_server" = "ollama" ] && [ "$(START_MODE)" = "dev" ]; then \
			echo "⚠️  Ollama niedostępna. Kontynuuję start-dev bez lokalnego LLM (ACTIVE_LLM_SERVER=none)."; \
			echo "ℹ️  Tryb restrykcyjny bez fallbacku: użyj 'make start-prod ACTIVE_LLM_SERVER=ollama'."; \
			llm_ready="none"; \
		elif [ "$(ALLOW_DEGRADED_START)" = "1" ]; then \
			echo "⚠️  Tryb degradowany: kontynuuję start bez aktywnego LLM (ALLOW_DEGRADED_START=1)"; \
			llm_ready="none"; \
		else \
			echo "❌ Nie udało się uruchomić aktywnego LLM: $$active_server"; \
			exit 1; \
		fi; \
	fi; \
	echo "🧠 LLM gotowy: $$llm_ready"
	@backend_reused=""; \
	if curl -fsS http://$(HOST_DISPLAY):$(PORT)/api/v1/system/status >/dev/null 2>&1; then \
		echo "⚠️  Backend już odpowiada na $(HOST_DISPLAY):$(PORT). Pomijam drugi start backendu."; \
		backend_reused="yes"; \
		if [ -f "$(PID_FILE)" ]; then \
			PID=$$(cat "$(PID_FILE)"); \
			if ! kill -0 $$PID 2>/dev/null; then rm -f "$(PID_FILE)"; fi; \
		fi; \
	elif [ -f "$(PID_FILE)" ]; then \
		PID=$$(cat "$(PID_FILE)"); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⚠️  Backend PID $$PID istnieje, ale /system/status jest niedostępny. Restartuję backend."; \
			kill $$PID 2>/dev/null || true; \
			for attempt in {1..30}; do \
				if kill -0 $$PID 2>/dev/null; then sleep 0.2; else break; fi; \
			done; \
			rm -f "$(PID_FILE)"; \
		else \
			rm -f "$(PID_FILE)"; \
		fi; \
	fi; \
		if [ -z "$$backend_reused" ]; then \
		if [ -f "$(PID_FILE)" ]; then \
			PID=$$(cat "$(PID_FILE)"); \
			if kill -0 $$PID 2>/dev/null; then \
				echo "⚠️  Venom backend już działa (PID $$PID). Użyj 'make stop' lub 'make restart'."; \
				exit 1; \
			else \
				rm -f "$(PID_FILE)"; \
			fi; \
		fi; \
			if [ "$(START_MODE)" = "prod" ]; then \
				UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_PROD_FLAGS)"; \
			else \
				if [ "$(BACKEND_RELOAD)" = "1" ]; then \
					UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_DEV_FLAGS)"; \
					echo "ℹ️  Backend dev z autoreload (BACKEND_RELOAD=1)"; \
				else \
					UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_PROD_FLAGS)"; \
					echo "ℹ️  Backend dev w trybie stabilnym bez autoreload (BACKEND_RELOAD=0)"; \
				fi; \
			fi; \
		echo "▶️  Uruchamiam Venom backend (uvicorn na $(HOST):$(PORT))"; \
		: > $(BACKEND_LOG); \
		$(ENV_RUN) setsid $(UVICORN) $(API_APP) $$UVICORN_FLAGS >> $(BACKEND_LOG) 2>&1 & \
		echo $$! > $(PID_FILE); \
		echo "✅ Venom backend wystartował z PID $$(cat $(PID_FILE))"; \
		echo "⏳ Czekam na backend (/api/v1/system/status)..."; \
		backend_ready=""; \
		for attempt in {1..60}; do \
			if curl -fsS http://$(HOST_DISPLAY):$(PORT)/api/v1/system/status >/dev/null 2>&1; then \
				backend_ready="yes"; \
				echo "✅ Backend gotowy"; \
				break; \
			fi; \
			if [ -f "$(PID_FILE)" ]; then \
				PID=$$(cat $(PID_FILE)); \
				if ! kill -0 $$PID 2>/dev/null; then \
					echo "⚠️  Proces startowy backendu $$PID nie działa"; \
					break; \
				fi; \
			fi; \
			sleep 1; \
		done; \
		if [ -z "$$backend_ready" ]; then \
			echo "❌ Backend nie wystartował w czasie (brak 200 z /api/v1/system/status)"; \
			if [ -f "$(BACKEND_LOG)" ]; then \
				echo "ℹ️  Ostatnie logi backendu:"; \
				tail -n 40 "$(BACKEND_LOG)" || true; \
			fi; \
			if [ -f "$(PID_FILE)" ]; then \
				BPID=$$(cat "$(PID_FILE)"); \
				kill $$BPID 2>/dev/null || true; \
				rm -f "$(PID_FILE)"; \
			fi; \
			$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
			$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
			exit 1; \
		fi; \
	else \
		echo "✅ Backend gotowy (używam już działającej instancji)"; \
	fi
	@ui_skip=""; \
	if [ ! -f $(WEB_PID_FILE) ]; then \
		EXT_UI_PIDS=""; \
		if command -v lsof >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(lsof -ti tcp:$(WEB_PORT) 2>/dev/null || true); \
		fi; \
		if [ -z "$$EXT_UI_PIDS" ] && command -v fuser >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(fuser -n tcp $(WEB_PORT) 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$$' || true); \
		fi; \
		if [ -z "$$EXT_UI_PIDS" ] && command -v ss >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(ss -ltnp 2>/dev/null | awk '/:$(WEB_PORT)[[:space:]]/ { while (match($$0, /pid=[0-9]+/)) { print substr($$0, RSTART+4, RLENGTH-4); $$0 = substr($$0, RSTART+RLENGTH); } }' | sort -u || true); \
		fi; \
		if [ -n "$$EXT_UI_PIDS" ]; then \
			echo "⚠️  Port $(WEB_PORT) zajęty przez niezarządzany proces UI ($$EXT_UI_PIDS). Czyszczę."; \
			kill $$EXT_UI_PIDS 2>/dev/null || true; \
			for attempt in {1..30}; do \
				EXT_STILL=""; \
				if command -v lsof >/dev/null 2>&1; then \
					EXT_STILL=$$(lsof -ti tcp:$(WEB_PORT) 2>/dev/null || true); \
				fi; \
				if [ -z "$$EXT_STILL" ] && command -v fuser >/dev/null 2>&1; then \
					EXT_STILL=$$(fuser -n tcp $(WEB_PORT) 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$$' || true); \
				fi; \
				if [ -z "$$EXT_STILL" ] && command -v ss >/dev/null 2>&1; then \
					EXT_STILL=$$(ss -ltnp 2>/dev/null | awk '/:$(WEB_PORT)[[:space:]]/ { while (match($$0, /pid=[0-9]+/)) { print substr($$0, RSTART+4, RLENGTH-4); $$0 = substr($$0, RSTART+RLENGTH); } }' | sort -u || true); \
				fi; \
				if [ -z "$$EXT_STILL" ]; then break; fi; \
				sleep 0.2; \
			done; \
			EXT_STILL=""; \
			if command -v lsof >/dev/null 2>&1; then \
				EXT_STILL=$$(lsof -ti tcp:$(WEB_PORT) 2>/dev/null || true); \
			fi; \
			if [ -z "$$EXT_STILL" ] && command -v fuser >/dev/null 2>&1; then \
				EXT_STILL=$$(fuser -n tcp $(WEB_PORT) 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$$' || true); \
			fi; \
			if [ -z "$$EXT_STILL" ] && command -v ss >/dev/null 2>&1; then \
				EXT_STILL=$$(ss -ltnp 2>/dev/null | awk '/:$(WEB_PORT)[[:space:]]/ { while (match($$0, /pid=[0-9]+/)) { print substr($$0, RSTART+4, RLENGTH-4); $$0 = substr($$0, RSTART+RLENGTH); } }' | sort -u || true); \
			fi; \
			if [ -n "$$EXT_STILL" ]; then \
				echo "❌ Nie udało się zwolnić portu $(WEB_PORT) (PID: $$EXT_STILL). Użyj: make web-stop"; \
				exit 1; \
			fi; \
		fi; \
	fi; \
	if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			if [ "$(START_MODE)" = "dev" ]; then \
				cmdline=$$(tr '\0' ' ' < /proc/$$WPID/cmdline 2>/dev/null || true); \
				want=""; \
				if [ "$(START_WEB_MODE)" = "turbo" ]; then \
					want="dev:turbo"; \
				elif [ "$(START_WEB_MODE)" = "turbo-debug" ]; then \
					want="dev:turbo:debug"; \
				else \
					want="dev --"; \
				fi; \
					if printf '%s' "$$cmdline" | grep -Fq "$$want"; then \
						echo "⚠️  UI (Next.js) już działa w trybie $(START_WEB_MODE) (PID $$WPID). Pomijam start UI."; \
						ui_skip="yes"; \
					else \
						echo "🔁 UI (Next.js) działa w innym trybie. Restartuję do trybu $(START_WEB_MODE)."; \
						kill -TERM -$$WPID 2>/dev/null || kill $$WPID 2>/dev/null || true; \
						for attempt in {1..20}; do \
							if kill -0 $$WPID 2>/dev/null; then sleep 0.2; else break; fi; \
						done; \
						if kill -0 $$WPID 2>/dev/null; then \
							kill -KILL -$$WPID 2>/dev/null || kill -KILL $$WPID 2>/dev/null || true; \
						fi; \
						rm -f $(WEB_PID_FILE); \
					fi; \
				else \
				echo "⚠️  UI (Next.js) już działa (PID $$WPID). Pomijam start UI."; \
				ui_skip="yes"; \
			fi; \
		else \
			rm -f $(WEB_PID_FILE); \
		fi; \
	fi; \
	if [ -z "$$ui_skip" ]; then \
		wait_for_ui_ready() { \
			local pid="$$1"; \
			local failure_label="$$2"; \
			local ready=""; \
			for attempt in {1..40}; do \
				if kill -0 "$$pid" 2>/dev/null; then \
					if curl -fsS http://$(WEB_DISPLAY):$(WEB_PORT) >/dev/null 2>&1; then \
						ready="yes"; \
						break; \
					fi; \
				else \
					echo "$$failure_label proces $$pid zakończył się przed startem" >&2; \
					break; \
				fi; \
				sleep 1; \
			done; \
			printf '%s' "$$ready"; \
		}; \
		: > $(WEB_LOG); \
		if [ "$(START_MODE)" = "prod" ]; then \
			echo "🛠  Buduję Next.js (npm run build)"; \
			cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(NPM) run build >/dev/null 2>&1; \
			echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"; \
			cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(ENV_RUN_ABS) setsid $(NPM) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
			echo $$! > $(WEB_PID_FILE); \
		else \
			if [ "$(START_WEB_MODE)" != "webpack" ] && [ "$(START_WEB_MODE)" != "turbo" ] && [ "$(START_WEB_MODE)" != "turbo-debug" ]; then \
				echo "❌ Nieznany START_WEB_MODE='$(START_WEB_MODE)' (dozwolone: webpack|turbo|turbo-debug)"; \
				exit 1; \
			fi; \
			if [ "$(START_WEB_MODE)" = "turbo" ]; then \
				echo "▶️  Uruchamiam UI (Next.js dev:turbo, host $(WEB_HOST), port $(WEB_PORT))"; \
				cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev NEXT_TELEMETRY_DISABLED=1 $(NEXT_TURBO_WATCH_ENV) $(ENV_RUN_ABS) setsid $(NPM) run dev:turbo -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			elif [ "$(START_WEB_MODE)" = "turbo-debug" ]; then \
				echo "▶️  Uruchamiam UI (Next.js dev:turbo:debug, host $(WEB_HOST), port $(WEB_PORT))"; \
				cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev $(NEXT_TURBO_WATCH_ENV) $(ENV_RUN_ABS) setsid $(NPM) run dev:turbo:debug -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			else \
				echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"; \
				cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_DEV_ENV) $(ENV_RUN_ABS) setsid $(NPM) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			fi; \
		fi; \
		WPID=$$(cat $(WEB_PID_FILE)); \
		ui_ready=$$(wait_for_ui_ready "$$WPID" "❌ UI (Next.js)"); \
		effective_web_mode="$(START_WEB_MODE)"; \
		if [ -z "$$ui_ready" ]; then \
			echo "❌ UI (Next.js) nie wystartował poprawnie na porcie $(WEB_PORT)"; \
			kill -TERM -$$WPID 2>/dev/null || kill $$WPID 2>/dev/null || true; \
			rm -f $(WEB_PID_FILE); \
			if [ "$(START_MODE)" = "dev" ] && { [ "$(START_WEB_MODE)" = "turbo" ] || [ "$(START_WEB_MODE)" = "turbo-debug" ]; } && [ -f "$(WEB_LOG)" ] && grep -Eiq "Too many open files|Failed to allocate directory watch" "$(WEB_LOG)"; then \
				echo "⚠️  Turbopack nie wystartował przez błąd watchera. Przełączam UI na fallback webpack."; \
				: > $(WEB_LOG); \
				cd $(WEB_DIR) && NODE_PATH="$(WEB_NODE_PATH)" NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_DEV_ENV) $(ENV_RUN_ABS) setsid $(NPM) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> ../$(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
				WPID=$$(cat $(WEB_PID_FILE)); \
				effective_web_mode="webpack"; \
				ui_ready=$$(wait_for_ui_ready "$$WPID" "❌ UI fallback (webpack)"); \
			fi; \
			if [ -z "$$ui_ready" ]; then \
				# zatrzymaj backend, aby nie zostawiać pół-startu
				if [ -f $(PID_FILE) ]; then \
					BPID=$$(cat $(PID_FILE)); \
					kill $$BPID 2>/dev/null || true; \
					rm -f $(PID_FILE); \
				fi; \
				$(MAKE) --no-print-directory vllm-stop >/dev/null || true; \
				$(MAKE) --no-print-directory ollama-stop >/dev/null || true; \
				exit 1; \
			fi; \
		fi; \
			if [ "$(START_MODE)" = "dev" ]; then \
				expected_bundler=""; \
				if [ "$$effective_web_mode" = "webpack" ]; then \
					expected_bundler="webpack"; \
				else \
					expected_bundler="turbopack"; \
				fi; \
				bundler_line_ok=""; \
				for attempt in {1..15}; do \
					if [ -f "$(WEB_LOG)" ] && grep -Eiq "Next\\.js .+\\($$expected_bundler\\)" "$(WEB_LOG)"; then \
						bundler_line_ok="yes"; \
						break; \
					fi; \
					sleep 1; \
				done; \
				if [ -z "$$bundler_line_ok" ]; then \
					echo "❌ UI nie potwierdził oczekiwanego bundlera '$$expected_bundler' w logach."; \
					echo "ℹ️  Ostatnie logi UI:"; \
					tail -n 60 "$(WEB_LOG)" || true; \
					kill $$WPID 2>/dev/null || true; \
					rm -f $(WEB_PID_FILE); \
					exit 1; \
				fi; \
			fi; \
			echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"; \
		fi
	@echo "🚀 Gotowe: backend http://$(HOST_DISPLAY):$(PORT), dashboard http://$(WEB_DISPLAY):$(WEB_PORT)"

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
		EXT_UI_PIDS=""; \
		if command -v lsof >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(lsof -ti tcp:$(WEB_PORT) 2>/dev/null || true); \
		fi; \
		if [ -z "$$EXT_UI_PIDS" ] && command -v fuser >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(fuser -n tcp $(WEB_PORT) 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$$' || true); \
		fi; \
		if [ -z "$$EXT_UI_PIDS" ] && command -v ss >/dev/null 2>&1; then \
			EXT_UI_PIDS=$$(ss -ltnp 2>/dev/null | awk '/:$(WEB_PORT)[[:space:]]/ { while (match($$0, /pid=[0-9]+/)) { print substr($$0, RSTART+4, RLENGTH-4); $$0 = substr($$0, RSTART+RLENGTH); } }' | sort -u || true); \
		fi; \
		if [ -n "$$EXT_UI_PIDS" ]; then \
			echo "⚠️  UI zajmuje port $(WEB_PORT), ale bez $(WEB_PID_FILE) (PID: $$EXT_UI_PIDS)"; \
			echo "    Użyj: make web-stop"; \
		else \
			echo "ℹ️  UI (Next.js) nie jest uruchomione"; \
		fi; \
	fi

clean-ports:
	@for PORT_TO_CHECK in $(PORTS_TO_CLEAN); do \
		if command -v lsof >/dev/null 2>&1; then \
			PIDS=$$(lsof -ti tcp:$$PORT_TO_CHECK 2>/dev/null || true); \
			if [ -n "$$PIDS" ]; then \
				echo "⚠️  Port $$PORT_TO_CHECK zajęty przez $$PIDS – kończę procesy"; \
				kill $$PIDS 2>/dev/null || true; \
			fi; \
		elif command -v fuser >/dev/null 2>&1; then \
			PIDS=$$(fuser -n tcp $$PORT_TO_CHECK 2>/dev/null || true); \
			if [ -n "$$PIDS" ]; then \
				echo "⚠️  Port $$PORT_TO_CHECK zajęty przez $$PIDS – kończę procesy (fuser)"; \
				fuser -k -n tcp $$PORT_TO_CHECK >/dev/null 2>&1 || true; \
			fi; \
		else \
			echo "ℹ️  Brak lsof/fuser – pomijam czyszczenie portu $$PORT_TO_CHECK"; \
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


# =============================================================================
# Monitoring zasobów
# =============================================================================

monitor:
	@if [ -f scripts/diagnostics/system_snapshot.sh ]; then \
		bash scripts/diagnostics/system_snapshot.sh; \
	else \
		echo "❌ Skrypt scripts/diagnostics/system_snapshot.sh nie istnieje"; \
		exit 1; \
	fi


help:
	@echo "Venom Makefile - najczęściej używane komendy"
	@echo ""
	@echo "Start/Stop:"
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
	@echo "Jakość:"
	@echo "  make pr-fast                  - hard gate (wymagane przed zakończeniem)"
	@echo "  make audit-dead-code          - heurystyczny audyt ślepego kodu (Python)"
	@echo "  make test-groups-check        - weryfikacja grup testów"
	@echo "  make test-catalog-check       - weryfikacja katalogu testów"
