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

.PHONY: lint format test precommit install-hooks start stop restart status

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
			echo "⚠️  Venom już działa (PID $$PID). Użyj 'make stop' aby go zatrzymać."; \
			exit 1; \
		else \
			rm -f $(PID_FILE); \
		fi \
	fi
	@echo "▶️  Uruchamiam Venom (uvicorn na $(HOST):$(PORT))"
	@$(UVICORN) venom_core.main:app --host $(HOST) --port $(PORT) --reload >/dev/null 2>&1 & echo $$! > $(PID_FILE)
	@echo "✅ Venom wystartował z PID $$(cat $(PID_FILE))"
	@if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			echo "⚠️  UI (Next.js) już działa (PID $$WPID). Użyj 'make stop' aby go zatrzymać."; \
			exit 1; \
		else \
			rm -f $(WEB_PID_FILE); \
		fi \
	fi
	@echo "▶️  Uruchamiam UI (Next.js na porcie $(WEB_PORT))"
	@$(NPM) --prefix $(WEB_DIR) run dev -- --hostname 0.0.0.0 --port $(WEB_PORT) >/dev/null 2>&1 & echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI wystartował z PID $$(cat $(WEB_PID_FILE))"

stop:
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		if kill -0 $$PID 2>/dev/null; then \
			echo "⏹️  Zatrzymuję Venom (PID $$PID)"; \
			pkill -P $$PID 2>/dev/null || true; \
			kill $$PID 2>/dev/null || true; \
		else \
			echo "⚠️  Proces ($$PID) już nie działa - czyszczę PID_FILE"; \
		fi; \
		rm -f $(PID_FILE); \
	else \
		echo "ℹ️  Brak aktywnego procesu (PID_FILE nie istnieje)"; \
	fi
	@pkill -f "uvicorn venom_core.main:app" 2>/dev/null || true
	@if [ -f $(WEB_PID_FILE) ]; then \
		WPID=$$(cat $(WEB_PID_FILE)); \
		if kill -0 $$WPID 2>/dev/null; then \
			echo "⏹️  Zatrzymuję UI (PID $$WPID)"; \
			pkill -P $$WPID 2>/dev/null || true; \
			kill $$WPID 2>/dev/null || true; \
		else \
			echo "⚠️  Proces UI ($$WPID) już nie działa - czyszczę WEB_PID_FILE"; \
		fi; \
		rm -f $(WEB_PID_FILE); \
	else \
		echo "ℹ️  UI nie był uruchomiony (WEB_PID_FILE nie istnieje)"; \
	fi
	@pkill -f "next dev" 2>/dev/null || true

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
