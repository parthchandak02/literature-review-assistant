"""Unit tests for deterministic contradiction detection.

Writing post-assembly calls detect_contradictions and turns flags into the
conflicting-evidence paragraph. Existing tests mock that call, so these
cover the detector itself.
"""

from __future__ import annotations

from src.models import ExtractionRecord, OutcomeRecord, StudyDesign
from src.synthesis.contradiction_detector import detect_contradictions


def _record(
    paper_id: str,
    summary: str,
    *,
    outcome: str = "retention",
    ci_lower: str = "",
    ci_upper: str = "",
) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.RCT,
        intervention_description="tutoring program",
        outcomes=[
            OutcomeRecord(
                name=outcome,
                effect_size="0.20",
                se="0.05",
                ci_lower=ci_lower,
                ci_upper=ci_upper,
            )
        ],
        results_summary={"summary": summary},
    )


def _words(count: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def test_fewer_than_two_records_returns_no_flags() -> None:
    assert detect_contradictions([]) == []
    assert detect_contradictions([_record("p1", f"{_words(12)} improved")]) == []


def test_blank_summary_is_skipped_even_when_another_pair_conflicts() -> None:
    shared = _words(12)
    flags = detect_contradictions(
        [
            _record("positive", f"{shared} improved beneficial"),
            _record("blank", ""),
            _record("negative", f"{shared} harmful null"),
        ]
    )
    assert len(flags) == 1
    assert {flags[0].paper_id_a, flags[0].paper_id_b} == {"positive", "negative"}


def test_similar_opposite_summaries_flag_shared_outcome() -> None:
    shared = _words(18)
    flags = detect_contradictions(
        [
            _record("paper-a", f"{shared} improved", outcome="Retention"),
            _record("paper-b", f"{shared} harmful", outcome="retention"),
        ]
    )
    assert len(flags) == 1
    flag = flags[0]
    assert flag.paper_id_a == "paper-a"
    assert flag.paper_id_b == "paper-b"
    assert flag.outcome_name == "retention"
    assert {flag.direction_a, flag.direction_b} == {"positive", "negative"}
    assert flag.similarity == flag.confidence
    assert flag.note == ""
    assert flag.similarity >= 0.75


def test_same_direction_and_low_overlap_are_not_flagged() -> None:
    shared = _words(18)
    assert (
        detect_contradictions(
            [
                _record("paper-a", f"{shared} improved"),
                _record("paper-b", f"{shared} beneficial"),
            ]
        )
        == []
    )
    assert (
        detect_contradictions(
            [
                _record("paper-a", f"{_words(3)} improved"),
                _record("paper-b", f"{_words(3)} harmful"),
            ]
        )
        == []
    )


def test_mixed_direction_phrase_is_not_treated_as_an_opposite() -> None:
    """'no significant' also contains the positive keyword 'significant'."""
    shared = _words(18)
    flags = detect_contradictions(
        [
            _record("paper-a", f"{shared} improved"),
            _record("paper-b", f"{shared} no significant"),
        ]
    )
    assert flags == []


def test_missing_shared_outcome_uses_primary_outcome_label() -> None:
    shared = _words(18)
    flags = detect_contradictions(
        [
            _record("paper-a", f"{shared} improved", outcome="exam score"),
            _record("paper-b", f"{shared} harmful", outcome="attendance"),
        ]
    )
    assert len(flags) == 1
    assert flags[0].outcome_name == "primary_outcome"


def test_nonoverlapping_intervals_raise_confidence_and_cap_at_one() -> None:
    shared = _words(18)
    flags = detect_contradictions(
        [
            _record(
                "paper-a",
                f"{shared} improved",
                ci_lower="0.10",
                ci_upper="0.20",
            ),
            _record(
                "paper-b",
                f"{shared} harmful",
                ci_lower="0.50",
                ci_upper="0.80",
            ),
        ]
    )
    assert len(flags) == 1
    flag = flags[0]
    assert flag.confidence == 1.0
    assert flag.confidence > flag.similarity
    assert flag.note == "Non-overlapping 95% CIs confirm directional disagreement."


def test_overlapping_or_missing_intervals_do_not_boost_confidence() -> None:
    shared = _words(18)
    overlapping = detect_contradictions(
        [
            _record("paper-a", f"{shared} improved", ci_lower="0.10", ci_upper="0.50"),
            _record("paper-b", f"{shared} harmful", ci_lower="0.40", ci_upper="0.90"),
        ]
    )
    missing = detect_contradictions(
        [
            _record("paper-a", f"{shared} improved", ci_lower="not-a-number", ci_upper="0.2"),
            _record("paper-b", f"{shared} harmful"),
        ]
    )
    assert len(overlapping) == 1
    assert overlapping[0].confidence == overlapping[0].similarity
    assert overlapping[0].note == ""
    assert len(missing) == 1
    assert missing[0].confidence == missing[0].similarity
    assert missing[0].note == ""


def test_flags_are_ordered_by_confidence() -> None:
    high = _words(10)
    flags = detect_contradictions(
        [
            _record("paper-a", f"{high} improved", outcome="score"),
            _record("paper-c", f"{_words(9)} harmful", outcome="other"),
            _record("paper-b", f"{high} harmful", outcome="score"),
        ]
    )
    assert len(flags) == 2
    assert flags[0].confidence >= flags[1].confidence
    assert {flags[0].paper_id_a, flags[0].paper_id_b} == {"paper-a", "paper-b"}
    assert flags[0].outcome_name == "score"
    assert {flags[1].paper_id_a, flags[1].paper_id_b} == {"paper-a", "paper-c"}
    assert flags[1].outcome_name == "primary_outcome"


def test_embeddings_replace_text_overlap_when_both_papers_have_vectors() -> None:
    shared = _words(18)
    dissimilar = [
        _record("paper-a", "improved beneficial positive effective"),
        _record("paper-b", "harmful null neutral worsened"),
    ]
    assert detect_contradictions(dissimilar) == []
    flagged = detect_contradictions(
        dissimilar,
        chunk_embeddings={"paper-a": [1.0, 0.0], "paper-b": [1.0, 0.0]},
    )
    assert len(flagged) == 1
    assert flagged[0].similarity == 1.0

    similar = [
        _record("paper-a", f"{shared} improved"),
        _record("paper-b", f"{shared} harmful"),
    ]
    assert detect_contradictions(similar) != []
    suppressed = detect_contradictions(
        similar,
        chunk_embeddings={"paper-a": [1.0, 0.0], "paper-b": [0.0, 1.0]},
    )
    assert suppressed == []


def test_missing_embedding_uses_text_and_bad_vectors_do_not() -> None:
    shared = _words(18)
    records = [
        _record("paper-a", f"{shared} improved"),
        _record("paper-b", f"{shared} harmful"),
    ]
    one_sided = detect_contradictions(records, chunk_embeddings={"paper-a": [1.0, 0.0]})
    zero_vector = detect_contradictions(
        records,
        chunk_embeddings={"paper-a": [0.0, 0.0], "paper-b": [1.0, 0.0]},
    )
    mismatched = detect_contradictions(
        records,
        chunk_embeddings={"paper-a": [1.0, 0.0], "paper-b": [1.0]},
    )
    assert len(one_sided) == 1
    assert zero_vector == []
    assert mismatched == []
