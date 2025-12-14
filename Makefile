# Makefile dla Venom

VENV ?= .venv
UVICORN ?= $(VENV)/bin/uvicorn
HOST ?= 0.0.0.0
PORT ?= 8000
PID_FILE ?= .venom.pid
NPM ?= npm
WEB_DIR ?= web-next
WEB_PORT ?= 3000
WEB_PID_FILE ?= .web-next.pid

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

PORTS_TO_CLEAN := $(PORT) $(WEB_PORT)

.PHONY: lint format test precommit install-hooks start stop restart status clean-ports

lint:
	pre-commit run --all-files

format:
	black . && isort .

test:
	pytest -q

install-hooks:
	pre-commit install

start:
	@if [ ! -x "$(UVICORN)" ]; then \
		echo "❌ Nie znaleziono uvicorn w $(UVICORN). Czy środowisko .venv jest zainstalowane?"; \
		exit 1; \
	fi
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⚠️  Venom już działa (PID $$PID). Użyj 'make stop' lub 'make restart'."; \
			exit 1; \
		else \
			rm -f $(PID_FILE); \
		fi; \
	fi
	@echo "▶️  Uruchamiam Venom (uvicorn na $(HOST):$(PORT))"
	@$(UVICORN) venom_core.main:app --host $(HOST) --port $(PORT) --reload >/dev/null 2>&1 & echo $$! > $(PID_FILE)
	@echo "✅ Venom wystartował z PID $$(cat $(PID_FILE))"
	@if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			echo "⚠️  UI (Next.js) już działa (PID $$WPID). Użyj 'make stop' lub 'make restart'."; \
			exit 1; \
		else \
			rm -f $(WEB_PID_FILE); \
		fi; \
	fi
	@echo "▶️  Uruchamiam UI (Next.js na porcie $(WEB_PORT))"
	@$(NPM) --prefix $(WEB_DIR) run dev -- --hostname 0.0.0.0 --port $(WEB_PORT) >/dev/null 2>&1 & echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🚀 Gotowe: backend http://$(HOST):$(PORT), dashboard http://127.0.0.1:$(WEB_PORT)"

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
	@pkill -f "uvicorn[[:space:]]+venom_core.main:app" 2>/dev/null || true
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
