from __future__ import annotations

import json
from pathlib import Path

from src.export.ieee_latex import markdown_to_latex
from src.export.markdown_refs import assemble_submission_manuscript, extract_inline_figure_artifact_keys


def test_assemble_submission_manuscript_inlines_custom_diagram_when_anchor_exists(tmp_path: Path) -> None:
    manuscript_path = tmp_path / "doc_manuscript.md"
    fig = tmp_path / "fig_custom_01.png"
    fig.write_bytes(b"png")
    report_path = tmp_path / "data_diagram_generation_report.json"
    report_path.write_text(
        json.dumps(
            {
                "workflow_id": "wf-0083",
                "results": [
                    {
                        "diagram_id": "d01",
                        "artifact_key": "custom_diagram_01",
                        "output_path": str(fig),
                        "chosen_round": 1,
                        "placement": {
                            "diagram_id": "d01",
                            "target_section": "results",
                            "anchor_text": "Primary outcome trends were stable.",
                            "fallback_policy": "append_to_figures_section",
                            "confidence": 0.86,
                            "rationale": "Placed near synthesis claim.",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    body = (
        "## Introduction\nIntro text.\n\n"
        "## Results\nPrimary outcome trends were stable.\nMore text.\n\n"
        "## Discussion\nDiscussion text.\n"
    )
    artifacts = {
        "custom_diagram_01": str(fig),
        "diagram_generation_report": str(report_path),
    }

    out = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=[],
    )
    assert "![Fig. 1:" in out
    assert "## Figures" not in out


def test_assemble_submission_manuscript_falls_back_to_figures_when_section_missing(tmp_path: Path) -> None:
    manuscript_path = tmp_path / "doc_manuscript.md"
    fig = tmp_path / "fig_custom_01.png"
    fig.write_bytes(b"png")
    report_path = tmp_path / "data_diagram_generation_report.json"
    report_path.write_text(
        json.dumps(
            {
                "workflow_id": "wf-0083",
                "results": [
                    {
                        "diagram_id": "d01",
                        "artifact_key": "custom_diagram_01",
                        "output_path": str(fig),
                        "chosen_round": 1,
                        "placement": {
                            "diagram_id": "d01",
                            "target_section": "methods",
                            "anchor_text": "Procedural anchor text.",
                            "fallback_policy": "append_to_figures_section",
                            "confidence": 0.42,
                            "rationale": "Fallback expected because methods section is absent.",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    body = "## Introduction\nOnly intro text.\n\n## Results\nOnly results text.\n"
    artifacts = {
        "custom_diagram_01": str(fig),
        "diagram_generation_report": str(report_path),
    }

    out = assemble_submission_manuscript(
        body=body,
        manuscript_path=manuscript_path,
        artifacts=artifacts,
        citation_rows=[],
    )
    assert "## Figures" in out
    assert "fig_custom_01.png" in out


def test_markdown_to_latex_converts_inline_markdown_image_to_figure_env() -> None:
    md = "# Title\n\n## Abstract\nA short abstract.\n\n## Results\n![Fig. 1: Custom diagram](fig_custom_01.png)\n"
    tex = markdown_to_latex(md, citekeys=set(), figure_paths=[])
    assert "\\includegraphics" in tex
    assert "figures/fig_custom_01" in tex


def test_extract_inline_figure_artifact_keys_uses_inline_markers_only() -> None:
    md = (
        "## Results\n"
        "<!--INLINEFIG:FIGCUSTOM02-->\n"
        "![Fig. 1: inline](fig_custom_02.png)\n\n"
        "## Figures\n"
        "![Fig. 2: fallback](fig_custom_03.png)\n"
    )
    artifacts = {
        "custom_diagram_02": "/tmp/fig_custom_02.png",
        "custom_diagram_03": "/tmp/fig_custom_03.png",
    }
    inline = extract_inline_figure_artifact_keys(md, artifacts)
    assert inline == {"custom_diagram_02"}
