"""HTML entity decoding for ingested and served paper text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.papers import CandidatePaper, decode_html_entities
from src.search.crossref import CrossrefConnector


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("students&amp;apos; mental health", "students' mental health"),
        ("students&apos; mental health", "students' mental health"),
        ("A &amp;amp;amp; B", "A & B"),
        ("caf&#233; &lt;3", "café <3"),
        ("R&D and AT&T", "R&D and AT&T"),
        ("plain title", "plain title"),
        ("", ""),
    ],
)
def test_decode_html_entities(raw: str, expected: str) -> None:
    assert decode_html_entities(raw) == expected


def test_decode_is_bounded_for_deep_nesting() -> None:
    raw = "&" + "amp;" * 20 + "lt;"
    decoded = decode_html_entities(raw)
    assert decoded.startswith("&")
    assert decoded != raw


def test_candidate_paper_decodes_user_visible_fields() -> None:
    paper = CandidatePaper(
        title="The impact of pickleball participation on students&amp;apos; mental health",
        authors=["O&apos;Brien, Se&#225;n", "Smith"],
        abstract="Effects &amp;gt; 0.5 were found.",
        keywords=["health &amp; wellbeing"],
        journal="Sport &amp; Society",
        source_database="crossref",
    )
    assert paper.title == "The impact of pickleball participation on students' mental health"
    assert paper.authors == ["O'Brien, Seán", "Smith"]
    assert paper.abstract == "Effects > 0.5 were found."
    assert paper.keywords == ["health & wellbeing"]
    assert paper.journal == "Sport & Society"


def test_crossref_ingest_decodes_title() -> None:
    item = {
        "title": ["Students&amp;apos; wellbeing"],
        "author": [{"given": "Se&#225;n", "family": "O&apos;Brien"}],
        "abstract": "Rates &lt; 5%",
        "DOI": "10.1/x",
    }
    paper = CrossrefConnector._to_candidate(item)
    assert paper.title == "Students' wellbeing"
    assert paper.authors == ["Seán O'Brien"]
    assert paper.abstract == "Rates < 5%"


@pytest.mark.asyncio
async def test_screening_summary_decodes_existing_db_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.db.database import get_db
    from src.web.routers import screening_review

    db_path = tmp_path / "runtime.db"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES ('wf-1', 'T', 'h', 'running')"
        )
        await db.execute(
            "INSERT INTO papers (paper_id, title, authors, year, source_database, abstract) VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", "Students&amp;apos; health", json.dumps(["O&apos;Brien"]), 2024, "crossref", "A &amp; B"),
        )
        await db.execute(
            "INSERT INTO screening_decisions (workflow_id, paper_id, stage, decision, reason, reviewer_type,"
            " confidence) VALUES ('wf-1', 'p1', 'title_abstract', 'include', 'ok', 'reviewer_a', 0.9)"
        )
        await db.commit()

    async def _resolve(_run_id: str) -> str:
        return str(db_path)

    monkeypatch.setattr(screening_review, "resolve_runtime_db", _resolve)
    result = await screening_review.get_screening_summary("run1")
    paper = result["papers"][0]
    assert paper["title"] == "Students' health"
    assert paper["authors"] == json.dumps(["O'Brien"])
    assert paper["abstract"] == "A & B"


def test_replayed_event_titles_are_decoded() -> None:
    from src.web.event_replay import decode_event_titles

    events = [
        {"type": "screening_decision", "title": "Students&amp;apos; health"},
        {"type": "pdf_result", "title": "Plain"},
        {"type": "status", "message": "no title"},
    ]
    decoded = decode_event_titles(events)
    assert decoded[0]["title"] == "Students' health"
    assert decoded[1]["title"] == "Plain"
    assert "title" not in decoded[2]
