"""Contract: Full-text retrieval and manual PDF ingest stay documented and keep a stable API surface."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "AGENTS.md"
FULLTEXT_INIT = ROOT / "src" / "fulltext" / "__init__.py"
FULLTEXT_RETRIEVAL = ROOT / "src" / "fulltext" / "retrieval.py"
FULLTEXT_INSTITUTIONAL = ROOT / "src" / "fulltext" / "institutional.py"
FULLTEXT_MANUAL = ROOT / "src" / "fulltext" / "manual_ingest.py"
SCOPUS_SESSION = ROOT / "src" / "search" / "scopus_session.py"
PDF_RETRIEVAL = ROOT / "src" / "search" / "pdf_retrieval.py"
REVIEW_PY = ROOT / "scripts" / "review.py"


def _top_level_names(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_fulltext_modules_and_entrypoints_exist() -> None:
    assert FULLTEXT_INIT.is_file()
    assert FULLTEXT_RETRIEVAL.is_file()
    assert FULLTEXT_INSTITUTIONAL.is_file()
    assert FULLTEXT_MANUAL.is_file()
    assert SCOPUS_SESSION.is_file()
    assert PDF_RETRIEVAL.is_file()

    init_names = _top_level_names(FULLTEXT_INIT)
    assert {"FullTextResolveRequest", "FullTextResolver"} <= init_names

    retrieval_names = _top_level_names(FULLTEXT_RETRIEVAL)
    assert {"FullTextResult", "fetch_full_text", "resolve_landing_page"} <= retrieval_names

    institutional_names = _top_level_names(FULLTEXT_INSTITUTIONAL)
    assert {"resolve_sciencedirect_pii", "fetch_sciencedirect_pdf_via_session"} <= institutional_names

    manual_names = _top_level_names(FULLTEXT_MANUAL)
    assert {
        "manual_pdf_directory",
        "find_manual_pdf_path",
        "load_manual_pdf_bytes",
        "reset_manual_index_cache",
    } <= manual_names

    session_names = _top_level_names(SCOPUS_SESSION)
    assert "load_scopus_session_cookie" in session_names

    pdf_retrieval_names = _top_level_names(PDF_RETRIEVAL)
    assert "PDFRetriever" in pdf_retrieval_names

    review_text = REVIEW_PY.read_text(encoding="utf-8")
    assert "--fetch-pdfs" in review_text


def test_agents_md_documents_fulltext_retrieval_and_manual_ingest() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Full-text retrieval and manual PDF ingest" in text
    assert "src/fulltext/__init__.py" in text
    assert "src/fulltext/retrieval.py" in text
    assert "src/fulltext/institutional.py" in text
    assert "src/fulltext/manual_ingest.py" in text
    assert "src/search/scopus_session.py" in text
    assert "src/search/pdf_retrieval.py" in text
    assert "fetch_full_text" in text
    assert "resolve_landing_page" in text
    assert "fetch_sciencedirect_pdf_via_session" in text
    assert "find_manual_pdf_path" in text
    assert "load_manual_pdf_bytes" in text
    assert "FULLTEXT_MANUAL_PDF_DIR" in text
    assert "SCOPUS_SESSION_COOKIE_FILE" in text
    assert "scripts/review.py info" in text
    assert "--fetch-pdfs" in text
