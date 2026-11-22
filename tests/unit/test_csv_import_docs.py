"""Contract: CSV search import workflow stays documented and keeps a stable API surface."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
API_DOC = ROOT / "docs" / "API.md"
CSV_IMPORT = ROOT / "src" / "search" / "csv_import.py"
SOURCE_INFERENCE = ROOT / "src" / "search" / "source_inference.py"
SEARCH_RUNNER = ROOT / "src" / "orchestration" / "runners" / "search_runner.py"
RUN_LIFECYCLE = ROOT / "src" / "web" / "routers" / "run_lifecycle.py"
REVIEW_CONFIG = ROOT / "src" / "models" / "config.py"


def _top_level_def_names(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_csv_import_modules_and_entrypoints_exist() -> None:
    assert CSV_IMPORT.is_file()
    assert SOURCE_INFERENCE.is_file()
    csv_defs = _top_level_def_names(CSV_IMPORT)
    assert {"validate_csv_file", "parse_masterlist_csv", "parse_supplementary_csvs"} <= csv_defs
    inference_defs = _top_level_def_names(SOURCE_INFERENCE)
    assert {"infer_csv_row_source", "detect_csv_export_format", "resolve_database_column"} <= inference_defs

    runner_text = SEARCH_RUNNER.read_text(encoding="utf-8")
    assert "parse_masterlist_csv" in runner_text
    assert "parse_supplementary_csvs" in runner_text

    router_text = RUN_LIFECYCLE.read_text(encoding="utf-8")
    assert "/api/run-with-masterlist" in router_text
    assert "/api/run-with-supplementary-csv" in router_text

    config_text = REVIEW_CONFIG.read_text(encoding="utf-8")
    assert "masterlist_csv_path" in config_text
    assert "supplementary_csv_paths" in config_text


def test_agents_md_documents_csv_search_import() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## CSV search import" in text
    assert "src/search/csv_import.py" in text
    assert "src/search/source_inference.py" in text
    assert "src/orchestration/runners/search_runner.py" in text
    assert "src/web/routers/run_lifecycle.py" in text
    assert "validate_csv_file" in text
    assert "parse_masterlist_csv" in text
    assert "parse_supplementary_csvs" in text
    assert "masterlist_csv_path" in text
    assert "supplementary_csv_paths" in text
    assert "/api/run-with-masterlist" in text
    assert "/api/run-with-supplementary-csv" in text


def test_api_md_lists_csv_upload_endpoints() -> None:
    text = API_DOC.read_text(encoding="utf-8")
    assert "/api/run-with-masterlist" in text
    assert "/api/run-with-supplementary-csv" in text
