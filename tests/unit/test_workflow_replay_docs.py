"""Contract: Workflow replay and fixture CLI commands stay documented and keep a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
HELP_SH = ROOT / "scripts" / "help.sh"
CHECK_PY = ROOT / "scripts" / "check.py"
REPAIR_PY = ROOT / "scripts" / "repair.py"
CHECK_REPLAY_FIXTURE = ROOT / "scripts" / "lib" / "check_replay_fixture.py"
CHECK_WORKFLOW_REPLAY = ROOT / "scripts" / "lib" / "check_workflow_replay.py"
MAINT_REPLAY_FIXTURE = ROOT / "scripts" / "lib" / "maint_replay_fixture.py"


def _argparse_dest_names(script: Path) -> set[str]:
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            flag = first.value
            names.add(flag.lstrip("-").replace("-", "_") if flag.startswith("-") else flag)
    return names


def test_workflow_replay_modules_exist() -> None:
    assert CHECK_REPLAY_FIXTURE.is_file()
    assert CHECK_WORKFLOW_REPLAY.is_file()
    assert MAINT_REPLAY_FIXTURE.is_file()
    assert "def check_fixture" in CHECK_REPLAY_FIXTURE.read_text(encoding="utf-8")
    assert "async def _run_checks" in CHECK_WORKFLOW_REPLAY.read_text(encoding="utf-8")
    assert "async def run_regen_replay_fixture" in MAINT_REPLAY_FIXTURE.read_text(encoding="utf-8")


def test_agents_md_documents_workflow_replay_cli() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Workflow replay CLI" in text
    assert "scripts/check.py replay-fixture" in text
    assert "scripts/check.py replay-workflow" in text
    assert "scripts/repair.py regen-replay-fixture" in text
    assert "scripts/lib/check_replay_fixture.py" in text
    assert "scripts/lib/check_workflow_replay.py" in text
    assert "scripts/lib/maint_replay_fixture.py" in text
    assert "tests/fixtures/replay" in text


def test_scripts_md_lists_workflow_replay_commands() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "replay-fixture" in text
    assert "replay-workflow" in text
    assert "regen-replay-fixture" in text


def test_help_sh_lists_workflow_replay_commands() -> None:
    text = HELP_SH.read_text(encoding="utf-8")
    assert "replay-fixture" in text
    assert "replay-workflow" in text
    assert "regen-replay-fixture" in text


def test_check_py_replay_workflow_cli_shape() -> None:
    names = _argparse_dest_names(CHECK_PY)
    assert "workflow_id" in names
    assert "db_path" in names
    assert "profile" in names
    assert "fail_on_error" in names
    assert "run_root" in names


def test_repair_py_regen_replay_fixture_cli_shape() -> None:
    names = _argparse_dest_names(REPAIR_PY)
    assert "profile" in names
    assert "workflow_id" in names
    assert "run_root" in names
    assert "source_run_dir" in names
    assert "db_path" in names
    assert "output_dir" in names
