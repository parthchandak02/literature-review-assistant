"""Contract: UX screenshot harness scripts stay documented and keep a stable CLI shape."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
SCRIPTS_DOC = ROOT / "docs" / "SCRIPTS.md"
UX_SCREENSHOTS = ROOT / "scripts" / "ux_screenshots.py"
UX_SCREENING = ROOT / "scripts" / "ux_screening_preview.py"


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


def test_ux_harness_script_files_exist() -> None:
    assert UX_SCREENSHOTS.is_file()
    assert UX_SCREENING.is_file()


def test_agents_md_documents_ux_screenshot_harness() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## UX screenshot harness" in text
    assert "scripts/ux_screenshots.py" in text
    assert "scripts/ux_screening_preview.py" in text
    assert "tmp/ux-shots" in text
    assert "playwright" in text.lower()


def test_scripts_md_lists_ux_harnesses() -> None:
    text = SCRIPTS_DOC.read_text(encoding="utf-8")
    assert "scripts/ux_screenshots.py" in text
    assert "scripts/ux_screening_preview.py" in text


def test_ux_screenshots_cli_shape() -> None:
    names = _argparse_dest_names(UX_SCREENSHOTS)
    assert "label" in names
    assert "base" in names


def test_ux_screening_preview_cli_shape() -> None:
    names = _argparse_dest_names(UX_SCREENING)
    assert "label" in names
    assert "base" in names
    assert "workflow" in names
