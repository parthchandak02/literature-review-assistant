"""Guard that uv and pnpm enforce a 7-day minimum dependency release age."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"
PNPM_WORKSPACE_PATH = REPO_ROOT / "frontend" / "pnpm-workspace.yaml"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"


def test_uv_excludes_newer_than_7_days() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    assert pyproject["tool"]["uv"]["exclude-newer"] == "7 days"

    lock = tomllib.loads(UV_LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["options"]["exclude-newer-span"] == "P7D"


def test_pnpm_sets_7_day_minimum_release_age() -> None:
    workspace = yaml.safe_load(PNPM_WORKSPACE_PATH.read_text(encoding="utf-8"))
    assert workspace["minimumReleaseAge"] == 10080


def test_agents_md_documents_dependency_age_policy_and_override() -> None:
    text = AGENTS_PATH.read_text(encoding="utf-8")
    assert "7 days old" in text
    assert "exclude-newer-package" in text
    assert "minimumReleaseAgeExclude" in text
