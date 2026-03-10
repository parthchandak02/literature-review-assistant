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


def test_assemble_dedupes_repeated_leading_h1_titles(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = "# A Systematic Review: X\n\n# A Systematic Review: X\n\n## Introduction\n\nHello [Smith2021].\n"
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=_make_mock_citation_rows(),
        research_question="What is the effect of X on Y?",
        title=None,
        include_rq_block=False,
    )
    assert result.count("# A Systematic Review: X") == 1


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
        setting="Hospital, USA",
        title="A test title",
        objectives="Test objectives",
        population="Adults",
        intervention="Treatment X",
        comparison="Control",
        outcomes=[_make_outcome("functional outcome")],
        results_summary={"summary": finding},
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


def test_compact_table_country_falls_back_to_nr() -> None:
    """Missing paper.country renders as NR (no setting-based fallback)."""
    from src.export.markdown_refs import build_compact_study_table

    papers = [_make_paper("p1", ["Smith A"], 2021, country="")]
    records = [_make_extraction("p1", "rct", 10, "Short finding")]
    result = build_compact_study_table(papers, records)
    assert "| NR |" in result


def test_compact_table_key_finding_priority_main_finding() -> None:
    """Falls back to results_summary.main_finding when summary is absent."""
    from src.export.markdown_refs import build_compact_study_table

    papers = [_make_paper("p1", ["Smith A"], 2021)]
    rec = _make_extraction("p1", "rct", 10, "")
    rec.results_summary = {"main_finding": "Main finding used"}
    result = build_compact_study_table(papers, [rec])
    assert "Main finding used" in result


def test_compact_table_reports_truncation_count() -> None:
    """When max_rows truncates output, note must include shown and total counts."""
    from src.export.markdown_refs import build_compact_study_table

    papers = [_make_paper(f"p{i}", [f"Author{i} A"], 2020 + (i % 5)) for i in range(3)]
    records = [_make_extraction(f"p{i}", "rct", 10 + i, f"finding {i}") for i in range(3)]
    result = build_compact_study_table(papers, records, max_rows=2)
    assert "Summary of 2 of 3 included studies" in result


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


def test_assemble_normalizes_inline_subsection_heading_body(tmp_path: Path) -> None:
    """Inline '### Heading body' is split into heading + paragraph."""
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "### Information Sources The systematic search was conducted in 2026.\n\n"
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Information Sources\n\nThe systematic search was conducted in 2026." in result


