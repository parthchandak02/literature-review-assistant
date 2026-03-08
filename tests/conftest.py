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

from dotenv import load_dotenv

load_dotenv(override=True)
