from src.restart.mvp_pipeline import (
    CandidatePaper,
    MVPGraphPipeline,
    ScreeningDecision,
    SearchQueryInput,
    SectionDraft,
)


def test_mvp_pipeline_runs_with_fallback():
    def search_fn(search_input: SearchQueryInput):
        assert search_input.query == "test query"
        return [
            CandidatePaper(
                title="Paper A",
                abstract="A" * 40,
                source="openalex",
            ),
            CandidatePaper(
                title="Paper B",
                abstract="B" * 40,
                source="crossref",
            ),
        ]

    def screen_fn(paper: CandidatePaper):
        include = paper.title == "Paper A"
        return ScreeningDecision(
            include=include,
            confidence=0.9,
            reasoning="include first paper",
        )

    def write_fn(papers: list[CandidatePaper]):
        assert len(papers) == 1
        return SectionDraft(
            section_name="introduction",
            content="This draft is long enough to satisfy the schema constraints for testing.",
            citations=["[Smith2024]"],
        )

    pipeline = MVPGraphPipeline(search_fn=search_fn, screen_fn=screen_fn, write_fn=write_fn)
    state = pipeline.run("test query", max_results=10)
    assert len(state["candidates"]) == 2
    assert len(state["included_candidates"]) == 1
    assert state["introduction_draft"]["section_name"] == "introduction"