def test_assemble_normalizes_known_eligibility_heading(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "### Eligibility Criteria Studies were included from 2000 to 2026.\n\n"
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Eligibility Criteria\n\nStudies were included from 2000 to 2026." in result


def test_assemble_normalizes_lowercase_run_on_heading(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "### Eligibility Criteria for this systematic review were predefined.\n\n"
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Eligibility Criteria\n\nfor this systematic review were predefined." in result


def test_assemble_splits_multiple_inline_headings_on_same_line(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "### Eligibility Criteria Studies were included. ### Information Sources The search ran in PubMed.\n\n"
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Eligibility Criteria\n\nStudies were included." in result
    assert "### Information Sources\n\nThe search ran in PubMed." in result


def test_assemble_merges_split_heading_lines(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = "## Results\n\n### Risk of\nBias Assessment\n\nStudy text [Smith2021].\n"
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Risk of Bias Assessment" in result


def test_assemble_merges_split_heading_lines_with_blank_gap(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Results\n\n"
        "### Synthesis of\n\n"
        "Findings This section summarizes outcomes [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "### Synthesis of Findings" in result


def test_assemble_strips_section_block_markers(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "<!-- SECTION_BLOCK:eligibility_criteria -->\n"
        "### Eligibility Criteria\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "SECTION_BLOCK" not in result
    assert "<!--" not in result


def test_assemble_strips_inline_section_block_markers(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    body = (
        "## Methods\n\n"
        "A paragraph. <!-- SECTION_BLOCK:selection_process -->\n"
        "### Selection Process followed predefined eligibility.\n\n"
        "## Results\n\n"
        "### Study Characteristics\n\n"
        "Study text [Smith2021].\n"
    )
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    result = assemble_submission_manuscript(
        body=body,
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    assert "SECTION_BLOCK" not in result
    assert "<!--" not in result


def test_assemble_compact_table_injection_is_idempotent(tmp_path: Path) -> None:
    from src.export.markdown_refs import assemble_submission_manuscript

    base_body = "## Results\n\n### Study Characteristics\n\nStudy text [Smith2021].\n"
    row = (1, "Smith2021", None, "Study", '["Smith A"]', 2021, "J", None, None)
    kwargs = dict(
        manuscript_path=tmp_path / "ms.md",
        artifacts={},
        citation_rows=[row],
        papers=[_make_paper("pid-1", ["Smith A"], 2021)],
        extraction_records=[_make_extraction("pid-1", "randomized_controlled_trial", 30, "Positive result found")],
    )
    out1 = assemble_submission_manuscript(body=base_body, **kwargs)
    out2 = assemble_submission_manuscript(body=out1, **kwargs)
    assert out2.count("See Appendix B for full characteristics.") == 1


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


def test_trim_abstract_iterative_enforcement_never_exceeds_limit() -> None:
    """Sentence-boundary trimming must still converge to <= limit words."""
    from src.orchestration.workflow import _trim_abstract_to_limit

    long_sentence = " ".join(["result"] * 80) + "."
    abstract = (
        f"**Background:** {long_sentence}\n\n"
        f"**Objectives:** {long_sentence}\n\n"
        f"**Methods:** {long_sentence}\n\n"
        f"**Results:** {long_sentence}\n\n"
        f"**Conclusion:** {long_sentence}\n\n"
        f"**Keywords:** alpha, beta"
    )
    out = _trim_abstract_to_limit(abstract, limit=120)
    kw_idx = out.rfind("**Keywords:")
    body = out[:kw_idx].strip() if kw_idx > 0 else out
    assert len(body.split()) <= 120


def test_enforce_prisma_sentence_counts_rewrites_numbers() -> None:
    from src.orchestration.workflow import _enforce_prisma_sentence_counts

    text = (
        "Methods section. Of the 141 reports sought for retrieval, 92 were not "
        "retrieved and 0 were assessed for eligibility, with 141 studies ultimately included."
    )
    out = _enforce_prisma_sentence_counts(text, 141, 92, 49, 141)
    assert "and 141 were assessed for eligibility" in out


def test_enforce_prisma_sentence_counts_rewrites_loose_variant() -> None:
    from src.orchestration.workflow import _enforce_prisma_sentence_counts

    text = (
        "Of 49 reports sought, 0 were not retrieved, 49 were assessed and 141 studies were included. "
        "The remaining details are unchanged."
    )
    out = _enforce_prisma_sentence_counts(text, 141, 92, 49, 141)
    assert "Of the 233 reports sought for retrieval" in out
    assert "and 141 were assessed for eligibility" in out


def test_enforce_prisma_sentence_counts_enforces_invariants() -> None:
    from src.orchestration.workflow import _enforce_prisma_sentence_counts

    text = (
        "Of the 49 reports sought for retrieval, 92 were not retrieved and 49 were assessed "
        "for eligibility, with 141 studies ultimately included."
    )
    out = _enforce_prisma_sentence_counts(text, 49, 92, 49, 141)
    assert "Of the 233 reports sought for retrieval" in out
    assert "92 were not retrieved and 141 were assessed for eligibility" in out


def test_zero_papers_minimal_abstract_contains_all_structured_fields() -> None:
    from src.orchestration.workflow import _build_minimal_sections_for_zero_papers

    out = _build_minimal_sections_for_zero_papers(
        research_question="what works",
        minimal_paragraph="none",
        sections=["abstract", "methods"],
    )
    abstract = out[0]
    for field in ["Background", "Objectives", "Methods", "Results", "Conclusion", "Keywords"]:
        assert f"**{field}:**" in abstract


def test_validate_writing_persistence_invariant_passes_when_all_sections_present() -> None:
    from src.orchestration.workflow import _validate_writing_persistence_invariant

    violated, missing = _validate_writing_persistence_invariant(
        required_sections=["abstract", "introduction", "methods"],
        persisted_sections={"abstract", "introduction", "methods"},
        failed_sections=[],
    )
    assert violated is False
    assert missing == []


def test_validate_writing_persistence_invariant_flags_missing_or_failed_sections() -> None:
    from src.orchestration.workflow import _validate_writing_persistence_invariant

    violated, missing = _validate_writing_persistence_invariant(
        required_sections=["abstract", "introduction", "methods"],
        persisted_sections={"abstract", "introduction"},
        failed_sections=["methods"],
    )
    assert violated is True
    assert missing == ["methods"]


def test_ensure_structured_abstract_adds_missing_fields() -> None:
    from src.writing.orchestration import _ensure_structured_abstract

    abstract = "**Objectives:** Goal.\n\n**Methods:** Method."
    out = _ensure_structured_abstract(abstract, "RQ")
    for field in ["Background", "Objectives", "Methods", "Results", "Conclusion", "Keywords"]:
        assert f"**{field}:**" in out


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


def test_make_citekey_base_sanitizes_display_label_spaces() -> None:
    from src.writing.orchestration import _make_citekey_base

    paper = SimpleNamespace(
        paper_id="p1",
        display_label="Engineering Inclusiv",
        year=2024,
        authors=["Smith A"],
        title="Assistive Study",
    )
    key = _make_citekey_base(paper, 0)
    assert " " not in key
    assert key.startswith("Engineering_Inclus")


def test_convert_to_numbered_citations_resolves_space_key_variant() -> None:
    from src.export.markdown_refs import convert_to_numbered_citations

    body = "Evidence from [Engineering Inclusiv] and [Smith2021]."
    rows = [
        (1, "Engineering_Inclusiv", None, "t1", '["A"]', 2024, "J", None, None),
        (2, "Smith2021", None, "t2", '["B"]', 2021, "J", None, None),
    ]
    out, ordered = convert_to_numbered_citations(body, rows)
    assert "[1]" in out and "[2]" in out
    assert "Engineering Inclusiv" not in out
    assert len(ordered) == 2


def test_sanitize_body_strips_citation_unavailable_placeholder() -> None:
    from src.export.markdown_refs import _sanitize_body

    text = "Some claim (citation unavailable). Another sentence."
    out = _sanitize_body(text)
    assert "(citation unavailable)" not in out


def test_sanitize_body_strips_ref_and_paper_placeholders() -> None:
    from src.export.markdown_refs import _sanitize_body

    text = "Evidence Ref141 remains [Paper_abc123] and [Ref7] in text."
    out = _sanitize_body(text)
    assert "Ref141" not in out
    assert "Paper_abc123" not in out
    assert "[Ref7]" not in out
