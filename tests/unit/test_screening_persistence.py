"""Rows written when a screening heuristic excludes a paper before LLM review."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.models import CandidatePaper, ExclusionReason, ReviewerType, ScreeningDecisionType
from src.screening.persistence import (
    persist_insufficient_content_exclusion,
    persist_no_fulltext_exclusion,
    persist_protocol_exclusion,
)


def _paper(paper_id: str) -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title="Effects of a classroom intervention",
        authors=["Ada Lovelace"],
        source_database="openalex",
        abstract="Participants were enrolled and the endpoint was measured.",
    )


async def _row(db, sql: str, params: tuple[object, ...]) -> tuple[object, ...] | None:
    cursor = await db.execute(sql, params)
    fetched = await cursor.fetchone()
    if fetched is None:
        return None
    return tuple(fetched)


@pytest.mark.asyncio
async def test_protocol_exclusion_persists_decision_log_and_callback(tmp_path: Path) -> None:
    paper = _paper("p-proto")
    seen: list[tuple[object, ...]] = []
    async with get_db(str(tmp_path / "protocol.db")) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        decision = await persist_protocol_exclusion(
            repo,
            workflow_id="wf-proto",
            stage="title_abstract",
            paper_id=paper.paper_id,
            on_screening_decision=lambda *args: seen.append(args),
        )
        await persist_protocol_exclusion(
            repo,
            workflow_id="wf-proto",
            stage="title_abstract",
            paper_id=paper.paper_id,
        )

        assert decision.decision == ScreeningDecisionType.EXCLUDE
        assert decision.confidence == 0.95
        assert decision.reviewer_type == ReviewerType.KEYWORD_FILTER
        assert decision.exclusion_reason == ExclusionReason.PROTOCOL_ONLY
        assert seen == [(paper.paper_id, "title_abstract", "exclude", "protocol_only_heuristic", 0.95)]

        stored = await _row(
            db,
            """
            SELECT decision, exclusion_reason, reviewer_type, confidence
            FROM screening_decisions
            WHERE workflow_id = ? AND paper_id = ? AND stage = ?
            """,
            ("wf-proto", paper.paper_id, "title_abstract"),
        )
        assert stored == ("exclude", "protocol_only", "keyword_filter", 0.95)
        count = await _row(
            db,
            "SELECT COUNT(*) FROM screening_decisions WHERE workflow_id = ? AND paper_id = ?",
            ("wf-proto", paper.paper_id),
        )
        assert count == (1,)
        dual = await _row(
            db,
            "SELECT COUNT(*) FROM dual_screening_results WHERE workflow_id = ? AND paper_id = ?",
            ("wf-proto", paper.paper_id),
        )
        assert dual == (0,)
        logged = await _row(
            db,
            """
            SELECT workflow_id, decision_type, decision, rationale, actor, phase
            FROM decision_log WHERE paper_id = ?
            """,
            (paper.paper_id,),
        )
        assert logged is not None
        assert logged[0] == ""
        assert logged[1:] == (
            "screening_protocol_heuristic",
            "exclude",
            "Protocol-only auto-exclusion (no results available).",
            "keyword_filter",
            "phase_3_screening",
        )


@pytest.mark.asyncio
async def test_insufficient_content_exclusion_records_word_threshold(tmp_path: Path) -> None:
    paper = _paper("p-short")
    seen: list[tuple[object, ...]] = []
    async with get_db(str(tmp_path / "short.db")) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        decision = await persist_insufficient_content_exclusion(
            repo,
            workflow_id="wf-short",
            stage="title_abstract",
            paper_id=paper.paper_id,
            abstract_word_count=2,
            min_words_threshold=5,
            on_screening_decision=lambda *args: seen.append(args),
        )
        assert decision.exclusion_reason == ExclusionReason.INSUFFICIENT_DATA
        assert decision.confidence == 0.90
        assert decision.reviewer_type == ReviewerType.KEYWORD_FILTER
        assert seen == [(paper.paper_id, "title_abstract", "exclude", "insufficient_content_heuristic|2w", 0.90)]
        logged = await _row(
            db,
            "SELECT decision_type, rationale, actor FROM decision_log WHERE paper_id = ?",
            (paper.paper_id,),
        )
        assert logged == (
            "screening_insufficient_content_heuristic",
            "Abstract absent or stub (2 words). Threshold: fewer than 5 words or explicit no-abstract marker.",
            "keyword_filter",
        )
        stored = await _row(
            db,
            "SELECT exclusion_reason, confidence FROM screening_decisions WHERE paper_id = ?",
            (paper.paper_id,),
        )
        assert stored == ("insufficient_data", 0.90)


@pytest.mark.asyncio
async def test_no_fulltext_exclusion_writes_dual_result(tmp_path: Path) -> None:
    paper = _paper("p-pdf")
    seen: list[tuple[object, ...]] = []
    async with get_db(str(tmp_path / "pdf.db")) as db:
        repo = WorkflowRepository(db)
        await repo.save_paper(paper)
        decision = await persist_no_fulltext_exclusion(
            repo,
            workflow_id="wf-pdf",
            stage="fulltext",
            paper_id=paper.paper_id,
            on_screening_decision=lambda *args: seen.append(args),
        )
        assert decision.decision == ScreeningDecisionType.EXCLUDE
        assert decision.confidence == 1.0
        assert decision.reviewer_type == ReviewerType.ADJUDICATOR
        assert decision.exclusion_reason == ExclusionReason.NO_FULL_TEXT
        assert decision.reason == "Full text not retrievable."
        assert seen == [(paper.paper_id, "fulltext", "exclude", "fulltext_no_pdf_heuristic", 1.0)]

        stored = await _row(
            db,
            """
            SELECT decision, exclusion_reason, reviewer_type, confidence
            FROM screening_decisions WHERE workflow_id = ? AND paper_id = ? AND stage = ?
            """,
            ("wf-pdf", paper.paper_id, "fulltext"),
        )
        assert stored == ("exclude", "no_full_text", "adjudicator", 1.0)
        dual = await _row(
            db,
            """
            SELECT agreement, final_decision, adjudication_needed
            FROM dual_screening_results WHERE workflow_id = ? AND paper_id = ? AND stage = ?
            """,
            ("wf-pdf", paper.paper_id, "fulltext"),
        )
        assert dual == (1, "exclude", 0)
        logged = await _row(
            db,
            "SELECT decision_type, rationale, actor, phase FROM decision_log WHERE paper_id = ?",
            (paper.paper_id,),
        )
        assert logged == (
            "screening_no_fulltext",
            "Full text not retrievable; excluded per skip_fulltext_if_no_pdf.",
            "adjudicator",
            "phase_3_screening",
        )
