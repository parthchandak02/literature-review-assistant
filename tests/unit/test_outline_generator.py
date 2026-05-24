from __future__ import annotations

import pytest

from src.models import AgentConfig, OutlineNode, SectionOutline, SettingsConfig
from src.writing.context_builder import StudySummary, WritingGroundingData
from src.writing.outline_generator import (
    build_fallback_section_outline,
    generate_section_outline,
)
from src.writing.prompts.outline import fallback_outline_headings


def _settings() -> SettingsConfig:
    return SettingsConfig(agents={"writing": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)})


def _grounding() -> WritingGroundingData:
    return WritingGroundingData(
        databases_searched=["OpenAlex"],
        other_methods_searched=[],
        search_date="2026-04-08",
        total_identified=10,
        duplicates_removed=1,
        total_screened=9,
        fulltext_assessed=3,
        total_included=3,
        fulltext_excluded=0,
        excluded_fulltext_reasons={},
        study_design_counts={"randomized controlled trial": 2, "qualitative": 1},
        total_participants=120,
        year_range="2020-2024",
        meta_analysis_feasible=False,
        synthesis_direction="predominantly_positive",
        n_studies_synthesized=3,
        narrative_text="Most studies reported improved learning outcomes.",
        key_themes=["improved engagement", "better retention"],
        study_summaries=[
            StudySummary(
                paper_id="p1",
                title="AI tutor outcomes in higher education",
                year=2024,
                study_design="randomized controlled trial",
                participant_count=50,
                key_finding="Improved examination performance compared with controls.",
            ),
            StudySummary(
                paper_id="p2",
                title="Adaptive tutoring and retention",
                year=2023,
                study_design="randomized controlled trial",
                participant_count=40,
                key_finding="Improved retention after eight weeks.",
            ),
            StudySummary(
                paper_id="p3",
                title="Learner perceptions of AI tutoring",
                year=2022,
                study_design="qualitative",
                participant_count=30,
                key_finding="Students described higher engagement and clearer feedback.",
            ),
        ],
        valid_citekeys=["Smith2024", "Jones2023", "Lee2022"],
        included_study_citekeys=["Smith2024", "Jones2023", "Lee2022"],
        citekey_title_map={
            "Smith2024": "AI tutor outcomes in higher education",
            "Jones2023": "Adaptive tutoring and retention",
            "Lee2022": "Learner perceptions of AI tutoring",
        },
        fulltext_sought=3,
        fulltext_not_retrieved=0,
    )


def test_fallback_outline_headings_parse_existing_prompt_structure() -> None:
    headings = fallback_outline_headings("discussion")
    assert headings == [
        "Principal Findings",
        "Comparison with Prior Work",
        "Strengths and Limitations",
        "Implications for Practice",
        "Implications for Research",
    ]


@pytest.mark.asyncio
async def test_generate_section_outline_uses_deterministic_fallback_on_llm_failure(monkeypatch) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("outline llm unavailable")

    monkeypatch.setattr(
        "src.writing.outline_generator.PydanticAIClient.complete_validated",
        _boom,
    )

    outline = await generate_section_outline(
        section="discussion",
        settings=_settings(),
        grounding=_grounding(),
        citation_catalog="[Smith2024] Study A",
        provider=None,
        on_llm_call=None,
    )

    assert outline.section_key == "discussion"
    assert [node.heading for node in outline.nodes] == [
        "Principal Findings",
        "Comparison with Prior Work",
        "Strengths and Limitations",
        "Implications for Practice",
        "Implications for Research",
    ]


@pytest.mark.asyncio
async def test_generate_results_outline_merges_authoritative_evidence_nodes(monkeypatch) -> None:
    async def _ok(self, prompt, *, model, temperature, response_model, json_schema=None, max_validation_retries=2):
        _ = (self, prompt, model, temperature, response_model, json_schema, max_validation_retries)
        return (
            SectionOutline(
                section_key="results",
                nodes=[
                    OutlineNode(
                        node_id="risk_of_bias",
                        heading="Risk of Bias Assessment",
                        intent="Summarize appraisal findings.",
                        required_citekeys=[],
                        evidence_chunk_ids=[],
                    )
                ],
            ),
            10,
            20,
            0,
            0,
            0,
        )

    monkeypatch.setattr(
        "src.writing.outline_generator.PydanticAIClient.complete_validated",
        _ok,
    )

    outline = await generate_section_outline(
        section="results",
        settings=_settings(),
        grounding=_grounding(),
        citation_catalog="[Smith2024] Study A\n[Jones2023] Study B\n[Lee2022] Study C",
        provider=None,
        on_llm_call=None,
    )

    headings = [node.heading for node in outline.nodes]
    assert headings[:3] == [
        "Study Selection",
        "Study Characteristics",
        "Synthesis of Findings",
    ]
    assert "Risk of Bias Assessment" in headings
    assert outline.nodes[1].required_citekeys == ["Smith2024", "Jones2023", "Lee2022"]


def test_build_fallback_section_outline_uses_results_citation_budget() -> None:
    outline = build_fallback_section_outline(
        "results",
        _grounding(),
        "[Smith2024] Study A\n[Jones2023] Study B\n[Lee2022] Study C",
    )

    assert outline.section_key == "results"
    assert outline.nodes
    assert any(node.required_citekeys for node in outline.nodes if node.heading != "Study Selection")
