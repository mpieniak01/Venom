# Makefile dla Venom – rozdzielony backend FastAPI + frontend Next.js

VENV ?= .venv
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
START_MODE ?= dev
UVICORN_DEV_FLAGS ?= --reload
UVICORN_PROD_FLAGS ?= --no-server-header
SERVE_LEGACY_DEV ?= True
SERVE_LEGACY_PROD ?= True
BACKEND_LOG ?= logs/backend.log
WEB_LOG ?= logs/web-next.log

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

PORTS_TO_CLEAN := $(PORT) $(WEB_PORT)

.PHONY: lint format test install-hooks start start-dev start-prod stop restart status clean-ports \
	api api-dev api-stop web web-dev web-stop \
	vllm-start vllm-stop vllm-restart ollama-start ollama-stop ollama-restart \
	monitor

lint:
	pre-commit run --all-files

format:
	black . && isort .

test:
	pytest -q

install-hooks:
	pre-commit install

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

start: start-dev

start-dev: START_MODE=dev
start-dev:
	$(MAKE) --no-print-directory _start

start-prod: START_MODE=prod
start-prod:
	$(MAKE) --no-print-directory _start

_start:
	@if [ ! -x "$(UVICORN)" ]; then \
		echo "❌ Nie znaleziono uvicorn w $(UVICORN). Czy środowisko .venv jest zainstalowane?"; \
		exit 1; \
	fi
	@mkdir -p logs
	$(call ensure_process_not_running,Venom backend,$(PID_FILE))
	@if [ "$(START_MODE)" = "prod" ]; then \
		UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_PROD_FLAGS)"; \
		export SERVE_LEGACY_UI=$(SERVE_LEGACY_PROD); \
	else \
		UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_DEV_FLAGS)"; \
		export SERVE_LEGACY_UI=$(SERVE_LEGACY_DEV); \
	fi; \
	echo "▶️  Uruchamiam Venom backend (uvicorn na $(HOST):$(PORT))"; \
	: > $(BACKEND_LOG); \
	setsid $(UVICORN) $(API_APP) $$UVICORN_FLAGS >> $(BACKEND_LOG) 2>&1 & \
	echo $$! > $(PID_FILE); \
	echo "✅ Venom backend wystartował z PID $$(cat $(PID_FILE))"
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@if [ "$(START_MODE)" = "prod" ]; then \
		echo "🛠  Buduję Next.js (npm run build)"; \
		$(NEXT_PROD_ENV) $(NPM) --prefix $(WEB_DIR) run build >/dev/null 2>&1; \
		echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"; \
		$(NEXT_PROD_ENV) setsid $(NPM) --prefix $(WEB_DIR) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
		echo $$! > $(WEB_PID_FILE); \
	else \
		echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"; \
		$(NEXT_DEV_ENV) setsid $(NPM) --prefix $(WEB_DIR) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
		echo $$! > $(WEB_PID_FILE); \
	fi
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🚀 Gotowe: backend http://$(HOST_DISPLAY):$(PORT), dashboard http://$(WEB_DISPLAY):$(WEB_PORT)"

stop:
	@trap '' TERM INT
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⏹️  Zatrzymuję Venom (PID $$PID)"; \
			kill $$PID 2>/dev/null || true; \
			for attempt in {1..20}; do \
				if kill -0 $$PID 2>/dev/null; then \
					sleep 0.2; \
				else \
					break; \
				fi; \
			done; \
		else \
			echo "⚠️  Proces ($$PID) już nie działa - czyszczę PID_FILE"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		echo "ℹ️  Brak aktywnego procesu (PID_FILE nie istnieje)"; \
	fi
	@pkill -f "uvicorn[[:space:]]+$(API_APP)" 2>/dev/null || true
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
			echo "⚠️  Proces UI ($$WPID) już nie działa - czyszczę WEB_PID_FILE"; \
		fi; \
		rm -f $(WEB_PID_FILE); \
	else \
		echo "ℹ️  UI nie był uruchomiony (WEB_PID_FILE nie istnieje)"; \
	fi
	@pkill -f "next dev" 2>/dev/null || true
	@pkill -f "next start" 2>/dev/null || true
	@$(MAKE) --no-print-directory clean-ports >/dev/null || true
	@echo "✅ Procesy Venom/Next zostały zatrzymane"

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
		echo "ℹ️  UI (Next.js) nie jest uruchomione"; \
	fi

clean-ports:
	@if ! command -v lsof >/dev/null 2>&1; then \
		echo "ℹ️  lsof nie jest dostępny – pomijam czyszczenie portów"; \
	else \
		for PORT_TO_CHECK in $(PORTS_TO_CLEAN); do \
			PIDS=$$(lsof -ti tcp:$$PORT_TO_CHECK 2>/dev/null || true); \
			if [ -n "$$PIDS" ]; then \
				echo "⚠️  Port $$PORT_TO_CHECK zajęty przez $$PIDS – kończę procesy"; \
				kill $$PIDS 2>/dev/null || true; \
			fi; \
		done; \
	fi

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
	export SERVE_LEGACY_UI=$(SERVE_LEGACY_PROD); \
	setsid $(UVICORN) $(API_APP) --host $(HOST) --port $(PORT) $(UVICORN_PROD_FLAGS) >> $(BACKEND_LOG) 2>&1 & \
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
	export SERVE_LEGACY_UI=$(SERVE_LEGACY_DEV); \
	setsid $(UVICORN) $(API_APP) --host $(HOST) --port $(PORT) $(UVICORN_DEV_FLAGS) >> $(BACKEND_LOG) 2>&1 & \
	echo $$! > $(PID_FILE)
	@echo "✅ Venom API wystartował z PID $$(cat $(PID_FILE))"
	@echo "📡 Backend: http://$(HOST):$(PORT)"
	@echo "🔄 Autoreload: aktywny (zmiana plików → restart)"

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
	$(NEXT_PROD_ENV) $(NPM) --prefix $(WEB_DIR) run build >/dev/null 2>&1
	@echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"
	$(NEXT_PROD_ENV) setsid $(NPM) --prefix $(WEB_DIR) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"

# Frontend Web (tylko) - developerski (next dev)
web-dev:
	@mkdir -p logs
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"
	$(NEXT_DEV_ENV) setsid $(NPM) --prefix $(WEB_DIR) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"
	@echo "🔄 Hot Reload: aktywny (zmiana plików → przeładowanie)"

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
# Kontrola LLM Runtime (vLLM, Ollama)
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
