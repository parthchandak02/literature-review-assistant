"""Contract: Run repair CLI commands stay documented and keep a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
HELP_SH = ROOT / "scripts" / "help.sh"
REPAIR_PY = ROOT / "scripts" / "repair.py"
MAINT_FINALIZE = ROOT / "scripts" / "lib" / "maint_finalize.py"
MAINT_RE_EXTRACT = ROOT / "scripts" / "lib" / "maint_re_extract.py"
INJECT_CITATIONS = ROOT / "scripts" / "lib" / "inject_citations.py"


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


def _subparser_names(script: Path) -> set[str]:
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_parser"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
    return names


def test_run_repair_modules_exist() -> None:
    assert MAINT_FINALIZE.is_file()
    assert MAINT_RE_EXTRACT.is_file()
    assert INJECT_CITATIONS.is_file()
    assert "async def run_finalize" in MAINT_FINALIZE.read_text(encoding="utf-8")
    assert "async def run_re_extract" in MAINT_RE_EXTRACT.read_text(encoding="utf-8")
    inject_text = INJECT_CITATIONS.read_text(encoding="utf-8")
    assert "async def run_inject_citations" in inject_text
    assert "def resolve_run_dir" in inject_text


def test_agents_md_documents_run_repair_cli() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Run repair CLI" in text
    assert "scripts/repair.py finalize" in text
    assert "scripts/repair.py re-extract" in text
    assert "scripts/repair.py inject-citations" in text
    assert "scripts/lib/maint_finalize.py" in text
    assert "scripts/lib/maint_re_extract.py" in text
    assert "scripts/lib/inject_citations.py" in text


def test_scripts_md_lists_run_repair_commands() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "scripts/repair.py finalize" in text
    assert "scripts/repair.py re-extract" in text
    assert "scripts/repair.py inject-citations" in text


def test_help_sh_lists_run_repair_commands() -> None:
    text = HELP_SH.read_text(encoding="utf-8")
    assert "scripts/repair.py finalize" in text
    assert "scripts/repair.py re-extract" in text
    assert "scripts/repair.py inject-citations" in text


def test_repair_py_run_repair_cli_shape() -> None:
    subcommands = _subparser_names(REPAIR_PY)
    assert "finalize" in subcommands
    assert "re-extract" in subcommands
    assert "inject-citations" in subcommands
    names = _argparse_dest_names(REPAIR_PY)
    assert "run_dir" in names
    assert "config" in names
    assert "workflow_id" in names
