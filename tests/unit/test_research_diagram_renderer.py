from __future__ import annotations

from pathlib import Path

import pytest

from src.llm.registry import supports_native_image_generation
from src.models.diagrams import DiagramBriefPack, DiagramEvidenceClaim, DiagramStyleGuide, ResearchDiagramBrief
from src.visualization import research_diagram_renderer as renderer


def test_supports_native_image_generation_only_for_google_image_models() -> None:
    assert supports_native_image_generation("google:gemini-3.1-flash-image-preview")
    assert supports_native_image_generation("google-gla:imagen-3.0-generate-002")
    assert not supports_native_image_generation("deepseek:deepseek-v4-flash")
    assert not supports_native_image_generation("google:gemini-2.5-flash")


def _minimal_brief(diagram_id: str) -> ResearchDiagramBrief:
    return ResearchDiagramBrief(
        diagram_id=diagram_id,
        diagram_type="layered_architecture",
        title="Architecture",
        objective="Summarize evidence flow.",
        required_labels=["Input"],
        key_entities=["studies"],
        relationships=["Input -> Output"],
    )


@pytest.mark.asyncio
async def test_render_custom_diagrams_skips_when_drawing_model_unsupported() -> None:
    pack = DiagramBriefPack(
        workflow_id="wf-test",
        source_included_count=3,
        diagrams=[_minimal_brief("diagram-01"), _minimal_brief("diagram-02")],
    )
    report = await renderer.render_custom_research_diagrams(
        brief_pack=pack,
        out_dir=Path("/tmp/unused"),
        drawing_model="deepseek:deepseek-v4-flash",
        critic_model="deepseek:deepseek-v4-pro",
        style_guide=DiagramStyleGuide(),
    )
    assert report.results == []
    assert any("does not support native image generation" in w for w in report.warnings)


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


@pytest.mark.asyncio
async def test_log_usage_cost_persists_row_even_with_zero_tokens() -> None:
    class _Repo:
        def __init__(self) -> None:
            self.rows = []

        async def save_cost_record(self, row):  # type: ignore[no-untyped-def]
            self.rows.append(row)

    repo = _Repo()
    await renderer._log_usage_cost(
        repository=repo,
        workflow_id="wf-0083",
        model="google:gemini-2.5-flash-lite",
        phase="phase_6f_custom_diagram_drawing",
        usage={"tokens_in": 0, "tokens_out": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
        latency_ms=123,
    )
    assert len(repo.rows) == 1
    assert repo.rows[0].phase == "phase_6f_custom_diagram_drawing"
