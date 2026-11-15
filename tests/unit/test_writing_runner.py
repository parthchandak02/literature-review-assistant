"""Unit tests for Phase 6 writing runner and sub-phases.

Covers `src/orchestration/runners/writing_runner.py` and its sub-modules:
- `setup.py`: narrative DB/JSON loading, rewind section invalidation, zero-papers
  fast path, figure map & fulltext ID discovery, citation registration.
- `rag_retrieval.py`: parallel HyDE generation with error isolation, RAG retrieval
  success (HyDE + rerank), empty-policy warn vs block, error diagnostics, skipped path.
- `section_loop.py`: persisted outline reuse vs timeout fallback, completed-section
  resume skip, Phase A -> Phase B prior context passing, failed-section sequential
  retry & placeholder recovery, humanizer citation/numeric drift reversion, RAG
  health threshold failure.
- `post_assembly.py`: section heading sanitization, DB-first vs rewound assembly,
  programmatic citation coverage patching into Results DB drafts, contradiction
  injection, manuscript asset & assembly persistence, non-fatal diagram failure handling.
- `writing_runner.py`: end-to-end orchestration, zero-papers path, writing persistence
  invariant failure, and writing manifest / fallback event recording.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_graph import GraphRunContext

from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import (
    CandidatePaper,
    CitationEntryRecord,
    DomainExpertConfig,
    ExtractionRecord,
    OutlineNode,
    ReviewConfig,
    SectionBlock,
    SectionDraft,
    SectionOutline,
    SectionWriteResult,
    SettingsConfig,
    SourceCategory,
    StructuredSectionDraft,
    StudyDesign,
)
from src.models.additional import PRISMACounts
from src.models.config import (
    AgentConfig,
    GatesConfig,
    IEEEExportConfig,
    RagConfig,
    WritingConfig,
)
from src.models.diagrams import (
    DiagramBriefPack,
    DiagramGenerationReport,
    DiagramPlacementPlan,
    ResearchDiagramBrief,
)
from src.models.workflow import StepStatus
from src.orchestration.runners.writing.post_assembly import (
    _sanitize_section_body_for_assembly,
    run_post_assembly,
)
from src.orchestration.runners.writing.rag_retrieval import (
    RagResult,
    generate_hyde_documents,
    retrieve_rag_for_section,
)
from src.orchestration.runners.writing.section_loop import (
    SectionLoopResult,
    run_section_writing_loop,
)
from src.orchestration.runners.writing.setup import load_narrative, run_writing_setup
from src.orchestration.runners.writing_runner import run_writing_node
from src.orchestration.state import ReviewState
from src.rag.retriever import RetrievedChunk
from src.synthesis.contradiction_detector import ContradictionFlag
from src.synthesis.feasibility import SynthesisFeasibility
from src.synthesis.narrative import NarrativeSynthesis
from src.writing.context_builder import build_writing_grounding
from src.writing.prompts.sections import SECTIONS

_WORKFLOW_ID = "wf-writing-runner-test"


@pytest.fixture(autouse=True)
def _no_rate_limit_sleep():
    """Avoid real RPM sleeps in RateLimiter during unit tests."""
    with patch("src.llm.rate_limiter.RateLimiter.acquire", new=AsyncMock()):
        yield


def _build_review() -> ReviewConfig:
    return ReviewConfig(
        research_question="How effective are digital reminders on medication adherence in primary care?",
        review_type="systematic",
        pico={
            "population": "Adult primary care patients prescribed chronic medications",
            "intervention": "digital reminder",
            "comparison": "Usual care without digital reminders",
            "outcome": "Medication adherence proportion",
        },
        keywords=["digital reminder", "medication adherence", "primary care"],
        domain="clinical informatics",
        scope="Primary care outpatient medication adherence interventions.",
        domain_expert=DomainExpertConfig(
            domain_summary="Evaluates digital medication reminder tools in outpatient primary care.",
            canonical_terms=["digital reminder", "medication adherence"],
        ),
        inclusion_criteria=["Empirical human studies reporting medication adherence outcomes"],
        exclusion_criteria=["Editorials and opinion pieces"],
        date_range_start=2018,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _build_settings(
    *,
    humanization: bool = False,
    ratchet_outline_enabled: bool = True,
    use_hyde: bool = False,
    rerank: bool = False,
    rag_empty_policy: str = "warn",
    block_writing_on_rag_failure: bool = False,
    max_empty_sections: int = 2,
) -> SettingsConfig:
    return SettingsConfig(
        agents={
            "writing": AgentConfig(model="google:gemini-2.5-pro", temperature=0.2),
            "humanizer": AgentConfig(model="google:gemini-2.5-flash", temperature=0.2),
            "abstract_generation": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "contradiction_resolver": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "concept_diagrams": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "research_diagram_preparer": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "research_diagram_placement": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "research_diagram_drawing": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
            "research_diagram_critic": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1),
        },
        gates=GatesConfig(profile="warning"),
        ieee_export=IEEEExportConfig(max_abstract_words=250),
        writing=WritingConfig(
            humanization=humanization,
            humanization_iterations=1,
            ratchet_outline_enabled=ratchet_outline_enabled,
            writing_concurrency=2,
            abstract_trim_floor_words=100,
        ),
        rag=RagConfig(
            embed_model="gemini-embedding-001",
            embed_dim=768,
            use_hyde=use_hyde,
            hyde_model="google:gemini-2.5-flash-lite",
            rerank=rerank,
            reranker_model="google:gemini-2.5-flash-lite",
            candidate_k=10,
            final_k=4,
            min_chunks_per_section=1,
            max_empty_sections=max_empty_sections,
            block_writing_on_rag_failure=block_writing_on_rag_failure,
            rag_empty_policy=rag_empty_policy,
        ),
    )


def _make_paper(paper_id: str, *, authors: list[str] | None = None, year: int = 2024) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Digital reminder trial {paper_id}",
        authors=authors or ["Smith, J."],
        year=year,
        source_database="openalex",
        source_category=SourceCategory.DATABASE,
        doi=f"10.1000/{paper_id}",
        abstract="Randomized primary care trial evaluating digital reminders for medication adherence.",
    )


def _make_extraction(paper_id: str, *, summary: str = "Improved adherence significantly.") -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.RCT,
        intervention_description="Daily SMS digital reminder",
        participant_demographics="Adults in primary care",
        outcomes=[],
        results_summary={"summary": summary},
    )


def _valid_abstract_markdown() -> str:
    return (
        "**Background:** Medication non-adherence in chronic primary care degrades long-term clinical outcomes, increases preventable hospitalizations, and raises health system costs across diverse outpatient populations worldwide.\n"
        "**Objectives:** This systematic review evaluates how automated digital medication reminders affect adherence proportions compared with usual care in adult primary care patients.\n"
        "**Methods:** Structured searches were conducted in OpenAlex for empirical human studies published between 2018 and 2026 evaluating automated digital reminders against routine outpatient care without electronic prompts.\n"
        "**Results:** Included randomized controlled trials demonstrated consistent, clinically meaningful improvements in medication adherence proportion with automated digital reminders over routine outpatient follow-up, although intervention delivery frequency, behavioral framing, and follow-up duration varied moderately across primary care clinical sites.\n"
        "**Conclusions:** Automated digital reminders provide a practical, low-cost, and scalable adjunct for improving chronic medication adherence in routine primary care settings.\n"
        "**Keywords:** digital reminders, medication adherence, primary care, systematic review."
    )


def _section_write_result(
    section: str,
    content: str | None = None,
    *,
    fallback_used: bool = False,
    validation_issues: list[str] | None = None,
    validation_retries: int = 0,
) -> SectionWriteResult:
    if content is None:
        if section == "abstract":
            content = _valid_abstract_markdown()
        elif section == "results":
            content = "### Study Characteristics\n\nIncluded trial [Smith2024] improved adherence.\n\n### Risk of Bias\n\nLow risk overall [Smith2024]."
        else:
            content = f"Substantive {section} prose citing [Smith2024]."
    return SectionWriteResult(
        section_key=section,
        content_markdown=content,
        structured_draft=StructuredSectionDraft(
            section_key=section,
            blocks=[SectionBlock(block_type="paragraph", text=content, citations=["Smith2024"])],
            cited_keys=["Smith2024"],
        ),
        cited_keys=["Smith2024"],
        word_count=len(content.split()),
        validation_retries=validation_retries,
        validation_issues=validation_issues or [],
        fallback_used=fallback_used,
    )


async def _init_state(
    tmp_path: Path,
    *,
    workflow_id: str = _WORKFLOW_ID,
    papers: list[CandidatePaper] | None = None,
    settings: SettingsConfig | None = None,
    next_phase: str = "phase_6_writing",
    with_rc: bool = True,
) -> ReviewState:
    run_root = tmp_path / "runs"
    run_dir = run_root / "2026-11-15" / workflow_id / "run_01"
    run_dir.mkdir(parents=True, exist_ok=True)
    papers_dir = run_dir / "papers"
    papers_dir.mkdir(exist_ok=True)
    db_path = run_dir / "runtime.db"

    review = _build_review()
    cfg = settings or _build_settings()
    paper_list = papers if papers is not None else [_make_paper("p-1")]

    async with get_db(str(db_path)) as db:
        repo = WorkflowRepository(db)
        await repo.create_workflow(workflow_id, review.research_question, "cfg-hash-1")
        for p in paper_list:
            await repo.save_paper(p)

    rc = None
    if with_rc:
        rc = MagicMock()
        rc.verbose = False
        rc.debug = False
        rc.offline = True

    return ReviewState(
        review_path=str(run_dir / "review.yaml"),
        settings_path=str(run_dir / "settings.yaml"),
        run_root=str(run_root),
        run_context=rc,
        run_id="20261115-061500",
        workflow_id=workflow_id,
        review=review,
        settings=cfg,
        db_path=str(db_path),
        log_dir=str(run_dir),
        output_dir=str(run_dir),
        dedup_count=max(1, len(paper_list)),
        deduped_papers=list(paper_list),
        included_papers=list(paper_list),
        extraction_records=[_make_extraction(p.paper_id) for p in paper_list],
        next_phase=next_phase,
        artifacts={
            "manuscript_md": str(run_dir / "doc_manuscript.md"),
            "narrative_synthesis": str(run_dir / "narrative_synthesis.json"),
            "prisma_diagram": str(run_dir / "fig_prisma_flow.png"),
            "timeline": str(run_dir / "fig_timeline.png"),
            "geographic": str(run_dir / "fig_geographic.png"),
            "papers_dir": str(papers_dir),
            "papers_manifest": str(run_dir / "papers_manifest.json"),
            "concept_taxonomy": str(run_dir / "fig_concept_taxonomy.svg"),
            "conceptual_framework": str(run_dir / "fig_conceptual_framework.svg"),
            "methodology_flow": str(run_dir / "fig_methodology_flow.svg"),
            "diagram_brief_pack": str(run_dir / "diagram_brief_pack.json"),
            "diagram_placement_plan": str(run_dir / "diagram_placement_plan.json"),
            "diagram_generation_report": str(run_dir / "diagram_generation_report.json"),
        },
    )


def _ctx(state: ReviewState) -> GraphRunContext[ReviewState]:
    return GraphRunContext(state=state, deps=None)


# ---------------------------------------------------------------------------
# setup.py: load_narrative & run_writing_setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_narrative_merges_meta_analysis_and_falls_back_to_json(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    narr_path = Path(state.artifacts["narrative_synthesis"])
    narr_path.write_text(
        json.dumps({"meta_analysis": {"pooled_effect": 0.42, "n_studies": 3}}),
        encoding="utf-8",
    )

    feas = SynthesisFeasibility(feasible=True, groupings=["adherence"], rationale="Compatible trials.")
    narr = NarrativeSynthesis(
        outcome_name="adherence",
        n_studies=1,
        effect_direction_summary="predominantly_positive",
        key_themes=["SMS reminders"],
        synthesis_table=[],
        narrative_text="Narrative summary.",
    )
    async with get_db(state.db_path) as db:
        await WorkflowRepository(db).save_synthesis_result(state.workflow_id, feas, narr)

    loaded = await load_narrative(state)
    assert loaded is not None
    assert loaded["feasibility"]["feasible"] is True
    assert loaded["narrative"]["key_themes"] == ["SMS reminders"]
    assert loaded["meta_analysis"] == {"pooled_effect": 0.42, "n_studies": 3}

    # Without DB synthesis, falls back to JSON file; corrupt JSON returns None.
    state_json = await _init_state(tmp_path, workflow_id="wf-narr-json")
    json_only = Path(state_json.artifacts["narrative_synthesis"])
    json_only.write_text(json.dumps({"narrative": {"n_studies": 2}}), encoding="utf-8")
    assert await load_narrative(state_json) == {"narrative": {"n_studies": 2}}

    json_only.write_text("{corrupt-json", encoding="utf-8")
    assert await load_narrative(state_json) is None


@pytest.mark.asyncio
async def test_writing_setup_rewind_ignores_completed_sections_and_builds_artifacts_maps(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, next_phase="phase_4_extraction_quality")
    # Create one figure file and one non-empty + one empty fulltext file.
    Path(state.artifacts["prisma_diagram"]).write_bytes(b"png-bytes")
    papers_dir = Path(state.artifacts["papers_dir"])
    (papers_dir / "p-1.pdf").write_bytes(b"%PDF-1.4 content")
    (papers_dir / "p-empty.pdf").write_bytes(b"")

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        await repo.save_section_draft(
            SectionDraft(
                workflow_id=state.workflow_id,
                section="abstract",
                version=1,
                content="Stale abstract draft",
                word_count=3,
            )
        )
        # Insert a placeholder GRADE row that setup must purge.
        await db.execute(
            """
            INSERT INTO grade_assessments (
                workflow_id, outcome_name, assessment_data, final_certainty
            ) VALUES (?, 'primary_outcome', '{}', 'very_low')
            """,
            (state.workflow_id,),
        )
        await db.commit()

        save_ckpt = AsyncMock()
        save_sub = AsyncMock()
        with (
            patch("src.orchestration.runners.writing.setup.render_prisma_diagram"),
            patch("src.orchestration.runners.writing.setup.render_timeline"),
            patch("src.orchestration.runners.writing.setup.render_geographic"),
            patch(
                "src.orchestration.runners.writing.setup.register_background_sr_citations",
                new=AsyncMock(return_value=["PriorSR2022"]),
            ),
        ):
            res = await run_writing_setup(
                state,
                repository=repo,
                db=db,
                citation_repo=CitationRepository(db),
                narrative=None,
                rc=state.run_context,
                save_writing_checkpoint=save_ckpt,
                save_subphase_checkpoint=save_sub,
            )

        grade_rows = await repo.load_grade_assessments(state.workflow_id)
        citekeys = await CitationRepository(db).get_citekeys()

    assert res["rewound_before_writing"] is True
    assert res["completed"] == set()
    assert res["sections_written_zero"] is None
    assert res["bg_citekeys"] == ["PriorSR2022"]
    assert res["grounding"].fulltext_retrieved_count == 1
    assert grade_rows == []
    assert any("Smith" in ck for ck in citekeys)
    save_ckpt.assert_awaited_once_with(papers_processed=0, status="partial")

    # Resuming directly at phase_6_writing preserves completed sections.
    state.next_phase = "phase_6_writing"
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        with (
            patch("src.orchestration.runners.writing.setup.render_prisma_diagram"),
            patch("src.orchestration.runners.writing.setup.render_timeline"),
            patch("src.orchestration.runners.writing.setup.render_geographic"),
            patch(
                "src.orchestration.runners.writing.setup.register_background_sr_citations",
                new=AsyncMock(return_value=[]),
            ),
        ):
            res_resume = await run_writing_setup(
                state,
                repository=repo,
                db=db,
                citation_repo=CitationRepository(db),
                narrative=None,
                rc=None,
                save_writing_checkpoint=AsyncMock(),
                save_subphase_checkpoint=AsyncMock(),
            )
    assert res_resume["rewound_before_writing"] is False
    assert "abstract" in res_resume["completed"]


# ---------------------------------------------------------------------------
# rag_retrieval.py: generate_hyde_documents & retrieve_rag_for_section
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_hyde_documents_isolates_per_section_errors(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)

    async def _fake_hyde(*, section: str, **_kw) -> str:
        if section == "methods":
            raise RuntimeError("hyde rate limit")
        return f"Hypothetical excerpt for {section}"

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        with patch("src.orchestration.runners.writing.rag_retrieval.generate_hyde_document", side_effect=_fake_hyde):
            docs = await generate_hyde_documents(
                state,
                hyde_model="google:gemini-2.5-flash-lite",
                pico_cfg=state.review.pico if state.review else None,
                repository=repo,
                rc=state.run_context,
            )

    assert "methods" not in docs
    assert len(docs) == len(SECTIONS) - 1
    assert docs["results"] == "Hypothetical excerpt for results"


@pytest.mark.asyncio
async def test_retrieve_rag_for_section_success_empty_error_and_skipped(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    chunks = [
        RetrievedChunk(chunk_id="c-1", paper_id="p-1", chunk_index=0, content="Adherence rose 18%.", score=0.91),
        RetrievedChunk(chunk_id="c-2", paper_id="p-1", chunk_index=1, content="Control arm steady.", score=0.75),
    ]
    retriever = MagicMock()
    retriever.search = AsyncMock(return_value=chunks)
    rerank_mock = AsyncMock(return_value=[chunks[0]])

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)

        # 1. Success with HyDE + rerank
        with (
            patch(
                "src.orchestration.runners.writing.rag_retrieval.rag_embed_query",
                new=AsyncMock(return_value=[0.1, 0.2]),
            ),
            patch("src.orchestration.runners.writing.rag_retrieval.rerank_chunks", new=rerank_mock),
        ):
            res_ok = await retrieve_rag_for_section(
                "results",
                state=state,
                repository=repo,
                retriever=retriever,
                chunk_count=2,
                hyde_docs={"results": "Hypothetical results"},
                embed_model="gemini-embedding-001",
                embed_dim=768,
                use_rerank=True,
                reranker_model="google:gemini-2.5-flash-lite",
                candidate_k=10,
                final_k=4,
                min_chunks_per_section=1,
                rag_empty_policy="warn",
                paper_citation_meta={"p-1": {"citekey": "Smith2024", "year": "2024", "title": "Trial A"}},
                pico_cfg=state.review.pico if state.review else None,
                rc=state.run_context,
            )
        assert res_ok.status == "success"
        assert res_ok.query_type == "hyde"
        assert res_ok.retrieved_count == 1
        assert "Smith2024" in res_ok.context
        rerank_mock.assert_awaited_once()

        # 2. Empty retrieval under warn policy -> logs diagnostic + fallback event
        retriever.search = AsyncMock(return_value=[])
        with patch(
            "src.orchestration.runners.writing.rag_retrieval.rag_embed_query",
            new=AsyncMock(return_value=[0.1, 0.2]),
        ):
            res_empty = await retrieve_rag_for_section(
                "introduction",
                state=state,
                repository=repo,
                retriever=retriever,
                chunk_count=2,
                hyde_docs={},
                embed_model="gemini-embedding-001",
                embed_dim=768,
                use_rerank=False,
                reranker_model="",
                candidate_k=10,
                final_k=4,
                min_chunks_per_section=1,
                rag_empty_policy="warn",
                paper_citation_meta={},
                pico_cfg=None,
                rc=state.run_context,
            )
        assert res_empty.status == "empty"
        assert res_empty.query_type == "section_fallback"

        # 3. Empty retrieval under block policy -> raises RuntimeError
        with patch(
            "src.orchestration.runners.writing.rag_retrieval.rag_embed_query",
            new=AsyncMock(return_value=[0.1, 0.2]),
        ):
            with pytest.raises(RuntimeError, match="rag_empty_policy=block"):
                await retrieve_rag_for_section(
                    "methods",
                    state=state,
                    repository=repo,
                    retriever=retriever,
                    chunk_count=2,
                    hyde_docs={},
                    embed_model="gemini-embedding-001",
                    embed_dim=768,
                    use_rerank=False,
                    reranker_model="",
                    candidate_k=10,
                    final_k=4,
                    min_chunks_per_section=1,
                    rag_empty_policy="block",
                    paper_citation_meta={},
                    pico_cfg=None,
                    rc=None,
                )

        # 4. Embedder exception -> caught, status="error", diagnostic + fallback persisted
        with patch(
            "src.orchestration.runners.writing.rag_retrieval.rag_embed_query",
            new=AsyncMock(side_effect=RuntimeError("embed failed")),
        ):
            res_err = await retrieve_rag_for_section(
                "discussion",
                state=state,
                repository=repo,
                retriever=retriever,
                chunk_count=2,
                hyde_docs={},
                embed_model="gemini-embedding-001",
                embed_dim=768,
                use_rerank=False,
                reranker_model="",
                candidate_k=10,
                final_k=4,
                min_chunks_per_section=1,
                rag_empty_policy="warn",
                paper_citation_meta={},
                pico_cfg=None,
                rc=state.run_context,
            )
        assert res_err.status == "error"
        assert "embed failed" in (res_err.error or "")

        # 5. Zero chunks -> skipped
        res_skip = await retrieve_rag_for_section(
            "conclusion",
            state=state,
            repository=repo,
            retriever=retriever,
            chunk_count=0,
            hyde_docs={},
            embed_model="gemini-embedding-001",
            embed_dim=768,
            use_rerank=False,
            reranker_model="",
            candidate_k=10,
            final_k=4,
            min_chunks_per_section=1,
            rag_empty_policy="warn",
            paper_citation_meta={},
            pico_cfg=None,
            rc=None,
        )
        assert res_skip.status == "skipped"

        diags = await repo.get_rag_retrieval_diagnostics(state.workflow_id)
        fb_summary = await repo.get_fallback_event_summary(state.workflow_id)

    assert {(d.section, d.status) for d in diags} == {
        ("results", "success"),
        ("introduction", "empty"),
        ("methods", "empty"),
        ("discussion", "error"),
        ("conclusion", "skipped"),
    }
    fb_types = {row["fallback_type"] for row in fb_summary}
    assert {"empty_retrieval_context", "rag_retrieval_error"} <= fb_types


# ---------------------------------------------------------------------------
# section_loop.py: outlines, resume skip, retries, humanizer guardrails, RAG health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_section_loop_reuses_outlines_skips_completed_and_retries_failed_section(tmp_path: Path) -> None:
    state = await _init_state(tmp_path)
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        citation_repo = CitationRepository(db)
        # Pre-seed all 6 outlines + phase_6a2_outline checkpoint so loop reuses them.
        for sec in SECTIONS:
            await repo.save_section_outline(
                state.workflow_id,
                SectionOutline(
                    section_key=sec,
                    nodes=[OutlineNode(node_id=f"{sec}-1", heading="Overview", intent="Summarize")],
                ),
                generation=1,
            )
        await repo.save_checkpoint(state.workflow_id, "phase_6a2_outline", papers_processed=len(SECTIONS))
        # Pre-seed completed introduction draft.
        await repo.save_section_artifacts_from_draft(
            SectionDraft(
                workflow_id=state.workflow_id,
                section="introduction",
                version=1,
                content="Persisted introduction prose [Smith2024].",
                word_count=4,
            ),
            section_order=1,
        )

        attempts: dict[str, int] = {}
        captured_prior_ctx: dict[str, str] = {}

        async def _fake_write(*, section: str, prior_sections_context: str = "", **_kw) -> SectionWriteResult:
            attempts[section] = attempts.get(section, 0) + 1
            captured_prior_ctx[section] = prior_sections_context
            if section == "discussion" and attempts[section] == 1:
                raise RuntimeError("transient LLM error")
            return _section_write_result(section)

        grounding = MagicMock()
        provider = MagicMock()
        with (
            patch("src.orchestration.runners.writing.section_loop.generate_section_outline") as mock_outline,
            patch(
                "src.orchestration.runners.writing.section_loop.retrieve_rag_for_section",
                new=AsyncMock(return_value=RagResult(status="success", context="RAG ctx")),
            ),
            patch(
                "src.orchestration.runners.writing.section_loop.write_section_with_validation", side_effect=_fake_write
            ),
        ):
            loop_res = await run_section_writing_loop(
                state,
                repository=repo,
                db=db,
                citation_repo=citation_repo,
                provider=provider,
                grounding=grounding,
                citation_catalog="[Smith2024] Digital reminder trial (2024)",
                completed={"introduction"},
                prisma_counts=None,
                rc=state.run_context,
                save_writing_checkpoint=AsyncMock(),
                save_subphase_checkpoint=AsyncMock(),
            )

        persisted = await repo.get_completed_sections(state.workflow_id)

    mock_outline.assert_not_called()
    assert "introduction" not in attempts
    assert attempts["discussion"] == 2
    assert "RESULTS SUMMARY" in captured_prior_ctx["discussion"]
    assert "RESULTS SUMMARY" in captured_prior_ctx["conclusion"]
    assert loop_res.failed_sections == []
    assert loop_res.sections_written[SECTIONS.index("introduction")] == "Persisted introduction prose [Smith2024]."
    assert persisted == set(SECTIONS)
    # 5 non-skipped sections + 1 retry for discussion = 6 RAG calls
    assert state.rag_sections_success == len(SECTIONS)


@pytest.mark.asyncio
async def test_section_loop_outline_timeout_fallback_and_empty_abstract_placeholder(tmp_path: Path) -> None:
    settings = _build_settings(ratchet_outline_enabled=True)
    state = await _init_state(tmp_path, settings=settings)

    async def _fake_write(*, section: str, **_kw) -> SectionWriteResult:
        if section == "abstract":
            return _section_write_result("abstract", content="   ")
        return _section_write_result(section)

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        citation_repo = CitationRepository(db)
        grounding = build_writing_grounding(
            prisma_counts=PRISMACounts(
                databases_records={"openalex": 10},
                other_sources_records={},
                total_identified_databases=10,
                total_identified_other=0,
                duplicates_removed=2,
                records_screened=8,
                records_excluded_screening=6,
                reports_sought=2,
                reports_not_retrieved=0,
                reports_assessed=2,
                reports_excluded_with_reasons={},
                studies_included_qualitative=0,
                studies_included_quantitative=1,
                arithmetic_valid=True,
                records_after_deduplication=8,
                total_included=1,
            ),
            extraction_records=state.extraction_records,
            included_papers=state.included_papers,
            narrative=None,
            citation_catalog="[Smith2024] Digital reminder trial (2024)",
            review_config=state.review,
        )
        with (
            patch(
                "src.orchestration.runners.writing.section_loop.generate_section_outline",
                new=AsyncMock(side_effect=TimeoutError("outline timed out")),
            ),
            patch(
                "src.orchestration.runners.writing.section_loop.retrieve_rag_for_section",
                new=AsyncMock(return_value=RagResult(status="skipped")),
            ),
            patch(
                "src.orchestration.runners.writing.section_loop.write_section_with_validation", side_effect=_fake_write
            ),
        ):
            loop_res = await run_section_writing_loop(
                state,
                repository=repo,
                db=db,
                citation_repo=citation_repo,
                provider=MagicMock(),
                grounding=grounding,
                citation_catalog="[Smith2024] Digital reminder trial (2024)",
                completed=set(),
                prisma_counts=None,
                rc=state.run_context,
                save_writing_checkpoint=AsyncMock(),
                save_subphase_checkpoint=AsyncMock(),
            )
        saved_outlines = await repo.load_section_outlines(state.workflow_id, generation=1)

    assert len(saved_outlines) == len(SECTIONS)
    assert "abstract" in loop_res.placeholder_sections
    assert "**Background:**" in loop_res.sections_written[SECTIONS.index("abstract")]


@pytest.mark.asyncio
async def test_section_loop_humanizer_reverts_on_citation_or_numeric_drift(tmp_path: Path) -> None:
    settings = _build_settings(humanization=True, ratchet_outline_enabled=False)
    state = await _init_state(tmp_path, settings=settings, with_rc=False)
    # Mark rc=None so use_llm_write follows _llm_available; mock _llm_available=True.

    async def _fake_write(*, section: str, **_kw) -> SectionWriteResult:
        if section == "results":
            return _section_write_result("results", content="Adherence improved by 15% in 2024 [Smith2024].")
        return _section_write_result(section)

    async def _fake_humanize(text: str, *, section: str, **_kw) -> str:
        if section == "results":
            # Drops [Smith2024] and alters 15% -> 20%, triggering drift reversion.
            return "Adherence improved by 20% in 2024."
        if section == "discussion":
            # Hallucinates an unknown citekey while keeping blocks/numbers unchanged? Let's test citation block mismatch.
            return text + " [Invented2099]"
        return text

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        provider = MagicMock()
        provider.reserve_call_slot = AsyncMock()
        with (
            patch("src.orchestration.runners.writing.section_loop._llm_available", return_value=True),
            patch(
                "src.orchestration.runners.writing.section_loop.retrieve_rag_for_section",
                new=AsyncMock(return_value=RagResult(status="skipped")),
            ),
            patch(
                "src.orchestration.runners.writing.section_loop.write_section_with_validation", side_effect=_fake_write
            ),
            patch("src.orchestration.runners.writing.section_loop.humanize_async", side_effect=_fake_humanize),
        ):
            loop_res = await run_section_writing_loop(
                state,
                repository=repo,
                db=db,
                citation_repo=CitationRepository(db),
                provider=provider,
                grounding=MagicMock(),
                citation_catalog="[Smith2024] Digital reminder trial (2024)",
                completed=set(),
                prisma_counts=None,
                rc=None,
                save_writing_checkpoint=AsyncMock(),
                save_subphase_checkpoint=AsyncMock(),
            )

    assert "15%" in loop_res.sections_written[SECTIONS.index("results")]
    assert "[Smith2024]" in loop_res.sections_written[SECTIONS.index("results")]
    assert "[Invented2099]" not in loop_res.sections_written[SECTIONS.index("discussion")]


@pytest.mark.asyncio
async def test_section_loop_raises_when_rag_threshold_breached_in_blocking_mode(tmp_path: Path) -> None:
    settings = _build_settings(
        ratchet_outline_enabled=False,
        block_writing_on_rag_failure=True,
        max_empty_sections=1,
    )
    state = await _init_state(tmp_path, settings=settings)

    async with get_db(state.db_path) as db:
        with (
            patch(
                "src.orchestration.runners.writing.section_loop.retrieve_rag_for_section",
                new=AsyncMock(return_value=RagResult(status="empty")),
            ),
            patch(
                "src.orchestration.runners.writing.section_loop.write_section_with_validation",
                side_effect=lambda *, section, **_kw: _section_write_result(section),
            ),
        ):
            with pytest.raises(RuntimeError, match="strict_mode=True"):
                await run_section_writing_loop(
                    state,
                    repository=WorkflowRepository(db),
                    db=db,
                    citation_repo=CitationRepository(db),
                    provider=MagicMock(),
                    grounding=MagicMock(),
                    citation_catalog="[Smith2024] Digital reminder trial (2024)",
                    completed=set(),
                    prisma_counts=None,
                    rc=state.run_context,
                    save_writing_checkpoint=AsyncMock(),
                    save_subphase_checkpoint=AsyncMock(),
                )
    assert state.rag_threshold_breached is True
    assert state.rag_sections_empty == len(SECTIONS)


# ---------------------------------------------------------------------------
# post_assembly.py: sanitization, DB-first vs rewind, coverage patch, contradictions, assets
# ---------------------------------------------------------------------------


def test_sanitize_section_body_for_assembly_strips_heading_and_leaked_h2() -> None:
    raw = "## Results\n\nPrimary finding prose.\n\n## Discussion\n\nLeaked discussion."
    cleaned = _sanitize_section_body_for_assembly("results", raw)
    assert cleaned == "Primary finding prose."


@pytest.mark.asyncio
async def test_post_assembly_coverage_patch_contradictions_assets_and_nonfatal_diagrams(tmp_path: Path) -> None:
    p1 = _make_paper("p-1", authors=["Smith, J."])
    p2 = _make_paper("p-2", authors=["Doe, A."])
    state = await _init_state(tmp_path, papers=[p1, p2])

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        c_repo = CitationRepository(db)
        await c_repo.ensure_schema()
        await c_repo.register_citation(
            CitationEntryRecord(
                citekey="Smith2024",
                doi=p1.doi,
                title=p1.title,
                authors=p1.authors,
                year=2024,
                journal="J Med",
                paper_id="p-1",
                resolved=True,
            )
        )
        await c_repo.register_citation(
            CitationEntryRecord(
                citekey="Doe2024",
                doi=p2.doi,
                title=p2.title,
                authors=p2.authors,
                year=2024,
                journal="J Med",
                paper_id="p-2",
                resolved=True,
            )
        )
        # Seed contiguous section_drafts + manuscript_sections so DB assembly & manifest validation work.
        section_texts = {
            "abstract": _valid_abstract_markdown(),
            "introduction": "Intro citing [INTERVENTION] and [Smith2024].",
            "methods": "Methods prose [Smith2024].",
            "results": "### Study Characteristics\n\nTrial [Smith2024] reported benefit.\n\n### Risk of Bias\n\nLow risk.",
            "discussion": "Discussion first paragraph.\n\nDiscussion second paragraph.",
            "conclusion": "Conclusion prose.",
        }
        for idx, sec in enumerate(SECTIONS):
            await repo.save_section_artifacts_from_draft(
                SectionDraft(
                    workflow_id=state.workflow_id,
                    section=sec,
                    version=1,
                    content=section_texts[sec],
                    word_count=len(section_texts[sec].split()),
                ),
                section_order=idx,
            )

    def _fake_assemble(*, body: str, **_kw) -> str:
        # Return markdown containing recognizable asset sections + injected body.
        return (
            body
            + "\n\n_Table 1. Summary of 2 included studies._\n\n"
            + "| Study (Year) | Country | Design | N | Key Finding |\n"
            + "|---|---|---|---|---|\n"
            + "| Smith (2024) | US | RCT | 100 | Improved |\n\n"
            + "---\n\n## Figures\n\n![PRISMA](fig_prisma_flow.png)\n\n"
            + "---\n\n## References\n\n1. Smith J. 2024.\n"
        )

    flag = ContradictionFlag(
        paper_id_a="p-1",
        paper_id_b="p-2",
        outcome_name="adherence",
        direction_a="positive",
        direction_b="negative",
        similarity=0.85,
        confidence=0.9,
        note="Divergent adherence effect",
    )
    brief_pack = DiagramBriefPack(
        workflow_id=state.workflow_id,
        source_included_count=2,
        diagrams=[
            ResearchDiagramBrief(
                diagram_id="diag-1",
                diagram_type="method_flow",
                title="Reminder Workflow",
                objective="Illustrate digital reminder intervention workflow across studies.",
            ),
            ResearchDiagramBrief(
                diagram_id="diag-2",
                diagram_type="evidence_map",
                title="Adherence Evidence Map",
                objective="Summarize adherence outcome directions across included studies.",
            ),
        ],
    )
    save_sub = AsyncMock()
    with (
        patch("src.orchestration.runners.writing.post_assembly.detect_contradictions", return_value=[flag]),
        patch(
            "src.orchestration.runners.writing.post_assembly.generate_contradiction_paragraph",
            new=AsyncMock(return_value="Heterogeneity may explain divergent findings."),
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.assemble_submission_manuscript",
            side_effect=_fake_assemble,
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.render_concept_diagrams",
            new=AsyncMock(side_effect=RuntimeError("graphviz unavailable")),
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.prepare_research_diagram_briefs",
            new=AsyncMock(return_value=(brief_pack, {})),
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.plan_inline_diagram_placements",
            new=AsyncMock(return_value=(DiagramPlacementPlan(workflow_id=state.workflow_id), {})),
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.render_custom_research_diagrams",
            new=AsyncMock(return_value=DiagramGenerationReport(workflow_id=state.workflow_id)),
        ),
    ):
        await run_post_assembly(
            state,
            sections_written=[section_texts[s] for s in SECTIONS],
            failed_sections=[],
            citation_catalog="[Smith2024] Trial 1\n[Doe2024] Trial 2",
            narrative=None,
            prisma_counts=None,
            rewound_before_writing=False,
            rc=state.run_context,
            save_subphase_checkpoint=save_sub,
        )

    manuscript_text = Path(state.artifacts["manuscript_md"]).read_text(encoding="utf-8")
    assert "[INTERVENTION]" not in manuscript_text
    assert "digital reminder" in manuscript_text
    assert "Doe2024" in manuscript_text  # programmatic citation coverage patch injected uncited Doe2024
    assert state.contradiction_flags == [flag]
    assert "### Conflicting Evidence" in manuscript_text
    assert "Divergent adherence effect" in manuscript_text

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        assembly = await repo.load_latest_manuscript_assembly(state.workflow_id, "md")
        tbl_asset = await repo.load_latest_manuscript_asset(state.workflow_id, "tbl_study_characteristics_compact")
        fig_asset = await repo.load_latest_manuscript_asset(state.workflow_id, "sec_figures")
        ref_asset = await repo.load_latest_manuscript_asset(state.workflow_id, "sec_references")
        cur = await db.execute(
            "SELECT content FROM section_drafts WHERE workflow_id = ? AND section = 'results' ORDER BY version DESC LIMIT 1",
            (state.workflow_id,),
        )
        results_row = await cur.fetchone()

    assert assembly is not None
    assert tbl_asset is not None
    assert fig_asset is not None
    assert ref_asset is not None
    assert results_row is not None and "Doe2024" in results_row[0]
    save_sub.assert_any_await("phase_6d_assembly", papers_processed=len(SECTIONS))
    save_sub.assert_any_await("phase_6f_custom_diagrams", papers_processed=0)


@pytest.mark.asyncio
async def test_post_assembly_rewound_before_writing_prefers_in_memory_sections_over_stale_db(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, workflow_id="wf-post-rewind")
    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        for idx, sec in enumerate(SECTIONS):
            await repo.save_section_artifacts_from_draft(
                SectionDraft(
                    workflow_id=state.workflow_id,
                    section=sec,
                    version=1,
                    content=f"STALE_DB_{sec}",
                    word_count=1,
                ),
                section_order=idx,
            )

    fresh_sections = [
        _valid_abstract_markdown(),
        "FRESH_INTRO",
        "FRESH_METHODS",
        "FRESH_RESULTS",
        "FRESH_DISCUSSION",
        "FRESH_CONCLUSION",
    ]
    with (
        patch("src.orchestration.runners.writing.post_assembly.detect_contradictions", return_value=[]),
        patch(
            "src.orchestration.runners.writing.post_assembly.assemble_submission_manuscript",
            side_effect=lambda *, body, **_kw: body,
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.render_concept_diagrams",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "src.orchestration.runners.writing.post_assembly.prepare_research_diagram_briefs",
            new=AsyncMock(side_effect=RuntimeError("skip custom diagrams")),
        ),
    ):
        await run_post_assembly(
            state,
            sections_written=fresh_sections,
            failed_sections=[],
            citation_catalog="",
            narrative=None,
            prisma_counts=None,
            rewound_before_writing=True,
            rc=None,
            save_subphase_checkpoint=AsyncMock(),
        )

    manuscript_text = Path(state.artifacts["manuscript_md"]).read_text(encoding="utf-8")
    assert "FRESH_INTRO" in manuscript_text
    assert "STALE_DB_introduction" not in manuscript_text


# ---------------------------------------------------------------------------
# writing_runner.py: full runner orchestration, zero-papers, invariant failure, manifests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writing_runner_zero_papers_fast_path_skips_llm_and_completes(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, workflow_id="wf-zero-papers", papers=[])
    state.deduped_papers = []
    state.included_papers = []
    state.extraction_records = []

    with (
        patch("src.orchestration.runners.writing.setup.render_prisma_diagram"),
        patch("src.orchestration.runners.writing.setup.render_timeline"),
        patch("src.orchestration.runners.writing.setup.render_geographic"),
        patch(
            "src.orchestration.runners.writing.setup.register_background_sr_citations",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "src.orchestration.runners.writing_runner.run_section_writing_loop",
            new=AsyncMock(),
        ) as mock_loop,
        patch(
            "src.orchestration.runners.writing_runner.run_post_assembly",
            new=AsyncMock(),
        ) as mock_post,
    ):
        await run_writing_node(state, _ctx(state))

    mock_loop.assert_not_awaited()
    mock_post.assert_awaited_once()
    assert len(mock_post.await_args.kwargs["sections_written"]) == len(SECTIONS)

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        checkpoints = await repo.get_checkpoints(state.workflow_id)
        manifests = await repo.get_writing_manifests(state.workflow_id)
        step_rows = await repo.get_step_history(state.workflow_id, phase="phase_6_writing")

    assert checkpoints["phase_6_writing"] == "completed"
    assert len(manifests) == len(SECTIONS)
    assert step_rows and step_rows[0].status == StepStatus.SUCCEEDED
    state.run_context.emit_phase_start.assert_called_once()
    state.run_context.emit_phase_done.assert_called_once_with("phase_6_writing", {"sections": len(SECTIONS)})


@pytest.mark.asyncio
async def test_writing_runner_persists_manifests_and_fallback_events(tmp_path: Path) -> None:
    state = await _init_state(tmp_path, workflow_id="wf-manifests")

    async def _fake_setup(s: ReviewState, **_kw) -> dict:
        return {
            "prisma_counts": None,
            "provider": MagicMock(),
            "grounding": MagicMock(),
            "citation_catalog": "[Smith2024] Digital reminder trial (2024)",
            "completed": set(),
            "bg_citekeys": [],
            "rewound_before_writing": False,
            "sections_written_zero": None,
        }

    async def _fake_loop(s: ReviewState, *, repository: WorkflowRepository, **_kw) -> SectionLoopResult:
        res_by_key = {}
        written = []
        for idx, sec in enumerate(SECTIONS):
            text = f"Section {sec} content."
            written.append(text)
            await repository.save_section_artifacts_from_draft(
                SectionDraft(
                    workflow_id=s.workflow_id,
                    section=sec,
                    version=1,
                    content=text,
                    word_count=len(text.split()),
                ),
                section_order=idx,
            )
            res_by_key[sec] = _section_write_result(
                sec,
                content=text,
                fallback_used=(sec == "methods"),
                validation_issues=(["thin_subsection_body:search"] if sec == "methods" else []),
                validation_retries=(1 if sec == "methods" else 0),
            )
        return SectionLoopResult(
            sections_written=written,
            failed_sections=[],
            section_results_by_key=res_by_key,
            placeholder_sections={"abstract"},
        )

    with (
        patch("src.orchestration.runners.writing_runner.run_writing_setup", side_effect=_fake_setup),
        patch("src.orchestration.runners.writing_runner.run_section_writing_loop", side_effect=_fake_loop),
        patch("src.orchestration.runners.writing_runner.run_post_assembly", new=AsyncMock()),
    ):
        await run_writing_node(state, _ctx(state))

    async with get_db(state.db_path) as db:
        repo = WorkflowRepository(db)
        manifests = await repo.get_writing_manifests(state.workflow_id)
        fb_summary = await repo.get_fallback_event_summary(state.workflow_id)
        checkpoints = await repo.get_checkpoints(state.workflow_id)

    assert checkpoints["phase_6_writing"] == "completed"
    by_sec = {m.section_key: m for m in manifests}
    assert len(by_sec) == len(SECTIONS)
    assert by_sec["methods"].fallback_used is True
    assert by_sec["methods"].retry_count == 1
    assert by_sec["abstract"].fallback_used is True
    assert by_sec["results"].fallback_used is False
    fb_types = {row["fallback_type"] for row in fb_summary}
    assert "deterministic_section_fallback" in fb_types
    assert "empty_section_placeholder" in fb_types


@pytest.mark.asyncio
async def test_writing_runner_persistence_invariant_failure_saves_partial_emits_error_and_raises(
    tmp_path: Path,
) -> None:
    state = await _init_state(tmp_path, workflow_id="wf-invariant-fail")

    async def _fake_setup(s: ReviewState, **_kw) -> dict:
        return {
            "prisma_counts": None,
            "provider": MagicMock(),
            "grounding": MagicMock(),
            "citation_catalog": "[Smith2024] Digital reminder trial (2024)",
            "completed": set(),
            "bg_citekeys": [],
            "rewound_before_writing": False,
            "sections_written_zero": None,
        }

    async def _fake_loop(s: ReviewState, *, repository: WorkflowRepository, **_kw) -> SectionLoopResult:
        # Persist only 5 of 6 sections; omit "conclusion" so invariant triggers.
        written = []
        for idx, sec in enumerate(SECTIONS):
            if sec == "conclusion":
                written.append("")
                continue
            text = f"Section {sec} content."
            written.append(text)
            await repository.save_section_artifacts_from_draft(
                SectionDraft(
                    workflow_id=s.workflow_id,
                    section=sec,
                    version=1,
                    content=text,
                    word_count=len(text.split()),
                ),
                section_order=idx,
            )
        return SectionLoopResult(
            sections_written=written,
            failed_sections=["conclusion"],
            section_results_by_key={},
            placeholder_sections=set(),
        )

    with (
        patch("src.orchestration.runners.writing_runner.run_writing_setup", side_effect=_fake_setup),
        patch("src.orchestration.runners.writing_runner.run_section_writing_loop", side_effect=_fake_loop),
        patch("src.orchestration.runners.writing_runner.run_post_assembly", new=AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="Writing section persistence invariant failed"):
            await run_writing_node(state, _ctx(state))

    async with get_db(state.db_path) as db:
        checkpoints = await WorkflowRepository(db).get_checkpoints(state.workflow_id)
    assert checkpoints["phase_6_writing"] == "partial"

    emitted_events = [call.args[0] for call in state.run_context._emit.call_args_list]
    error_events = [ev for ev in emitted_events if isinstance(ev, dict) and ev.get("type") == "writing_error"]
    assert len(error_events) == 1
    assert error_events[0]["missing_sections"] == ["conclusion"]
    assert error_events[0]["failed_sections"] == ["conclusion"]
    state.run_context.emit_phase_done.assert_not_called()
