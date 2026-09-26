from src.rag.jev_rerank import _order_by_scores
from src.rag.retriever import RetrievedChunk
from src.screening.jev_batch_ranker import _score_to_unit


def test_score_to_unit_maps_rubric_to_zero_one() -> None:
    assert _score_to_unit(4.0) == 1.0
    assert _score_to_unit(0.0) == 0.0
    assert _score_to_unit(2.0) == 0.5


def test_order_by_scores_puts_highest_first() -> None:
    chunks = [
        RetrievedChunk(chunk_id="0", paper_id="a", chunk_index=0, content="low", score=0.1),
        RetrievedChunk(chunk_id="1", paper_id="b", chunk_index=1, content="high", score=0.1),
        RetrievedChunk(chunk_id="2", paper_id="c", chunk_index=2, content="mid", score=0.1),
    ]
    ordered = _order_by_scores(chunks, [1.0, 4.0, 2.0], top_k=2)
    assert [c.paper_id for c in ordered] == ["b", "c"]
    assert ordered[0].score == 1.0
    assert ordered[1].score == 0.95
