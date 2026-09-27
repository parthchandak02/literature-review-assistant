from __future__ import annotations

import asyncio
import random
import re
import threading
import time

import pytest

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository, WorkflowRepository
from src.models import AgentConfig, ReviewConfig, ReviewType, SettingsConfig
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.context_builder import WritingGroundingData
from src.writing.orchestration import (
    _render_and_sanitize,
    _sanitize_section_headings,
    write_section_with_validation,
)
from src.writing.renderers import render_section_markdown
from src.writing.section_validation import has_excessive_comma_list
from src.writing.section_writer import SectionWriteMetadata

_WORDS = "adaptive feedback learners outcomes tutoring engagement retention cohorts".split()


def _run_bounded(fn, timeout: float = 2.0):
    box: dict[str, object] = {}

    def _target() -> None:
        box["value"] = fn()

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), f"call did not finish within {timeout}s"
    return box["value"]


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does adaptive tutoring improve learner outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "university students",
            "intervention": "adaptive tutoring",
            "comparison": "usual instruction",
            "outcome": "learning outcomes",
        },
        keywords=["adaptive tutoring"],
        domain="education",
        scope="systematic review scope",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews"],
        date_range_start=2020,
        date_range_end=2026,
        target_databases=["openalex"],
    )


def _settings() -> SettingsConfig:
    return SettingsConfig(
        agents={"writing": AgentConfig(model="google:gemini-2.5-flash", temperature=0.1)},
        writing={"ratchet_max_iterations": 1, "ratchet_cost_cap_per_section": 1.0},
    )


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
        study_design_counts={"randomized controlled trial": 3},
        total_participants=120,
        year_range="2020-2024",
        meta_analysis_feasible=False,
        synthesis_direction="mixed",
        n_studies_synthesized=3,
        narrative_text="Narrative synthesis only.",
        key_themes=["engagement"],
        study_summaries=[],
        valid_citekeys=["Janzen2026"],
        included_study_citekeys=["Janzen2026"],
        fulltext_sought=3,
        fulltext_not_retrieved=0,
    )


@pytest.mark.parametrize(
    "content",
    [
        "### Implications for Practice in Rural Settings\n\nBody.\n\n### Discussion\n\nMore body.",
        "### Implications for Practice in Rural Settings\n\nBody.\n\n### Implications for\n\nlowercase body.",
        "### Limitations in Rural Settings\n\nA.\n\n### Limitations in Rural Settings\n\nB.",
        "### Evidence in Rural Settings\n\nA.\n\n### [Janzen2026]\n\nB.",
    ],
)
def test_sanitize_section_headings_terminates_when_dropping_headings(content: str) -> None:
    out = _run_bounded(lambda: _sanitize_section_headings("discussion", content))
    assert "Body." in out or "A." in out


def test_sanitize_section_headings_drops_section_name_and_connector_headings() -> None:
    out = _run_bounded(
        lambda: _sanitize_section_headings(
            "discussion", "### Discussion\n\nFirst body.\n\n### Implications for\n\nlowercase body."
        )
    )
    assert "### Discussion" not in out
    assert "### Implications for" not in out
    assert "First body." in out
    assert "lowercase body." in out


