"""Unit tests for build_conflicting_evidence_section (Enhancement #8)."""

from __future__ import annotations

from src.synthesis.contradiction_detector import ContradictionFlag
from src.writing.contradiction_resolver import build_conflicting_evidence_section


def _flag(
    paper_a: str = "paper-aaa-001",
    paper_b: str = "paper-bbb-002",
    outcome: str = "dispensing error rate",
    dir_a: str = "positive",
    dir_b: str = "negative",
    similarity: float = 0.82,
    note: str = "",
) -> ContradictionFlag:
    return ContradictionFlag(
        paper_id_a=paper_a,
        paper_id_b=paper_b,
        outcome_name=outcome,
        direction_a=dir_a,
        direction_b=dir_b,
        similarity=similarity,
        note=note,
    )


def test_empty_flags_returns_empty_string() -> None:
    assert build_conflicting_evidence_section([]) == ""


def test_section_contains_heading() -> None:
    result = build_conflicting_evidence_section([_flag()])
    assert "### Conflicting Evidence" in result


def test_section_contains_both_paper_ids() -> None:
    flag = _flag(paper_a="paper-aaa-001", paper_b="paper-bbb-002")
    result = build_conflicting_evidence_section([flag])
    assert "paper-aaa-001"[:12] in result
    assert "paper-bbb-002"[:12] in result


def test_section_contains_outcome_name() -> None:
    flag = _flag(outcome="medication dispensing error rate")
    result = build_conflicting_evidence_section([flag])
    assert "medication dispensing error rate" in result


def test_section_contains_direction_labels() -> None:
    flag = _flag(dir_a="positive", dir_b="negative")
    result = build_conflicting_evidence_section([flag])
    assert "positive" in result
    assert "negative" in result


def test_section_contains_similarity_score() -> None:
    flag = _flag(similarity=0.87)
    result = build_conflicting_evidence_section([flag])
    assert "0.87" in result


def test_note_appended_when_present() -> None:
    flag = _flag(note="Different patient populations may explain the discrepancy.")
    result = build_conflicting_evidence_section([flag])
    assert "Different patient populations" in result


def test_note_absent_when_empty() -> None:
    flag = _flag(note="")
    result = build_conflicting_evidence_section([flag])
    assert "Note:" not in result


def test_multiple_flags_all_listed() -> None:
    flags = [
        _flag(outcome="dispensing accuracy"),
        _flag(outcome="medication error rate", paper_a="paper-ccc", paper_b="paper-ddd"),
        _flag(outcome="staff satisfaction", paper_a="paper-eee", paper_b="paper-fff"),
    ]
    result = build_conflicting_evidence_section(flags)
    assert "dispensing accuracy" in result
    assert "medication error rate" in result
    assert "staff satisfaction" in result


def test_capped_at_ten_flags() -> None:
    flags = [_flag(outcome=f"outcome_{i}", paper_a=f"paper-{i:04d}", paper_b=f"paper-{i:04d}-b") for i in range(15)]
    result = build_conflicting_evidence_section(flags)
    # Only up to 10 should appear; outcome_10 and beyond should not
    assert "outcome_9" in result
    assert "outcome_10" not in result


def test_returns_valid_markdown_subsection() -> None:
    result = build_conflicting_evidence_section([_flag(), _flag(outcome="secondary outcome")])
    lines = result.split("\n")
    # First non-empty line must be the H3 heading
    non_empty = [l for l in lines if l.strip()]
    assert non_empty[0] == "### Conflicting Evidence"
    # Should contain at least one bullet
    bullets = [l for l in lines if l.startswith("- ")]
    assert len(bullets) >= 1
