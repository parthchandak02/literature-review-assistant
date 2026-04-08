from __future__ import annotations

from src.knowledge_graph.builder import PaperEdge, PaperGraph, PaperNode, build_paper_graph
from src.knowledge_graph.community import detect_communities
from src.knowledge_graph.gap_detector import detect_research_gaps
from src.models import CandidatePaper, ExtractionRecord, OutcomeRecord, StudyDesign


def _paper(paper_id: str, title: str) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=title,
        authors=["Author A"],
        year=2024,
        source_database="test",
    )


def _record(paper_id: str, outcome: str, demographics: str, design: StudyDesign) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=design,
        participant_demographics=demographics,
        intervention_description="AI tutoring support in classrooms",
        outcomes=[OutcomeRecord(name=outcome)],
        results_summary={"summary": "Outcome reported."},
    )


def test_build_paper_graph_creates_shared_outcome_edge() -> None:
    records = [
        _record("p1", "exam_score", "urban students", StudyDesign.RCT),
        _record("p2", "exam_score", "rural students", StudyDesign.RCT),
    ]
    graph = build_paper_graph(records, [_paper("p1", "One"), _paper("p2", "Two")])
    assert len(graph.nodes) == 2
    assert any(edge.rel_type == "shared_outcome" for edge in graph.edges)


def test_detect_communities_falls_back_to_single_cluster() -> None:
    graph = PaperGraph(
        nodes=[
            PaperNode(paper_id="p1", title="One", year=2024, study_design="rct"),
            PaperNode(paper_id="p2", title="Two", year=2024, study_design="rct"),
        ],
        edges=[PaperEdge(source="p1", target="p2", rel_type="shared_outcome", weight=0.8)],
    )
    updated_nodes, communities = detect_communities(graph)
    assert len(updated_nodes) == 2
    assert len(communities) >= 1


def test_detect_research_gaps_finds_sparse_outcome() -> None:
    records = [
        _record("p1", "exam_score", "urban women", StudyDesign.RCT),
        _record("p2", "exam_score", "urban men", StudyDesign.RCT),
        _record("p3", "engagement", "rural women", StudyDesign.NON_RANDOMIZED),
        _record("p4", "exam_score", "urban students", StudyDesign.RCT),
        _record("p5", "exam_score", "urban students", StudyDesign.RCT),
    ]
    gaps = detect_research_gaps(records)
    assert any(gap.gap_type == "missing_outcome" for gap in gaps)
