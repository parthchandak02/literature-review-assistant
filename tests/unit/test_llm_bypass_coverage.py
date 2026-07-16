"""Guardrail: visualization LLM entrypoints must wire provider rate limiting and cost logging."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_VISUALIZATION_LLM_MODULES = (
    "src/visualization/concept_diagrams.py",
    "src/visualization/research_diagram_renderer.py",
    "src/visualization/research_diagram_placement.py",
    "src/visualization/research_diagram_preparer.py",
)

_WIRING_MARKERS = (
    "reserve_call_slot",
    "log_cost",
    "save_cost_record",
    "_log_usage_cost",
)


def _functions_calling_get_chat_client(module_path: Path) -> list[str]:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if "get_chat_client" not in segment:
            continue
        if not any(marker in segment for marker in _WIRING_MARKERS):
            rel = module_path.relative_to(_REPO_ROOT)
            raise AssertionError(
                f"{rel}:{node.name} calls get_chat_client without provider/cost wiring "
                f"(expected one of {_WIRING_MARKERS})"
            )
        hits.append(node.name)
    return hits


def test_visualization_modules_wire_llm_provider_for_chat_client() -> None:
    all_hits: list[str] = []
    for rel in _VISUALIZATION_LLM_MODULES:
        path = _REPO_ROOT / rel
        assert path.is_file(), f"missing module: {rel}"
        all_hits.extend(_functions_calling_get_chat_client(path))
    assert all_hits, "expected at least one get_chat_client usage in visualization modules"


def test_visualization_modules_expose_provider_resolution() -> None:
    for rel in _VISUALIZATION_LLM_MODULES:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "resolve_llm_provider" in text, f"{rel} should support provider resolution from repository"
