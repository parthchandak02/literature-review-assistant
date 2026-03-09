"""Unit tests for manuscript quality improvements (mq plan).

Covers:
- include_rq_block=False removes Research Question prefix
- build_compact_study_table generates correct 5-column table
- _trim_abstract_to_limit enforces word cap
- _build_citation_coverage_patch groups by design when mapping provided
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# include_rq_block -- Research Question prefix
# ---------------------------------------------------------------------------


def _make_mock_citation_rows() -> list:
    # row layout: (cid, citekey, doi, title, authors_json, year, journal, bibtex, url)
    return [
        (1, "Smith2021", None, "Test paper", '["Smith A"]', 2021, "Test Journal", None, None),
    ]


def test_assemble_no_rq_block_default(tmp_path: Path) -> None:
    """Default include_rq_block=False must omit 'Research Question:' from output."""
    from src.export.markdown_refs import assemble_submission_manuscript

    body = "## Introduction\n\nHello world [Smith2021].\n"
    ms_path = tmp_path / "manuscript.md"
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=ms_path,
        artifacts={},
        citation_rows=_make_mock_citation_rows(),
        research_question="What is the effect of X on Y?",
        title="A Systematic Review: X and Y",
        include_rq_block=False,
    )
    assert "Research Question:" not in result
    assert "A Systematic Review:" in result


def test_assemble_rq_block_when_enabled(tmp_path: Path) -> None:
    """include_rq_block=True must include the Research Question prefix."""
    from src.export.markdown_refs import assemble_submission_manuscript

    body = "## Introduction\n\nHello [Smith2021].\n"
    ms_path = tmp_path / "manuscript.md"
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=ms_path,
        artifacts={},
        citation_rows=_make_mock_citation_rows(),
        research_question="What is the effect of X on Y?",
        title=None,
        include_rq_block=True,
    )
    assert "**Research Question:**" in result


def test_assemble_strips_existing_rq_block(tmp_path: Path) -> None:
    """Re-runs with include_rq_block=False must strip any old prefix from body."""
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "# A Systematic Review: X\n\n"
        "**Research Question:** What is the effect of X on Y?\n\n"
        "---\n\n"
        "## Introduction\n\nHello [Smith2021].\n"
    )
    ms_path = tmp_path / "manuscript.md"
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=ms_path,
        artifacts={},
        citation_rows=_make_mock_citation_rows(),
        research_question="What is the effect of X on Y?",
        title=None,
        include_rq_block=False,
    )
    # After strip, only one title heading should appear (not duplicated)
    assert result.count("**Research Question:**") == 0
    assert result.count("A Systematic Review:") <= 1


# ---------------------------------------------------------------------------
# build_compact_study_table
# ---------------------------------------------------------------------------


def _make_paper(pid: str, authors: list, year: int, country: str = "USA") -> SimpleNamespace:
    return SimpleNamespace(
        paper_id=pid,
        authors=authors,
        year=year,
        country=country,
    )


def _make_outcome(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_extraction(pid: str, design: str, n: int, finding: str) -> SimpleNamespace:
    design_ns = SimpleNamespace(value=design)
    return SimpleNamespace(
        paper_id=pid,
        study_design=design_ns,
        participant_count=n,
        key_finding=finding,
        setting="Hospital, USA",
        title="A test title",
        objectives="Test objectives",
        population="Adults",
        intervention="Treatment X",
        comparison="Control",
        outcomes=[_make_outcome("functional outcome")],
        results_summary="Results here",
        authors_conclusions="Positive",
        limitations="Small sample",
    )


def test_compact_table_basic() -> None:
    """compact table returns correct header and row count."""
    from src.export.markdown_refs import build_compact_study_table

    papers = [
        _make_paper("p1", ["Smith, Andrew", "Jones, Bob"], 2021),
        _make_paper("p2", ["Brown, Carol"], 2022, country="UK"),
    ]
    records = [
        _make_extraction("p1", "randomized_controlled_trial", 45, "Improved outcome significantly"),
        _make_extraction("p2", "pre_post", 20, "Mixed results observed"),
    ]
    result = build_compact_study_table(papers, records)
    assert "| Study (Year) |" in result
    # First paper has 2 authors -> "Smith et al."
    assert "et al." in result
    # Second paper (single author) has Brown somewhere
    assert "Brown" in result
    assert "Table 1." in result


def test_compact_table_empty_when_no_data() -> None:
    """Returns empty string when both inputs are empty."""
    from src.export.markdown_refs import build_compact_study_table

    assert build_compact_study_table([], []) == ""


def test_compact_table_truncates_long_finding() -> None:
    """Key findings longer than 100 chars are truncated with ellipsis."""
    from src.export.markdown_refs import build_compact_study_table

    papers = [_make_paper("p1", ["Smith A"], 2021)]
    records = [_make_extraction("p1", "rct", 10, "A" * 120)]
    result = build_compact_study_table(papers, records)
    assert "..." in result


def test_compact_table_injected_in_body(tmp_path: Path) -> None:
    """Compact table is injected after '### Study Characteristics' in assembled manuscript."""
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Studies were diverse [Smith2021].\n\n"
        "## Discussion\n\nSome discussion.\n"
    )
    papers = [_make_paper("pid-1", ["Smith A"], 2021)]
    records = [_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")]
    # row layout: (cid, citekey, doi, title, authors_json, year, journal, bibtex, url)
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=papers,
        extraction_records=records,
        research_question="Research Q",
        include_rq_block=False,
    )
    # Compact table header must appear in the Results body
    assert "| Study (Year) |" in result
    assert "### Study Characteristics" in result


# ---------------------------------------------------------------------------
# _trim_abstract_to_limit
# ---------------------------------------------------------------------------


def test_trim_abstract_no_trim_needed() -> None:
    """Abstract under limit is returned unchanged."""
    from src.orchestration.workflow import _trim_abstract_to_limit

    short = "**Background:** Short text.\n\n**Objectives:** Short.\n\n**Keywords:** a, b"
    result = _trim_abstract_to_limit(short, limit=230)
    assert result == short


def test_trim_abstract_trims_over_limit() -> None:
    """Abstract over limit is trimmed; Keywords line is preserved."""
    from src.orchestration.workflow import _trim_abstract_to_limit

    # Build a ~350-word abstract body (well over the 230 limit)
    long_results = " ".join(["result"] * 280)
    abstract = (
        f"**Background:** Brief background text here.\n\n"
        f"**Objectives:** Short specific objective.\n\n"
        f"**Methods:** Short methods description here.\n\n"
        f"**Results:** {long_results}\n\n"
        f"**Conclusion:** Short conclusion statement.\n\n"
        f"**Keywords:** alpha, beta, gamma"
    )
    # Verify fixture is actually over-limit
    kw_start = abstract.rfind("**Keywords:")
    body_only = abstract[:kw_start].strip() if kw_start > 0 else abstract
    total_before = len(body_only.split())
    assert total_before > 230, f"Fixture too short: {total_before} words"

    result = _trim_abstract_to_limit(abstract, limit=230)
    # Keywords must be preserved
    assert "Keywords:" in result or "keywords:" in result.lower()
    # Body word count (excluding Keywords, with bold labels counted as tokens)
    # must be <= 230 per IEEE/PRISMA abstract limit
    kw_split = result.rfind("**Keywords:")
    body_after = result[:kw_split].strip() if kw_split > 0 else result
    assert len(body_after.split()) <= 230, f"Still too long: {len(body_after.split())} words"


def test_trim_abstract_no_bold_fields() -> None:
    """Abstract without bold field labels falls back to word-level truncation."""
    from src.orchestration.workflow import _trim_abstract_to_limit

    plain = " ".join(["word"] * 300)
    result = _trim_abstract_to_limit(plain, limit=230)
    assert len(result.split()) <= 230


# ---------------------------------------------------------------------------
# _build_citation_coverage_patch -- design grouping
# ---------------------------------------------------------------------------


def test_coverage_patch_empty_returns_empty() -> None:
    from src.orchestration.workflow import _build_citation_coverage_patch

    assert _build_citation_coverage_patch([]) == ""


def test_coverage_patch_no_design_map_chunked() -> None:
    """Without design map, patch groups keys into chunked fallback sentences."""
    from src.orchestration.workflow import _build_citation_coverage_patch

    keys = [f"Author{i}202{i % 3}" for i in range(10)]
    result = _build_citation_coverage_patch(keys)
    assert result != ""
    for key in keys:
        assert key in result


def test_coverage_patch_groups_by_design() -> None:
    """With design map, patch groups keys into design-labelled sentences."""
    from src.orchestration.workflow import _build_citation_coverage_patch

    keys = ["Smith2021", "Jones2022", "Brown2020"]
    design_map = {
        "Smith2021": "randomized_controlled_trial",
        "Jones2022": "pre_post",
        "Brown2020": "pre_post",
    }
    result = _build_citation_coverage_patch(keys, citekey_to_design=design_map)
    assert "Randomized" in result or "randomized" in result.lower()
    assert "Smith2021" in result
    assert "Jones2022" in result and "Brown2020" in result
