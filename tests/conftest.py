"""Root test configuration.

Loads .env at session start so API keys are available to all tests,
including integration tests that instantiate components directly without
going through src/config/loader.py (which is the only other place
load_dotenv() is called in this codebase).

override=True ensures .env takes precedence over stale/invalid keys that
may already be set in the shell environment (e.g. an expired GOOGLE_API_KEY
exported in .zshrc).  The project's own load_dotenv() calls use the default
(no override) which is correct for production; tests need the .env values.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv(override=True)


@pytest.fixture
def workflow_replay_id() -> str | None:
    """Optional workflow id for real-data replay tests (set WORKFLOW_REPLAY_ID)."""
    value = os.getenv("WORKFLOW_REPLAY_ID", "").strip()
    return value or None


@pytest.fixture
def workflow_replay_db_path() -> str | None:
    """Optional runtime.db path for real-data replay tests (set WORKFLOW_REPLAY_DB_PATH)."""
    value = os.getenv("WORKFLOW_REPLAY_DB_PATH", "").strip()
    return value or None
