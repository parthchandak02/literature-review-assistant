"""Validation tests for the GitHub Actions CI workflow."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SHA_PIN_RE = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _load_workflow() -> dict:
    assert CI_WORKFLOW_PATH.is_file(), f"Missing CI workflow: {CI_WORKFLOW_PATH}"
    data = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_ci_workflow_triggers_and_runners() -> None:
    raw_text = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    data = _load_workflow()
    # PyYAML parses bare `on` as boolean True unless quoted.
    triggers = data.get("on") if "on" in data else data.get(True)
    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert "secrets." not in raw_text

    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs
    for job_name, job in jobs.items():
        assert job.get("runs-on") == "ubuntu-latest", f"Job {job_name} must run on ubuntu-latest"


def test_ci_workflow_pins_all_actions_to_full_commit_shas() -> None:
    data = _load_workflow()
    jobs = data["jobs"]
    uses_refs: list[str] = []
    for job in jobs.values():
        for step in job.get("steps", []):
            if "uses" in step:
                uses_refs.append(step["uses"])

    assert uses_refs, "Expected CI workflow to reference GitHub Actions"
    for ref in uses_refs:
        assert SHA_PIN_RE.match(ref), f"Action must be pinned to a full 40-char commit SHA: {ref}"


def test_ci_workflow_runs_backend_and_frontend_checks() -> None:
    data = _load_workflow()
    jobs = data["jobs"]

    assert "backend" in jobs
    backend_runs = "\n".join(step.get("run", "") for step in jobs["backend"].get("steps", []))
    assert "uv sync" in backend_runs
    assert "ruff check" in backend_runs
    assert "pytest" in backend_runs

    assert "frontend" in jobs
    frontend_runs = "\n".join(step.get("run", "") for step in jobs["frontend"].get("steps", []))
    assert "pnpm install" in frontend_runs
    assert "pnpm test" in frontend_runs
    assert "pnpm build" in frontend_runs
