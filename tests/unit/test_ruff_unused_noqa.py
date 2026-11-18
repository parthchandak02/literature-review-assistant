"""Guard that unused noqa suppressions stay in the default ruff rule set."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def test_ruff_select_includes_unused_noqa() -> None:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    select = data["tool"]["ruff"]["lint"]["select"]
    assert "RUF100" in select


def test_ruff_select_includes_asyncio_dangling_task() -> None:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    select = data["tool"]["ruff"]["lint"]["select"]
    assert "RUF006" in select
