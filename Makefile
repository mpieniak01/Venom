# Makefile dla Venom

.PHONY: lint format test precommit install-hooks

lint:
	pre-commit run --all-files

format:
	black . && isort .

test:
	pytest -q

install-hooks:
	pre-commit install
