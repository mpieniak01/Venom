# Makefile dla Venom

VENV ?= .venv
UVICORN ?= $(VENV)/bin/uvicorn
QA_SCRIPT ?= scripts/qa/run_ui_suite.sh
HOST ?= 0.0.0.0
PORT ?= 8000
PID_FILE ?= .venom.pid

.PHONY: lint format test precommit install-hooks start stop restart status qa

lint:
	pre-commit run --all-files

format:
	black . && isort .

test:
	pytest -q

qa:
	bash $(QA_SCRIPT)

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
