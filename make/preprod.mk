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
