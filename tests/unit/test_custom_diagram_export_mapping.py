from __future__ import annotations

from pathlib import Path

from src.export.markdown_refs import get_existing_figure_entries


def test_custom_diagram_artifacts_are_included_in_figure_entries(tmp_path: Path) -> None:
    manuscript_path = tmp_path / "doc_manuscript.md"
    manuscript_path.write_text("# Title\n", encoding="utf-8")

    fig1 = tmp_path / "fig_custom_01.png"
    fig2 = tmp_path / "fig_custom_02.png"
    fig1.write_bytes(b"png")
    fig2.write_bytes(b"png")

    artifacts = {
        "custom_diagram_01": str(fig1),
        "custom_diagram_02": str(fig2),
    }
    entries = get_existing_figure_entries(manuscript_path, artifacts)
    captions = [caption for caption, _, _ in entries]

    assert any("Custom research architecture" in caption for caption in captions)
    assert any("Custom methodological flow" in caption for caption in captions)
