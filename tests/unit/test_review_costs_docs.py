"""Contract: review info --costs stays documented and keeps a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
HELP_SH = ROOT / "scripts" / "help.sh"
REVIEW_PY = ROOT / "scripts" / "review.py"
DIAG_COSTS = ROOT / "scripts" / "lib" / "diag_costs.py"


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


def test_diag_costs_module_exists() -> None:
    assert DIAG_COSTS.is_file()
    text = DIAG_COSTS.read_text(encoding="utf-8")
    assert "def run_costs" in text
    assert "def summarize" in text
    assert "cost_records" in text


def test_agents_md_documents_run_cost_summary_cli() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Run cost summary CLI" in text
    assert "scripts/review.py info" in text
    assert "--costs" in text
    assert "scripts/lib/diag_costs.py" in text
    assert "cost_records" in text


def test_scripts_md_lists_review_info_costs() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "scripts/review.py info" in text
    assert "--costs" in text
    assert "diag_costs.py" in text


def test_help_sh_lists_review_info_costs() -> None:
    text = HELP_SH.read_text(encoding="utf-8")
    assert "scripts/review.py info" in text
    assert "--costs" in text


def test_review_info_cli_exposes_costs_flag() -> None:
    names = _argparse_dest_names(REVIEW_PY)
    assert "costs" in names
    assert "workflow_id" in names
    assert "run_dir" in names
