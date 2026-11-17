"""Contract: PRISMA regenerate CLI stays documented and keeps a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
HELP_SH = ROOT / "scripts" / "help.sh"
REGENERATE_PY = ROOT / "scripts" / "regenerate_prisma.py"
REGENERATE_MOD = ROOT / "src" / "prisma" / "regenerate.py"


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


def test_regenerate_module_exists() -> None:
    assert REGENERATE_MOD.is_file()
    text = REGENERATE_MOD.read_text(encoding="utf-8")
    assert "async def regenerate_prisma" in text or "def regenerate_prisma" in text
    assert "def format_counts_diff" in text
    assert "def stale_manuscript_warning" in text


def test_agents_md_documents_prisma_regenerate_cli() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## PRISMA regenerate CLI" in text
    assert "scripts/regenerate_prisma.py" in text
    assert "src/prisma/regenerate.py" in text
    assert "--dry-run" in text
    assert "prisma_counts.json" in text


def test_scripts_md_lists_regenerate_prisma() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "scripts/regenerate_prisma.py" in text
    assert "--dry-run" in text


def test_help_sh_lists_regenerate_prisma() -> None:
    text = HELP_SH.read_text(encoding="utf-8")
    assert "regenerate_prisma.py" in text


def test_regenerate_prisma_cli_shape() -> None:
    assert REGENERATE_PY.is_file()
    names = _argparse_dest_names(REGENERATE_PY)
    assert "run" in names
    assert "dry_run" in names
    assert "run_root" in names
