from __future__ import annotations

from src.utils.logging_paths import create_output_paths, create_run_paths, workflow_slug


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


def test_create_output_paths_matches_date_workflow_run(tmp_path) -> None:
    output = create_output_paths(
        output_root=str(tmp_path),
        workflow_description="Conversational AI Tutors",
        run_dir_name="run_03-53-10PM",
        date_folder="2026-02-15",
    )
    assert output.run_dir.parts[-3] == "2026-02-15"
    assert output.run_dir.parts[-2] == "conversational-ai-tutors"
    assert output.run_dir.parts[-1] == "run_03-53-10PM"
    assert output.search_appendix.name == "search_strategies_appendix.md"
    assert output.protocol_markdown.name == "protocol.md"
