from __future__ import annotations

from src.utils.logging_paths import create_run_paths, workflow_slug


def test_workflow_slug_sanitizes_and_limits() -> None:
    slug = workflow_slug("How do Conversational AI Tutors impact Learning Outcomes?", max_len=32)
    assert slug.startswith("how-do-conversational-ai-tutors")
    assert len(slug) <= 32


def test_create_run_paths_uses_date_and_12h_format(tmp_path) -> None:
    paths = create_run_paths(str(tmp_path), "Conversational AI Tutors")
    parts = paths.run_dir.parts
    # .../<YYYY-MM-DD>/<workflowSlug>/run_hh-mm-ssAM
    assert len(parts) >= 3
    assert parts[-2] == "conversational-ai-tutors"
    assert parts[-1].startswith("run_")
    assert parts[-1][-2:] in {"AM", "PM"}
    assert paths.run_summary.name == "run_summary.json"
    assert paths.runtime_db.name == "runtime.db"
    assert paths.search_appendix.name == "doc_search_strategies_appendix.md"
    assert paths.protocol_markdown.name == "doc_protocol.md"
    # All paths share the same run_dir
    assert paths.app_log.parent == paths.run_dir
    assert paths.search_appendix.parent == paths.run_dir
