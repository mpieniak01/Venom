start-preprod: ENV_FILE=.env.preprod
start-preprod: ENV_EXAMPLE_FILE=.env.preprod.example
start-preprod: START_MODE=prod
start-preprod: START_WEB_MODE=webpack
start-preprod: export ENVIRONMENT_ROLE=preprod
start-preprod: export DB_SCHEMA=preprod
start-preprod: export CACHE_NAMESPACE=preprod
start-preprod: export QUEUE_NAMESPACE=preprod
start-preprod: export STORAGE_PREFIX=preprod
start-preprod: export ALLOW_DATA_MUTATION=0
start-preprod: ensure-env-file _start

# Preprod aliases (short commands)
startpre: start-preprod
stoppre: stop
restartpre: stoppre startpre
statuspre: status
apipre: api-preprod
webpre: web-preprod
testpre: test-preprod-readonly-smoke
ensurepreenv: ensure-preprod-env-file

ensure-env-file:
	@bash scripts/dev/ensure_env_file.sh "$(ENV_FILE)" "$(ENV_EXAMPLE_FILE)"

ensure-preprod-env-file: ENV_FILE=.env.preprod
ensure-preprod-env-file: ENV_EXAMPLE_FILE=.env.preprod.example
ensure-preprod-env-file: ensure-env-file

preprod-backup:
	@$(PREPROD_ENV_READONLY) \
		bash scripts/preprod/backup_restore.sh backup

preprod-restore:
	@$(PREPROD_ENV_MUTATION) \
		bash scripts/preprod/backup_restore.sh restore "$${TS:-}"

preprod-verify:
	@$(PREPROD_ENV_READONLY) \
		bash scripts/preprod/backup_restore.sh verify "$${TS:-}"
	@$(PREPROD_ENV_READONLY) \
		$(PYTEST_BIN) -q tests/test_preprod_readonly_smoke.py tests/test_preprod_optional_modules_smoke.py -m smoke

preprod-audit:
	@bash scripts/preprod/audit_log.sh \
		"$${ACTOR:-unknown}" \
		"$${ACTION:-manual-operation}" \
		"$${TICKET:-N/A}" \
		"$${RESULT:-OK}"

preprod-drill:
	@set -e; \
	backup_out="$$( $(PREPROD_ENV_READONLY) bash scripts/preprod/backup_restore.sh backup )"; \
	echo "$$backup_out"; \
	ts="$$(printf '%s\n' "$$backup_out" | sed -n 's/^Backup timestamp:[[:space:]]*//p' | tail -n 1)"; \
	if [ -z "$$ts" ]; then \
		echo "❌ Nie udało się odczytać timestamp z backupu preprod."; \
		exit 1; \
	fi; \
	if ! printf '%s' "$$ts" | grep -Eq '^[0-9]{8}[-_][0-9]{6}$$'; then \
		echo "❌ Nieprawidłowy format timestamp z backupu preprod: '$$ts'."; \
		exit 2; \
	fi; \
	$(PREPROD_ENV_READONLY) bash scripts/preprod/backup_restore.sh verify "$$ts"; \
	$(PREPROD_ENV_READONLY) $(PYTEST_BIN) -q tests/test_preprod_readonly_smoke.py tests/test_preprod_optional_modules_smoke.py -m smoke; \
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
