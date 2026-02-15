"""MVP graph pipeline for search -> screen -> section draft."""

from collections.abc import Callable
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field


class SearchQueryInput(BaseModel):
    """Strict input contract for the MVP search stage."""

    query: str = Field(min_length=3)
    max_results: int = Field(default=30, ge=1, le=500)


class CandidatePaper(BaseModel):
    """Strict candidate paper contract across pipeline stages."""

    title: str = Field(min_length=3)
    abstract: str = Field(min_length=20)
    source: str
    doi: str | None = None
    url: str | None = None


class ScreeningDecision(BaseModel):
    """Structured output for screening stage."""

    include: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=5)


class SectionDraft(BaseModel):
    """Structured output for section drafting stage."""

    section_name: str
    content: str = Field(min_length=40)
    citations: list[str] = Field(default_factory=list)


class MVPGraphState(TypedDict):
    """State container used by both LangGraph and fallback execution."""

    query: str
    max_results: int
    candidates: NotRequired[list[dict[str, Any]]]
    included_candidates: NotRequired[list[dict[str, Any]]]
    introduction_draft: NotRequired[dict[str, Any]]


SearchFn = Callable[[SearchQueryInput], list[CandidatePaper]]
ScreenFn = Callable[[CandidatePaper], ScreeningDecision]
WriteFn = Callable[[list[CandidatePaper]], SectionDraft]


class MVPGraphPipeline:
    """LangGraph-first implementation with deterministic fallback."""

    def __init__(self, search_fn: SearchFn, screen_fn: ScreenFn, write_fn: WriteFn):
        self.search_fn = search_fn
        self.screen_fn = screen_fn
        self.write_fn = write_fn

    def run(self, query: str, max_results: int = 30) -> MVPGraphState:
        initial: MVPGraphState = {"query": query, "max_results": max_results}
        graph = self._build_langgraph()
        if graph is None:
            return self._run_fallback(initial)
        return graph.invoke(initial)

    def _run_fallback(self, state: MVPGraphState) -> MVPGraphState:
        search_input = SearchQueryInput(query=state["query"], max_results=state["max_results"])
        candidates = self.search_fn(search_input)
        screened = [paper for paper in candidates if self.screen_fn(paper).include]
        draft = self.write_fn(screened)
        return {
            **state,
            "candidates": [paper.model_dump() for paper in candidates],
            "included_candidates": [paper.model_dump() for paper in screened],
            "introduction_draft": draft.model_dump(),
        }

    def _build_langgraph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None

        builder = StateGraph(MVPGraphState)
        builder.add_node("search_node", self._search_node)
        builder.add_node("screen_node", self._screen_node)
        builder.add_node("write_node", self._write_node)
        builder.add_edge(START, "search_node")
        builder.add_edge("search_node", "screen_node")
        builder.add_edge("screen_node", "write_node")
        builder.add_edge("write_node", END)
        return builder.compile()

    def _search_node(self, state: MVPGraphState) -> MVPGraphState:
        search_input = SearchQueryInput(query=state["query"], max_results=state["max_results"])
        candidates = self.search_fn(search_input)
        return {"candidates": [paper.model_dump() for paper in candidates]}

    def _screen_node(self, state: MVPGraphState) -> MVPGraphState:
        included: list[dict[str, Any]] = []
        for paper_dict in state.get("candidates", []):
            paper = CandidatePaper.model_validate(paper_dict)
            decision = self.screen_fn(paper)
            if decision.include:
                included.append(paper.model_dump())
        return {"included_candidates": included}

    def _write_node(self, state: MVPGraphState) -> MVPGraphState:
        included = [
            CandidatePaper.model_validate(paper_dict)
            for paper_dict in state.get("included_candidates", [])
        ]
        draft = self.write_fn(included)
        return {"introduction_draft": draft.model_dump()}
