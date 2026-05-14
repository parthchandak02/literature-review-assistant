from __future__ import annotations

from src.models.diagrams import DiagramEvidenceClaim, DiagramStyleGuide, ResearchDiagramBrief
from src.visualization import research_diagram_renderer as renderer


def test_extract_inline_image_b64_supports_camel_and_snake_case() -> None:
    payload_camel = {
        "candidates": [{"content": {"parts": [{"inlineData": {"data": "AAA", "mimeType": "image/png"}}]}}]
    }
    payload_snake = {
        "candidates": [{"content": {"parts": [{"inline_data": {"data": "BBB", "mime_type": "image/png"}}]}}]
    }
    assert renderer._extract_inline_image_b64(payload_camel) == "AAA"
    assert renderer._extract_inline_image_b64(payload_snake) == "BBB"


def test_build_generation_prompt_includes_required_constraints() -> None:
    brief = ResearchDiagramBrief(
        diagram_id="diag_1",
        diagram_type="layered_architecture",
        title="Architecture",
        objective="Summarize included-study evidence flow into findings.",
        required_labels=["Input Studies", "Extraction Layer", "Findings"],
        key_entities=["studies", "extraction", "findings"],
        relationships=["Input Studies -> Extraction Layer", "Extraction Layer -> Findings"],
        evidence_claims=[DiagramEvidenceClaim(claim="Claim text", supporting_paper_ids=["p1"])],
    )
    style = DiagramStyleGuide()
    prompt = renderer._build_generation_prompt(brief=brief, style=style, round_index=1, revision_prompt=None)
    assert "Input Studies" in prompt
    assert "black-and-white" not in prompt.lower() or "monochrome" in prompt.lower()
    assert "Uniform line weight" in prompt
