from __future__ import annotations

import pytest

from src.llm.pydantic_client import PydanticAIClient
from src.models.writing import StructuredAbstractOutput
from src.writing.section_writer import SectionWriter


def _sentences(seed: str, repeat: int) -> str:
    return " ".join(f"{seed} sentence {i} improves manuscript quality." for i in range(1, repeat + 1))


def _abstract(per_field: int) -> StructuredAbstractOutput:
    return StructuredAbstractOutput(
        background=_sentences("Background", per_field),
        objectives=_sentences("Objectives", per_field),
        methods=_sentences("Methods", per_field),
        results=_sentences("Results", per_field),
        conclusions=_sentences("Conclusions", per_field),
        keywords=["systematic review", "evidence synthesis", "older adults"],
    )


def _writer() -> SectionWriter:
    review = type(
        "Review",
        (),
        {
            "domain_brief_lines": lambda self=None: [],
            "domain_signal_terms": lambda self=None, limit=12: [],
            "preferred_terminology": lambda self=None: [],
            "discouraged_terminology": lambda self=None: [],
            "expert_topic": lambda self=None: "pickleball",
            "domain": "gerontology",
            "research_question": "What are the effects of pickleball?",
            "keywords": ["pickleball"],
        },
    )()
    settings = type(
        "Settings",
        (),
        {
            "llm": type("LLM", (), {"request_timeout_seconds": 60})(),
            "agents": {"writing": type("Agent", (), {"model": "google:gemini-3.5-flash", "temperature": 0.1})()},
            "writing": type("Writing", (), {"abstract_trim_floor_words": 210})(),
            "ieee_export": type("IEEE", (), {"max_abstract_words": 250})(),
        },
    )()
    return SectionWriter(review=review, settings=settings)


def _patch(monkeypatch: pytest.MonkeyPatch, payload: StructuredAbstractOutput, prompts: list[str]) -> None:
    async def fake(self, prompt, **kwargs):
        prompts.append(prompt)
        return payload, 100, 100, 0, 0, 0

    monkeypatch.setattr(PydanticAIClient, "complete_validated", fake)


@pytest.mark.asyncio
async def test_near_miss_abstract_is_kept_instead_of_template(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[str] = []
    _patch(monkeypatch, _abstract(per_field=6), prompts)
    structured, _ = await _writer().write_section_structured_async("abstract", "grounded context")
    assert structured.section_key == "abstract"
    assert len(prompts) == 2
    assert "180 < 210" in prompts[1]


@pytest.mark.asyncio
async def test_far_off_abstract_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _abstract(per_field=2), [])
    with pytest.raises(RuntimeError, match="failed structured output validation"):
        await _writer().write_section_structured_async("abstract", "grounded context")


def test_fit_to_max_words_trims_longest_fields() -> None:
    long_abstract = _abstract(per_field=14)
    assert long_abstract.body_word_count() == 420
    fitted = long_abstract.fit_to_max_words(250)
    assert 210 <= fitted.body_word_count() <= 250
    assert all(getattr(fitted, f) for f in ("background", "objectives", "methods", "results", "conclusions"))


@pytest.mark.asyncio
async def test_overlong_abstract_is_trimmed_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts: list[str] = []
    _patch(monkeypatch, _abstract(per_field=14), prompts)
    structured, _ = await _writer().write_section_structured_async("abstract", "grounded context")
    assert structured.section_key == "abstract"
    assert len(prompts) == 1
