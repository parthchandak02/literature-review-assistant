"""Contract: Jev eval CLI stays documented and keeps a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
HELP_SH = ROOT / "scripts" / "help.sh"
CHECK_PY = ROOT / "scripts" / "check.py"
JEV_EVAL = ROOT / "scripts" / "lib" / "check_jev_eval.py"


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


def test_jev_eval_module_exists() -> None:
    assert JEV_EVAL.is_file()
    text = JEV_EVAL.read_text(encoding="utf-8")
    assert "def evaluate_db" in text
    assert "def run_live_sample" in text
    assert "def build_parser" in text


def test_agents_md_documents_jev_eval_cli() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Jev eval CLI" in text
    assert "scripts/check.py jev-eval" in text
    assert "scripts/lib/check_jev_eval.py" in text
    assert "--db" in text
    assert "--confirm-live" in text
    assert "jev_decisions" in text


def test_scripts_md_lists_jev_eval() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "jev-eval" in text
    assert "--db" in text
    assert "--confirm-live" in text


def test_help_sh_lists_jev_eval() -> None:
    text = HELP_SH.read_text(encoding="utf-8")
    assert "jev-eval" in text


def test_check_py_routes_jev_eval() -> None:
    text = CHECK_PY.read_text(encoding="utf-8")
    assert '"jev-eval"' in text
    assert "check_jev_eval" in text


def test_jev_eval_cli_shape() -> None:
    names = _argparse_dest_names(JEV_EVAL)
    assert "db" in names
    assert "json" in names
    assert "live_sample" in names
    assert "confirm_live" in names
    assert "out" in names
