# Makefile dla Venom – rozdzielony backend FastAPI + frontend Next.js

VENV ?= .venv
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
START_WEB_MODE ?= turbo
ALLOW_DEGRADED_START ?= 0
UVICORN_DEV_FLAGS ?= --reload
UVICORN_PROD_FLAGS ?= --no-server-header
BACKEND_LOG ?= logs/backend.log
WEB_LOG ?= logs/web-next.log
VLLM_ENDPOINT ?= http://127.0.0.1:8001
VLLM_START_TIMEOUT_SEC ?= 240
ENV_FILE ?= .env.dev
ENV_EXAMPLE_FILE ?= .env.dev.example
ENV_RUN ?= $(PYTHON_BIN) -m dotenv -f "$(ENV_FILE)" run --
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

# Test Artifact Strategy (docs/TEST_ARTIFACTS_POLICY.md)
# Domyślnie: CLEAN (artefakty testowe są usuwane)
# Opcjonalnie: PRESERVE (artefakty zachowane do debugowania)
TEST_ARTIFACT_MODE ?= clean
TEST_ARTIFACT_CLEANUP_DAYS ?= 7

test:
	@echo "🧪 Uruchamiam testy w trybie CLEAN (artefakty usuwane po sesji)..."
	@set +e; \
	VENOM_TEST_ARTIFACT_MODE=clean VENOM_API_BASE="$${VENOM_API_BASE:-http://$(HOST_DISPLAY):$(PORT)}" bash scripts/run-pytest-optimal.sh; \
	rc=$$?; \
	$(call handle_pytest_no_tests,test) \
	if [ $$rc -ne 0 ]; then \
		echo ""; \
		echo "❌ make test: testy nie przeszły (exit=$$rc)."; \
		echo "   Sprawdź sekcję 'short test summary info' powyżej."; \
		exit $$rc; \
	fi

test-data:
	@echo "🧪 Uruchamiam testy w trybie PRESERVE (artefakty zachowane)..."
	@set +e; \
	VENOM_TEST_ARTIFACT_MODE=preserve VENOM_API_BASE="$${VENOM_API_BASE:-http://$(HOST_DISPLAY):$(PORT)}" bash scripts/run-pytest-optimal.sh; \
	rc=$$?; \
	$(call handle_pytest_no_tests,test-data) \
	if [ $$rc -ne 0 ]; then \
		echo ""; \
		echo "❌ make test-data: testy nie przeszły (exit=$$rc)."; \
		echo "   Sprawdź sekcję 'short test summary info' powyżej."; \
		exit $$rc; \
	fi

