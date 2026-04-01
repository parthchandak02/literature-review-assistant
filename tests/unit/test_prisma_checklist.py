from __future__ import annotations

from src.export.prisma_checklist import (
    render_prisma_csv,
    render_prisma_html,
    render_prisma_markdown_table,
    validate_prisma,
)


def test_validate_prisma_returns_deterministic_items_when_artifacts_missing() -> None:
    result = validate_prisma(tex_content=None, md_content=None)
    assert result.source_state == "artifact_missing"
    assert result.primary_total == 27
    assert len(result.items) >= 40
    assert any(item.item_id == "13e" for item in result.items)


def test_validate_prisma_detects_core_sections() -> None:
    md = (
        "# A systematic review of pharmacy automation\n\n"
        "## Abstract\n\n"
        "Objective: Evaluate outcomes.\n"
        "Methods: We searched PubMed and OpenAlex.\n"
        "Results: We synthesized findings.\n"
        "Conclusions: Implications are discussed.\n\n"
        "## Introduction\n\n"
        "Background and rationale identify an evidence gap.\n\n"
        "## Methods\n\n"
        "Eligibility criteria included PICO and study design.\n"
        "Selection used independent dual screening with adjudication.\n"
        "Data extraction and risk of bias were assessed with ROBINS-I.\n"
        "Meta-analysis model and heterogeneity (I2) were planned.\n\n"
        "## Results\n\n"
        "PRISMA flow reported identified, screened, and included studies.\n"
        "Study characteristics and certainty using GRADE were reported.\n\n"
        "## Discussion\n\n"
        "Limitations, interpretation, and implications for policy were discussed.\n\n"
        "## Other Information\n\n"
        "Registration: PROSPERO CRD42000.\n"
        "Funding and conflict of interest declarations were provided.\n"
    )
    result = validate_prisma(tex_content=None, md_content=md)
    assert result.source_state == "validated_md"
    assert result.reported_count >= 8
    assert any(item.item_id == "1" and item.status == "REPORTED" for item in result.items)
    assert any(item.item_id == "24a" and item.status != "MISSING" for item in result.items)


def test_prisma_renderers_emit_non_empty_structured_outputs() -> None:
    result = validate_prisma(
        tex_content=None,
        md_content="# Systematic review\n\n## Methods\n\nSearch strategy and eligibility criteria.",
    )
    md_table = render_prisma_markdown_table(result)
    csv_text = render_prisma_csv(result)
    assert "PRISMA 2020 checklist validation" in md_table
    assert "| Item | Section | Status |" in md_table
    assert "item_id,section,status,applies,description,rationale,evidence_terms" in csv_text


def test_prisma_html_renderer_includes_color_badges() -> None:
    result = validate_prisma(
        tex_content=None,
        md_content="# Systematic review\n\n## Methods\n\nSearch strategy, eligibility criteria, and risk of bias.",
    )
    html = render_prisma_html(result)
    assert "<!doctype html>" in html.lower()
    assert "badge reported" in html or "badge partial" in html or "badge missing" in html
    assert "PRISMA 2020 Checklist Validation" in html
