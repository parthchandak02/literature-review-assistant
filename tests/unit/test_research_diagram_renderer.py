from __future__ import annotations

from pathlib import Path

import pytest

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


def test_extract_usage_tokens_reads_usage_metadata() -> None:
    payload = {
        "usageMetadata": {
            "promptTokenCount": 11,
            "candidatesTokenCount": 7,
            "cacheReadTokenCount": 3,
            "cacheWriteTokenCount": 2,
        }
    }
    usage = renderer._extract_usage_tokens(payload)
    assert usage["tokens_in"] == 11
    assert usage["tokens_out"] == 7
    assert usage["cache_read_tokens"] == 3
    assert usage["cache_write_tokens"] == 2


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
        model="google-gla:gemini-2.5-flash-lite",
        phase="phase_6f_custom_diagram_drawing",
        usage={"tokens_in": 0, "tokens_out": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
        latency_ms=123,
    )
    assert len(repo.rows) == 1
    assert repo.rows[0].phase == "phase_6f_custom_diagram_drawing"


def test_read_reference_parts_supports_webp_and_skips_unsupported(tmp_path: Path) -> None:
    webp = tmp_path / "style.webp"
    webp.write_bytes(b"WEBP")
    svg = tmp_path / "style.svg"
    svg.write_text("<svg></svg>", encoding="utf-8")

    parts = renderer._read_reference_parts([str(webp), str(svg), str(tmp_path / "missing.png")])

    assert len(parts) == 1
    assert parts[0]["inline_data"]["mime_type"] == "image/webp"