test-artifacts-cleanup:
	@echo "🗑️  Czyszczenie starych artefaktów testowych..."
	@if [ "$(CLEANUP_ALL)" = "1" ]; then \
		echo "Usuwanie wszystkich artefaktów z test-results/tmp/..."; \
		rm -rf test-results/tmp/*; \
		echo "✅ Usunięto wszystkie artefakty testowe"; \
	else \
		echo "Usuwanie artefaktów starszych niż $(TEST_ARTIFACT_CLEANUP_DAYS) dni..."; \
		find test-results/tmp -type d -name "session-*" -mtime +$(TEST_ARTIFACT_CLEANUP_DAYS) -exec rm -rf {} + 2>/dev/null || true; \
		echo "✅ Usunięto stare artefakty testowe"; \
	fi

test-unit:
	pytest -k "not performance and not smoke"

test-smoke:
	pytest -m smoke

test-preprod-readonly-smoke:
	$(PREPROD_ENV_READONLY) \
		$(PYTEST_BIN) -q tests/test_preprod_readonly_smoke.py tests/test_preprod_optional_modules_smoke.py -m smoke

test-perf:
	pytest -m performance

test-web-unit:
	$(NPM) --prefix $(WEB_DIR) run test:unit

test-web-e2e:
	$(NPM) --prefix $(WEB_DIR) run test:e2e

test-web-turbo-smoke:
	$(NPM) --prefix $(WEB_DIR) run test:dev:turbo:smoke

test-web-turbo-smoke-clean:
	$(NPM) --prefix $(WEB_DIR) run test:dev:turbo:smoke:clean

test-all:
	@overall_start=$$(date +%s); \
	overall_rc=0; \
	\
	run_phase() { \
		local phase_name="$$1"; \
		local phase_target="$$2"; \
		local start_ts end_ts duration duration_min rc status; \
		echo ""; \
		echo "▶️  Faza: $$phase_name"; \
		start_ts=$$(date +%s); \
		set +e; \
		$(MAKE) --no-print-directory "$$phase_target"; \
		rc=$$?; \
		set -e; \
		end_ts=$$(date +%s); \
		duration=$$((end_ts - start_ts)); \
		duration_min=$$(awk "BEGIN {printf \"%.2f\", $$duration/60}"); \
		if [ $$rc -eq 0 ]; then \
			status="OK"; \
		else \
			status="FAIL($$rc)"; \
			overall_rc=1; \
		fi; \
		phase_durations+=("$$duration"); \
		phase_durations_min+=("$$duration_min"); \
		phase_statuses+=("$$status"); \
		echo "⏱️  $$phase_name: $${duration}s ($${duration_min} min) [$${status}]"; \
	}; \
	\
	phase_names=("Backend tests" "Web unit tests" "Web e2e tests"); \
	phase_targets=("test" "test-web-unit" "test-web-e2e"); \
	phase_durations=(); \
	phase_durations_min=(); \
	phase_statuses=(); \
	\
	for i in "$${!phase_names[@]}"; do \
		run_phase "$${phase_names[$$i]}" "$${phase_targets[$$i]}"; \
	done; \
	\
	overall_end=$$(date +%s); \
	overall_duration=$$((overall_end - overall_start)); \
	overall_duration_min=$$(awk "BEGIN {printf \"%.2f\", $$overall_duration/60}"); \
	echo ""; \
	echo "========================================"; \
	echo "📊 Podsumowanie make test-all"; \
	echo "========================================"; \
	for i in "$${!phase_names[@]}"; do \
		printf " - %-18s : %6ss (%6s min)  [%s]\n" "$${phase_names[$$i]}" "$${phase_durations[$$i]}" "$${phase_durations_min[$$i]}" "$${phase_statuses[$$i]}"; \
	done; \
	echo "----------------------------------------"; \
	printf " Σ Czas całkowity      : %6ss (%6s min)\n" "$$overall_duration" "$$overall_duration_min"; \
	if [ $$overall_rc -eq 0 ]; then \
		echo "✅ Status końcowy: OK"; \
	else \
		echo "❌ Status końcowy: FAIL"; \
	fi; \
	echo "========================================"; \
	\
	exit $$overall_rc

sonar-reports-backend:
	@mkdir -p test-results/sonar
	pytest -m "not performance and not smoke" -o junit_family=xunit1 --cov=venom_core --cov-report=xml:test-results/sonar/python-coverage.xml --junitxml=test-results/sonar/python-junit.xml

NEW_CODE_COVERAGE_MIN ?= 0
NEW_CODE_TEST_GROUP ?= config/pytest-groups/sonar-new-code.txt
NEW_CODE_BASELINE_GROUP ?= config/pytest-groups/ci-lite.txt
NEW_CODE_INCLUDE_BASELINE ?= 1
NEW_CODE_COV_TARGET ?= venom_core
NEW_CODE_COVERAGE_XML ?= test-results/sonar/python-coverage.xml
NEW_CODE_JUNIT_XML ?= test-results/sonar/python-junit.xml
NEW_CODE_COVERAGE_HTML ?= test-results/sonar/htmlcov-new-code
NEW_CODE_PYTEST_MARK_EXPR ?= not requires_docker and not requires_docker_compose and not performance and not smoke
NEW_CODE_CHANGED_LINES_MIN ?= 80
NEW_CODE_DIFF_BASE ?= origin/main
NEW_CODE_AUTO_INCLUDE_CHANGED ?= 1
NEW_CODE_TIME_BUDGET_SEC ?= 90
NEW_CODE_FALLBACK_COVERAGE ?= 1
NEW_CODE_MAX_FALLBACK_TESTS ?= 20
NEW_CODE_MAX_TESTS ?= 0
NEW_CODE_EXCLUDE_SLOW_FASTLANE ?= 1
NEW_CODE_TEST_CATALOG ?= config/testing/test_catalog.json
TEST_INTEL_SLOW_THRESHOLD ?= 1.8
TEST_INTEL_FAST_THRESHOLD ?= 0.1
TEST_INTEL_MIN_TESTS_PROMOTION ?= 3
TEST_INTEL_TOP_N ?= 15
TEST_INTEL_APPEND_HISTORY ?= 1
TEST_INTEL_HISTORY_FILE ?= test-results/sonar/test-intelligence-history.jsonl

test-fast-coverage:
	@mkdir -p "$$(dirname "$(NEW_CODE_COVERAGE_XML)")"
	@if [ -n "$(NEW_CODE_JUNIT_XML)" ]; then mkdir -p "$$(dirname "$(NEW_CODE_JUNIT_XML)")"; fi
	@if [ -n "$(NEW_CODE_COVERAGE_HTML)" ]; then mkdir -p "$(NEW_CODE_COVERAGE_HTML)"; fi
	@$(PYTHON_BIN) scripts/run_new_code_coverage_gate.py \
		--pytest-bin "$(PYTEST_BIN)" \
		--baseline-group "$(NEW_CODE_BASELINE_GROUP)" \
		--new-code-group "$(NEW_CODE_TEST_GROUP)" \
		--include-baseline "$(NEW_CODE_INCLUDE_BASELINE)" \
		--diff-base "$(NEW_CODE_DIFF_BASE)" \
		--time-budget-sec "$(NEW_CODE_TIME_BUDGET_SEC)" \
		--timings-junit-xml "$(NEW_CODE_JUNIT_XML)" \
		--exclude-slow-fastlane "$(NEW_CODE_EXCLUDE_SLOW_FASTLANE)" \
		--max-tests "$(NEW_CODE_MAX_TESTS)" \
		--catalog "$(NEW_CODE_TEST_CATALOG)" \
		--fallback-coverage "$(NEW_CODE_FALLBACK_COVERAGE)" \
		--max-fallback-tests "$(NEW_CODE_MAX_FALLBACK_TESTS)" \
		--mark-expr "$(NEW_CODE_PYTEST_MARK_EXPR)" \
		--cov-target "$(NEW_CODE_COV_TARGET)" \
		--coverage-xml "$(NEW_CODE_COVERAGE_XML)" \
		--coverage-html "$(NEW_CODE_COVERAGE_HTML)" \
		--junit-xml "$(NEW_CODE_JUNIT_XML)" \
		--cov-fail-under "$(NEW_CODE_COVERAGE_MIN)" \
		--min-coverage "$(NEW_CODE_CHANGED_LINES_MIN)" \
		--sonar-config "sonar-project.properties"

test-light-coverage: test-fast-coverage

check-new-code-coverage: test-fast-coverage
	@$(MAKE) --no-print-directory check-file-coverage-floor \
		COVERAGE_XML="$(NEW_CODE_COVERAGE_XML)" \
		COVERAGE_FLOOR_FILE="config/coverage-file-floor.txt"

check-new-code-coverage-diagnostics:
	@$(PYTHON_BIN) scripts/check_new_code_coverage.py \
		--coverage-xml "$(NEW_CODE_COVERAGE_XML)" \
		--sonar-config "sonar-project.properties" \
		--diff-base "$(NEW_CODE_DIFF_BASE)" \
		--scope "$(NEW_CODE_COV_TARGET)" \
		--min-coverage "$(NEW_CODE_CHANGED_LINES_MIN)"

check-file-coverage-floor:
	@$(PYTHON_BIN) scripts/check_file_coverage_floor.py \
		--coverage-xml "$(COVERAGE_XML)" \
		--thresholds "$(COVERAGE_FLOOR_FILE)"

# Szybki tryb lokalny: krótsza pętla developerska bez zmiany gate'ów CI.
check-new-code-coverage-local:
	@$(MAKE) check-new-code-coverage \
		NEW_CODE_INCLUDE_BASELINE=0 \
		NEW_CODE_FALLBACK_COVERAGE=0 \
		NEW_CODE_TIME_BUDGET_SEC=45 \
		NEW_CODE_COVERAGE_XML=test-results/local-fast/python-coverage.xml \
		NEW_CODE_JUNIT_XML=test-results/local-fast/python-junit.xml \
		NEW_CODE_COVERAGE_HTML=

pr-fast:
	@bash scripts/pr_fast_check.sh

# Agent-friendly wrapper: best-effort refresh of origin/main, then runs pr-fast.
agent-pr-fast:
	@# Best-effort refresh of origin/main: skip or warn if remote is missing/unreachable.
	@if git remote get-url origin >/dev/null 2>&1; then \
		git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main || \
		echo "Warning: git fetch origin/main failed; continuing without refreshed base ref."; \
	else \
		echo "Warning: remote 'origin' not found; skipping git fetch for agent-pr-fast."; \
	fi
	@PR_BASE_REF=origin/main $(MAKE) --no-print-directory pr-fast

# Lokalny skrót zamiast pełnego pr-fast + osobnego check-new-code-coverage.
pr-fast-local:
	@$(MAKE) check-new-code-coverage-local

sonar-reports-backend-new-code: test-light-coverage

sonar-reports-frontend:
	$(NPM) --prefix $(WEB_DIR) run test:unit:coverage

sonar-reports: sonar-reports-backend sonar-reports-frontend

openapi-export:
	python3 scripts/export_openapi.py --output openapi/openapi.json

openapi-codegen-types: openapi-export
	npx --yes openapi-typescript@7.10.1 openapi/openapi.json -o web-next/lib/generated/api-types.d.ts

pytest:
	@set +e; \
	VENOM_API_BASE="$${VENOM_API_BASE:-http://$(HOST_DISPLAY):$(PORT)}" bash scripts/run-pytest-optimal.sh; \
	rc=$$?; \
	$(call handle_pytest_no_tests,pytest) \
	if [ $$rc -ne 0 ]; then \
		echo ""; \
		echo "❌ make pytest: testy nie przeszły (exit=$$rc)."; \
		echo "   Sprawdź sekcję 'short test summary info' powyżej."; \
		exit $$rc; \
	fi

e2e:
	bash scripts/run-e2e-optimal.sh

test-optimal: pytest e2e

test-ci-lite:
	TESTS=$$(grep -vE '^\s*(#|$$)' config/pytest-groups/ci-lite.txt); \
	if [ -z "$$TESTS" ]; then \
		echo "❌ Brak testów w config/pytest-groups/ci-lite.txt"; \
		exit 1; \
	fi; \
	$(PYTEST_BIN) -q $$TESTS

audit-ci-lite:
	@$(MAKE) --no-print-directory ci-lite-preflight
	@echo "🔍 Audyt zależności w testach CI Lite..."
	@$(PYTHON_BIN) scripts/audit_lite_deps.py --import-smoke
	@echo "🔍 Lekka walidacja polityki zależności..."
	@$(PYTHON_BIN) scripts/dev/env_audit.py --ci-check

test-intelligence-report:
	@$(PYTHON_BIN) scripts/test_intelligence_report.py \
		--junit-xml test-results/sonar/python-junit.xml \
		--ci-lite-group config/pytest-groups/ci-lite.txt \
		--new-code-group config/pytest-groups/sonar-new-code.txt \
		--catalog config/testing/test_catalog.json \
		--slow-threshold "$(TEST_INTEL_SLOW_THRESHOLD)" \
		--fast-threshold "$(TEST_INTEL_FAST_THRESHOLD)" \
		--min-tests-for-promotion "$(TEST_INTEL_MIN_TESTS_PROMOTION)" \
		--top-n "$(TEST_INTEL_TOP_N)" \
		--history-file "$(TEST_INTEL_HISTORY_FILE)" \
		--append-history "$(TEST_INTEL_APPEND_HISTORY)" \
		--output text

architecture-drift-check:
	@$(PYTHON_BIN) scripts/check_architecture_contracts.py \
		--contracts config/architecture/contracts.yaml \
		--source-root venom_core
	@$(PYTHON_BIN) scripts/validate_sonar_architecture.py \
		--config config/architecture/sonar-architecture.yaml

architecture-sonar-export:
	@$(PYTHON_BIN) scripts/export_sonar_intended_architecture_payload.py \
		--config config/architecture/sonar-architecture.yaml \
		--output test-results/sonar/architecture-summary.json

optional-modules-contracts-check:
	@$(PYTHON_BIN) scripts/check_optional_modules_contracts.py --repo-root .

test-lane-contracts-check:
	@$(PYTHON_BIN) scripts/check_test_lane_contracts.py \
		--contracts config/testing/lane_contracts.yaml \
		--assignments config/testing/lane_assignments.yaml \
		--repo-root .

test-catalog-sync:
	@$(PYTHON_BIN) scripts/generate_test_catalog.py \
		--repo-root . \
		--output config/testing/test_catalog.json \
		--write 1

test-catalog-check:
	@ENFORCE_CHANGED_TEST_NEW_CODE=1; \
	if [ "$${CI:-}" = "true" ] || [ "$${CI:-}" = "1" ]; then \
		ENFORCE_CHANGED_TEST_NEW_CODE=0; \
	fi; \
	$(PYTHON_BIN) scripts/check_test_catalog.py \
		--catalog config/testing/test_catalog.json \
		--repo-root . \
		--ci-lite-group config/pytest-groups/ci-lite.txt \
		--new-code-group config/pytest-groups/sonar-new-code.txt \
		--fast-group config/pytest-groups/fast.txt \
		--long-group config/pytest-groups/long.txt \
		--heavy-group config/pytest-groups/heavy.txt \
		--enforce-changed-test-new-code "$$ENFORCE_CHANGED_TEST_NEW_CODE" \
		--diff-base "$(NEW_CODE_DIFF_BASE)"

test-groups-sync:
	@$(PYTHON_BIN) scripts/sync_pytest_groups_from_catalog.py \
		--repo-root . \
		--catalog config/testing/test_catalog.json \
		--write 1

test-groups-check:
	@$(PYTHON_BIN) scripts/sync_pytest_groups_from_catalog.py \
		--repo-root . \
		--catalog config/testing/test_catalog.json \
		--check

test-dynamic-preview:
	@mkdir -p test-results/sonar
	@$(PYTHON_BIN) scripts/resolve_sonar_new_code_tests.py \
		--baseline-group config/pytest-groups/ci-lite.txt \
		--new-code-group config/pytest-groups/sonar-new-code.txt \
		--include-baseline 1 \
		--diff-base "$(NEW_CODE_DIFF_BASE)" \
		--exclude-slow-fastlane 1 \
		--catalog config/testing/test_catalog.json \
		--debug-json test-results/sonar/dynamic-selection-preview.json >/dev/null
	@echo "✅ Dynamic preview saved: test-results/sonar/dynamic-selection-preview.json"

ci-lite-preflight:
	@if ! command -v "$(PYTHON_BIN)" >/dev/null 2>&1; then \
		echo "❌ Nie znaleziono interpretera Pythona: $(PYTHON_BIN)"; \
		echo "   Skonfiguruj środowisko (np. make ci-lite-bootstrap) i spróbuj ponownie."; \
		exit 2; \
	fi
	@if [ ! -x "$(VENV)/bin/python" ]; then \
		if [ "$${CI:-}" = "true" ]; then \
			echo "ℹ️ CI mode: brak $(VENV), używam $(PYTHON_BIN)"; \
		else \
			echo "❌ Brak środowiska $(VENV)."; \
			echo "   Uruchom: make ci-lite-bootstrap"; \
			exit 2; \
		fi; \
	fi
	@$(PYTHON_BIN) scripts/ci_lite_preflight.py

ci-lite-bootstrap:
	@if [ ! -d "$(VENV)" ]; then python3 -m venv "$(VENV)"; fi
	@"$(VENV)/bin/pip" install --upgrade pip
	@"$(VENV)/bin/pip" install -r requirements-ci-lite.txt

install-hooks:
	pre-commit install
	pre-commit install --hook-type pre-push

sync-sonar-new-code-group:
	pre-commit run --hook-stage manual update-sonar-new-code-group

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
	NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev $(NEXT_TURBO_WATCH_ENV) $(4) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run $(2) -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI ($(1)) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"
	@echo "$(3)"
endef

start: start-dev

start-dev:
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=dev START_WEB_MODE=turbo _start

start2: start-dev-webpack

start-dev-webpack:
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=dev START_WEB_MODE=webpack _start

start-dev-turbo:
	$(MAKE) --no-print-directory start-dev

start-prod:
	@echo "⚠️  OSTRZEŻENIE: tryb 'prod' nie jest jeszcze oficjalnie zwalidowany/rekomendowany operacyjnie."
	@echo "⚠️  Zalecane środowiska: 'dev' (testy/prace) oraz 'preprod' (UAT + smoke read-only)."
	$(MAKE) --no-print-directory ensure-env-file
	$(MAKE) --no-print-directory START_MODE=prod _start

start-preprod:
	$(PREPROD_ENV_READONLY) \
		$(MAKE) --no-print-directory ensure-env-file
	$(PREPROD_ENV_READONLY) \
		$(MAKE) --no-print-directory START_MODE=prod _start

# Preprod aliases (short commands)
startpre: start-preprod
stoppre: stop
restartpre:
	$(MAKE) --no-print-directory stoppre
	$(MAKE) --no-print-directory startpre
statuspre: status
apipre: api-preprod
webpre: web-preprod
testpre: test-preprod-readonly-smoke
ensurepreenv: ensure-preprod-env-file

ensure-env-file:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		if [ -f "$(ENV_EXAMPLE_FILE)" ]; then \
			cp "$(ENV_EXAMPLE_FILE)" "$(ENV_FILE)"; \
			echo "ℹ️  Utworzono $(ENV_FILE) na podstawie $(ENV_EXAMPLE_FILE)."; \
			echo "ℹ️  Uzupełnij klucze/secrets w $(ENV_FILE) (jeśli wymagane) i uruchom ponownie start."; \
		else \
			echo "⚠️  Brak $(ENV_FILE) i $(ENV_EXAMPLE_FILE). Start użyje wartości domyślnych tam, gdzie to możliwe."; \
		fi; \
	fi

ensure-preprod-env-file:
	@$(PREPROD_ENV_BASE) \
		$(MAKE) --no-print-directory ensure-env-file

preprod-backup:
	@$(PREPROD_ENV_READONLY) \
		bash scripts/preprod/backup_restore.sh backup

preprod-restore:
	@$(PREPROD_ENV_MUTATION) \
		bash scripts/preprod/backup_restore.sh restore "$${TS:-}"

preprod-verify:
	@$(PREPROD_ENV_READONLY) \
		bash scripts/preprod/backup_restore.sh verify "$${TS:-}"
	@$(MAKE) --no-print-directory test-preprod-readonly-smoke

preprod-audit:
	@bash scripts/preprod/audit_log.sh \
		"$${ACTOR:-unknown}" \
		"$${ACTION:-manual-operation}" \
		"$${TICKET:-N/A}" \
		"$${RESULT:-OK}"

preprod-drill:
	@set -e; \
	backup_out="$$( $(MAKE) --no-print-directory preprod-backup )"; \
	echo "$$backup_out"; \
	ts="$$(printf '%s\n' "$$backup_out" | sed -n 's/^Backup timestamp:[[:space:]]*//p' | tail -n 1)"; \
	if [ -z "$$ts" ]; then \
		echo "❌ Nie udało się odczytać timestamp z backupu preprod."; \
		exit 1; \
	fi; \
	$(MAKE) --no-print-directory preprod-verify TS="$$ts"; \
	echo "✅ Preprod drill zakończony (TS=$$ts)."

