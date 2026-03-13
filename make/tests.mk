# Test Artifact Strategy (docs/TEST_ARTIFACTS_POLICY.md)
# Domyślnie: CLEAN (artefakty testowe są usuwane)
# Opcjonalnie: PRESERVE (artefakty zachowane do debugowania)
TEST_ARTIFACT_MODE ?= clean
TEST_ARTIFACT_CLEANUP_DAYS ?= 7

test:
	@echo "🧪 Uruchamiam testy w trybie CLEAN (artefakty usuwane po sesji)..."
	@set +e; \
	VENOM_TEST_ARTIFACT_MODE=clean VENOM_API_BASE="$${VENOM_API_BASE:-http://$${HOST_DISPLAY:-127.0.0.1}:$${PORT:-8000}}" bash scripts/run-pytest-optimal.sh; \
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
	VENOM_TEST_ARTIFACT_MODE=preserve VENOM_API_BASE="$${VENOM_API_BASE:-http://$${HOST_DISPLAY:-127.0.0.1}:$${PORT:-8000}}" bash scripts/run-pytest-optimal.sh; \
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
		days="$${TEST_ARTIFACT_CLEANUP_DAYS:-7}"; \
		if ! printf '%s' "$$days" | grep -Eq '^[0-9]+$$'; then \
			echo "❌ Nieprawidłowe TEST_ARTIFACT_CLEANUP_DAYS='$$days' (oczekiwano liczby całkowitej)."; \
			exit 2; \
		fi; \
		echo "Usuwanie artefaktów starszych niż $$days dni..."; \
		find test-results/tmp -type d -name "session-*" -mtime +"$$days" -exec rm -rf {} + 2>/dev/null || true; \
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

test-llm-manual:
	@echo "🧪 Manual LLM/runtime tests (operator-triggered only)"
	pytest -m manual_llm

test-duration-audit:
	@echo "🕒 Duration audit (>120s) for long/heavy groups"
	@echo "Long group:"
	@pytest -q -n 1 $$(grep -vE '^\s*(#|$$)' config/pytest-groups/long.txt) --durations=0 --durations-min=120 || true
	@echo ""
	@echo "Heavy group:"
	@pytest -q -n 1 $$(grep -vE '^\s*(#|$$)' config/pytest-groups/heavy.txt) --durations=0 --durations-min=120 || true
	@echo ""
	@echo "Manual exclusion list: config/pytest-groups/manual-long-running.txt"

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
	pytest -n "$(SONAR_BACKEND_PYTEST_WORKERS)" -m "not performance and not smoke" -o junit_family=xunit1 --cov=venom_core --cov-report=xml:test-results/sonar/python-coverage.xml --junitxml=test-results/sonar/python-junit.xml

NEW_CODE_COVERAGE_MIN ?= 0
NEW_CODE_PYTEST_WORKERS ?= 4
SONAR_BACKEND_PYTEST_WORKERS ?= 1
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
		--workers "$(NEW_CODE_PYTEST_WORKERS)" \
		--min-coverage "$(NEW_CODE_CHANGED_LINES_MIN)" \
		--sonar-config "sonar-project.properties"

test-light-coverage:
	@echo "⚠️  test-light-coverage jest aliasem kompatybilności. Użyj: make test-fast-coverage"
	@$(MAKE) --no-print-directory test-fast-coverage

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

sonar-reports-backend-new-code: test-fast-coverage

sonar-reports-frontend:
	$(NPM) --prefix $(WEB_DIR) run test:unit:coverage

sonar-reports: sonar-reports-backend sonar-reports-frontend

openapi-export:
	@$(PYTHON_BIN) scripts/export_openapi.py --output openapi/openapi.json

openapi-codegen-types: openapi-export
	npx --yes openapi-typescript@7.10.1 openapi/openapi.json -o web-next/lib/generated/api-types.d.ts

pytest:
	@set +e; \
	VENOM_API_BASE="$${VENOM_API_BASE:-http://$${HOST_DISPLAY:-127.0.0.1}:$${PORT:-8000}}" bash scripts/run-pytest-optimal.sh; \
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
	@$(PYTHON_BIN) scripts/check_github_actions_node_runtime.py
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
