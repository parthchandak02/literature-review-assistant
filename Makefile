.PHONY: lint test-unit test-integration-smoke check-api check-replay-fixture check-local check-release pm2-restart deploy-prod scripts-help

lint:
	uv run ruff check .

test-unit:
	uv run pytest tests/unit -q

test-integration-smoke:
	uv run pytest tests/integration/test_api_endpoint_parity_gate.py -q

# Quality checks (lay-friendly names; see scripts/check.py and scripts/check.sh)
check-api:
	uv run python scripts/check.py api

check-replay-fixture:
	uv run python scripts/check.py replay-fixture

check-local:
	./scripts/check.sh local

check-release:
	./scripts/check.sh release

# Short aliases kept for habit / docs
parity: check-api
local-ci: check-local
release-check: check-release

pm2-restart:
	./scripts/ops_pm2.sh restart

deploy-prod:
	./scripts/ops_pm2.sh restart --prod-ui

scripts-help:
	./scripts/help.sh