def test_has_excessive_comma_list_matches_legacy_regex() -> None:
    rng = random.Random(7)
    alphabet = [",", " ", "\n", "a", "b"]
    for _ in range(5000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        min_items = rng.randint(1, 5)
        max_chars = rng.randint(1, 4)
        legacy = bool(re.search(rf"(?:,\s*[^,]{{1,{max_chars}}}){{{min_items},}}", text))
        assert has_excessive_comma_list(text, min_items, max_chars) is legacy


def test_has_excessive_comma_list_is_linear_on_near_miss_lists() -> None:
    near_miss = ("Across studies, " + ", ".join(["ab cd"] * 18) + " " + "y" * 200 + ". ") * 200
    start = time.perf_counter()
    assert has_excessive_comma_list(near_miss) is False
    assert has_excessive_comma_list(near_miss, min_items=8) is True
    assert time.perf_counter() - start < 0.5


def _adversarial_discussion_draft() -> StructuredSectionDraft:
    rng = random.Random(0)
    keys = [f"Janzen{2000 + i}" for i in range(30)]

    def _near_miss_paragraph() -> str:
        parts = []
        for _ in range(4):
            segments = [" ".join(rng.choice(_WORDS) for _ in range(2)) for _ in range(17)]
            tail = " ".join(rng.choice(_WORDS) for _ in range(20))
            parts.append("Across studies, " + ", ".join(segments) + f" {tail}. [{', '.join(rng.sample(keys, 3))}]")
        return " ".join(parts)

    headings = [
        "Summary of Main Findings in Rural Settings",
        "Discussion",
        "Implications for",
        "Implications for",
        "Future Research Directions",
    ]
    blocks: list[SectionBlock] = []
    for heading in headings:
        blocks.append(SectionBlock(block_type="subheading", text=heading, level=3))
        blocks.append(SectionBlock(block_type="paragraph", text=_near_miss_paragraph(), citations=keys[:4]))
    return StructuredSectionDraft(section_key="discussion", blocks=blocks)


def test_render_and_sanitize_completes_quickly_on_adversarial_discussion() -> None:
    draft = _adversarial_discussion_draft()
    valid = {f"Janzen{2000 + i}" for i in range(30)}
    start = time.perf_counter()
    _structured, content, _forced = _run_bounded(
        lambda: _render_and_sanitize(
            "discussion",
            draft,
            grounding=_grounding(),
            review=_review(),
            settings=_settings(),
            valid_citekeys=valid,
        ),
        timeout=5.0,
    )
    assert time.perf_counter() - start < 1.0
    assert "### Discussion" not in content


@pytest.mark.asyncio
async def test_write_section_post_processing_does_not_block_event_loop(tmp_path, monkeypatch) -> None:
    draft = StructuredSectionDraft(
        section_key="introduction",
        blocks=[SectionBlock(block_type="paragraph", text="A complete introduction paragraph.")],
    )

    async def _fake_write(self, section, context, word_limit=None, agent_name="writing"):
        _ = (self, section, context, word_limit, agent_name)
        return draft, SectionWriteMetadata(
            model="google:gemini-2.5-flash", tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1
        )

    def _slow_render(section, structured, **kwargs):
        _ = (section, kwargs)
        time.sleep(0.5)
        return structured, render_section_markdown(structured), False

    async def _no_claims(*args, **kwargs):
        _ = (args, kwargs)
        return 0

    async def _validation_stub(self, section, content):
        _ = (self, section, content)

        class _Result:
            unresolved_citations: list[str] = []
            unresolved_claims: list[str] = []

        return _Result()

    monkeypatch.setattr("src.writing.section_writer.SectionWriter.write_section_structured_async", _fake_write)
    monkeypatch.setattr("src.writing.orchestration._render_and_sanitize", _slow_render)
    monkeypatch.setattr("src.writing.orchestration._section_completeness_issues", lambda *a, **k: [])
    monkeypatch.setattr("src.writing.orchestration.extract_and_register_claims", _no_claims)
    monkeypatch.setattr(CitationLedger, "validate_section", _validation_stub)

    ticks = 0
    stop = asyncio.Event()

    async def _ticker() -> None:
        nonlocal ticks
        while not stop.is_set():
            await asyncio.sleep(0.02)
            ticks += 1

    async with get_db(str(tmp_path / "loop_safety.db")) as db:
        await WorkflowRepository(db).create_workflow("wf-loop", "topic", "hash")
        ticker = asyncio.create_task(_ticker())
        result = await write_section_with_validation(
            section="introduction",
            context="context",
            workflow_id="wf-loop",
            review=_review(),
            settings=_settings(),
            citation_repo=CitationRepository(db),
        )
        stop.set()
        await ticker

    assert result.content_markdown == "A complete introduction paragraph."
    assert ticks >= 10
