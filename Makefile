.PHONY: lint test-unit test-integration-smoke parity check-replay-fixture local-ci release-check

lint:
	uv run ruff check .

test-unit:
	uv run pytest tests/unit -q

test-integration-smoke:
	uv run pytest tests/integration/test_api_endpoint_parity_gate.py -q

parity:
	uv run python scripts/check_spec_endpoint_parity.py

check-replay-fixture:
	uv run python scripts/check_replay_fixture_schema.py

local-ci:
	./scripts/local_ci.sh

release-check:
	./scripts/release_check.sh