preprod-readiness-check:
	@$(PYTHON_BIN) scripts/preprod/readiness_check.py \
		--env-file "$${ENV_FILE_PATH:-.env.preprod}" \
		--actor "$${ACTOR:-unknown}" \
		--ticket "$${TICKET:-N/A}" \
		--run-audit "$${RUN_AUDIT:-1}" \
		--dry-run "$${DRY_RUN:-0}"

# Preprod operation aliases
prebackup: preprod-backup
prerestore: preprod-restore
preverify: preprod-verify
preaudit: preprod-audit
predrill: preprod-drill
prereadiness: preprod-readiness-check

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
		if ! $(MAKE) --no-print-directory ollama-start >/dev/null; then \
			echo "❌ Nie udało się wywołać 'ollama-start' (sprawdź instalację/usługę Ollama)."; \
			return 1; \
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
			UVICORN_FLAGS="--host $(HOST) --port $(PORT) $(UVICORN_DEV_FLAGS)"; \
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
		: > $(WEB_LOG); \
		if [ "$(START_MODE)" = "prod" ]; then \
			echo "🛠  Buduję Next.js (npm run build)"; \
			NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(NPM) --prefix $(WEB_DIR) run build >/dev/null 2>&1; \
			echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"; \
			NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
			echo $$! > $(WEB_PID_FILE); \
		else \
			if [ "$(START_WEB_MODE)" != "webpack" ] && [ "$(START_WEB_MODE)" != "turbo" ] && [ "$(START_WEB_MODE)" != "turbo-debug" ]; then \
				echo "❌ Nieznany START_WEB_MODE='$(START_WEB_MODE)' (dozwolone: webpack|turbo|turbo-debug)"; \
				exit 1; \
			fi; \
			if [ "$(START_WEB_MODE)" = "turbo" ]; then \
				echo "▶️  Uruchamiam UI (Next.js dev:turbo, host $(WEB_HOST), port $(WEB_PORT))"; \
				NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev NEXT_TELEMETRY_DISABLED=1 $(NEXT_TURBO_WATCH_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run dev:turbo -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			elif [ "$(START_WEB_MODE)" = "turbo-debug" ]; then \
				echo "▶️  Uruchamiam UI (Next.js dev:turbo:debug, host $(WEB_HOST), port $(WEB_PORT))"; \
				NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=dev $(NEXT_TURBO_WATCH_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run dev:turbo:debug -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			else \
				echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"; \
				NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_DEV_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
				echo $$! > $(WEB_PID_FILE); \
			fi; \
		fi; \
		WPID=$$(cat $(WEB_PID_FILE)); \
		ui_ready=""; \
		for attempt in {1..40}; do \
			if kill -0 $$WPID 2>/dev/null; then \
				if curl -fsS http://$(WEB_DISPLAY):$(WEB_PORT) >/dev/null 2>&1; then \
					ui_ready="yes"; \
					break; \
				fi; \
			else \
				echo "❌ UI (Next.js) proces $$WPID zakończył się przed startem"; \
				break; \
			fi; \
			sleep 1; \
		done; \
			if [ -z "$$ui_ready" ]; then \
				echo "❌ UI (Next.js) nie wystartował poprawnie na porcie $(WEB_PORT)"; \
				kill -TERM -$$WPID 2>/dev/null || kill $$WPID 2>/dev/null || true; \
				rm -f $(WEB_PID_FILE); \
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
			if [ "$(START_MODE)" = "dev" ]; then \
				expected_bundler=""; \
				if [ "$(START_WEB_MODE)" = "webpack" ]; then \
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
	NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(NPM) --prefix $(WEB_DIR) run build >/dev/null 2>&1
	@echo "▶️  Uruchamiam UI (Next.js start, host $(WEB_HOST), port $(WEB_PORT))"
	NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_PROD_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run start -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
	echo $$! > $(WEB_PID_FILE)
	@echo "✅ UI (Next.js) wystartował z PID $$(cat $(WEB_PID_FILE))"
	@echo "🎨 Dashboard: http://$(WEB_DISPLAY):$(WEB_PORT)"

# Frontend Web (tylko) - developerski (next dev)
web-dev:
	@mkdir -p logs
	$(call ensure_process_not_running,UI (Next.js),$(WEB_PID_FILE))
	: > $(WEB_LOG)
	@echo "▶️  Uruchamiam UI (Next.js dev, host $(WEB_HOST), port $(WEB_PORT))"
	NEXT_PUBLIC_APP_VERSION="$(WEB_APP_VERSION)" NEXT_PUBLIC_ENVIRONMENT_ROLE="$${ENVIRONMENT_ROLE:-dev}" $(NEXT_DEV_ENV) $(ENV_RUN) setsid $(NPM) --prefix $(WEB_DIR) run dev -- --hostname $(WEB_HOST) --port $(WEB_PORT) >> $(WEB_LOG) 2>&1 & \
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

# =============================================================================
# Odchudzanie środowiska (Repo + Docker)
# =============================================================================

env-audit:
	@python3 scripts/dev/env_audit.py

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

help:
	@echo "Venom Makefile - najczęściej używane komendy"
	@echo ""
	@echo "Start/Stop:"
	@echo "  make start                    - start backend + frontend (turbopack) + runtime LLM"
	@echo "  make start2                   - start backend + frontend (webpack) + runtime LLM"
	@echo "  make stop                     - stop backend + frontend + runtime LLM"
	@echo "  make status                   - status procesów"
	@echo "  make web-dev                  - frontend dev (webpack, fallback)"
	@echo "  make web-dev-turbo            - frontend dev (turbopack, domyślny tryb dev)"
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
	@echo "  make test-groups-check        - weryfikacja grup testów"
	@echo "  make test-catalog-check       - weryfikacja katalogu testów"
