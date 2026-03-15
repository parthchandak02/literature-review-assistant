"""Unit tests for export package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.db.database import get_db
from src.export.bibtex_builder import build_bibtex
from src.export.submission_packager import _copy_included_study_pdfs
from src.export.ieee_latex import _convert_citations, _convert_md_table_to_latex, _escape_latex, markdown_to_latex
from src.export.markdown_refs import (
    _normalize_subsection_heading_layout,
    get_existing_figure_entries,
    get_latex_figure_paths,
)
from src.export.ieee_validator import validate_ieee
from src.export.prisma_checklist import validate_prisma


def test_build_bibtex_empty():
    assert build_bibtex([]) == "% No citations\n"


def test_build_bibtex_single():
    citations = [
        ("c1", "Paper1", "10.1234/xyz", "Test Title", '["Author A"]', 2024, "Journal X", None),
    ]
    out = build_bibtex(citations)
    assert "@article{Paper1," in out
    # build_bibtex wraps each title word in braces for case-preservation:
    # "Test Title" -> "{Test} {Title}"
    assert "Test" in out
    assert "Title" in out
    assert "2024" in out


def test_build_bibtex_sanitizes_space_citekey() -> None:
    citations = [
        (1, "Engineering Inclusiv", None, "A title", '["Smith A"]', 2024, "J", None),
    ]
    out = build_bibtex(citations)
    assert "@article{Engineering_Inclusiv," in out


def test_build_bibtex_replaces_internal_paper_key() -> None:
    citations = [
        (1, "Paper_709c9b2024", None, "Assistive Device Study", '["Atallah A"]', 2025, "J", None),
    ]
    out = build_bibtex(citations)
    assert "Paper_709c9b2024" not in out
    assert "@article{Atallah2025," in out


def test_build_bibtex_replaces_ref_numeric_placeholder_key() -> None:
    citations = [
        (1, "Ref141", None, "Assistive Device Study", '["Atallah A"]', 2025, "J", None),
    ]
    out = build_bibtex(citations)
    assert "@article{Ref141," not in out
    assert "@article{Atallah2025," in out


def test_build_bibtex_prunes_uncited_entries() -> None:
    citations = [
        ("c1", "KeyA2023", None, "Title A", '["Author A"]', 2023, "J", None),
        ("c2", "KeyB2024", None, "Title B", '["Author B"]', 2024, "J", None),
    ]
    out = build_bibtex(citations, cited_citekeys={"KeyA2023"})
    assert "KeyA2023" in out
    assert "KeyB2024" not in out


def test_markdown_to_latex_basic():
    md = "**Title:** My Review\n\n**Abstract**\n\nShort abstract.\n\n## Introduction\n\nSome text."
    out = markdown_to_latex(md, citekeys=set())
    assert "\\documentclass" in out
    assert "My Review" in out
    assert "Introduction" in out and ("\\section{" in out or "\\subsection{" in out)


def test_get_figure_entries_and_latex_paths_share_manifest(tmp_path) -> None:
    manuscript = tmp_path / "doc_manuscript.md"
    manuscript.write_text("stub", encoding="utf-8")
    png_path = tmp_path / "fig_prisma_flow.png"
    svg_path = tmp_path / "fig_concept_taxonomy.svg"
    png_path.write_bytes(b"x")
    svg_path.write_bytes(b"y")
    artifacts = {
        "prisma_diagram": str(png_path),
        "concept_taxonomy": str(svg_path),
    }
    entries = get_existing_figure_entries(manuscript, artifacts)
    latex_paths = get_latex_figure_paths(manuscript, artifacts)
    assert len(entries) == 2
    assert "fig_prisma_flow.png" in latex_paths
    assert "fig_concept_taxonomy.svg" not in latex_paths


def test_markdown_to_latex_extracts_structured_abstract_from_background_block() -> None:
    md = (
        "# Test Title\n\n"
        "**Background:** A background sentence.\n"
        "**Objectives:** Objective sentence.\n"
        "**Methods:** Method sentence.\n"
        "**Results:** Results sentence.\n"
        "**Conclusion:** Conclusion sentence.\n"
        "**Keywords:** one, two, three\n\n"
        "## Introduction\n\n"
        "Body text.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\begin{abstract}" in out
    assert "Background" in out


def test_markdown_to_latex_splits_inline_h3_heading_body() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "### Information Sources The systematic search was conducted in 2026.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Information Sources}" in out
    assert "The systematic search was conducted in 2026." in out


def test_markdown_to_latex_splits_inline_h4_heading_body() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "#### Eligibility Details This subsection defines inclusion rules.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsubsection{Eligibility Details}" in out
    assert "This subsection defines inclusion rules." in out


def test_markdown_to_latex_preserves_non_inline_joined_heading() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "### Data Collection Process and Data Items\n"
        "Data extraction was standardized.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Data Collection Process and Data Items}" in out
    assert "\\subsection{Data Collection Process}" not in out


def test_convert_citations_resolves_mixed_list_with_space_key() -> None:
    text = "[Abdallah2017, Engineering Inclusiv, UnknownKey]"
    citekeys = {"Abdallah2017", "Engineering_Inclusiv"}
    out = _convert_citations(text, citekeys)
    assert out == "\\cite{Abdallah2017,Engineering_Inclusiv}"


def test_convert_citations_resolves_single_space_key() -> None:
    text = "Evidence from [Engineering Inclusiv] supports this."
    citekeys = {"Engineering_Inclusiv"}
    out = _convert_citations(text, citekeys)
    assert "\\cite{Engineering_Inclusiv}" in out


def test_convert_citations_rewrites_ref_and_paper_placeholders() -> None:
    text = "Legacy [Ref141] and [Paper_abc123] remain."
    out = _convert_citations(text, set())
    assert "[Ref141]" not in out
    assert "[Paper_abc123]" not in out
    assert "(citation unavailable)" in out


def test_convert_citations_numeric_single_uses_number_map() -> None:
    text = "Evidence [12] supports this."
    out = _convert_citations(text, {"Smith2021"}, {"12": "Smith2021"})
    assert "\\cite{Smith2021}" in out


def test_convert_citations_numeric_list_uses_number_map() -> None:
    text = "Evidence [2, 3] supports this."
    out = _convert_citations(text, {"A2020", "B2021"}, {"2": "A2020", "3": "B2021"})
    assert "\\cite{A2020,B2021}" in out


def test_convert_citations_numeric_with_spaces_and_punctuation() -> None:
    text = "Selection process reports Cohen's kappa = 0.091 [ 1 ]."
    out = _convert_citations(text, {"Cohen1960"}, {"1": "Cohen1960"})
    assert "\\cite{Cohen1960}" in out
    assert "[ 1 ]" not in out


def test_markdown_to_latex_strips_section_block_markers() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "<!-- SECTION_BLOCK:eligibility_criteria -->\n"
        "### Eligibility Criteria\n\n"
        "Study details.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "SECTION_BLOCK" not in out
    assert "<!--" not in out


def test_markdown_to_latex_strips_inline_section_block_markers() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "A paragraph. <!-- SECTION_BLOCK:selection_process -->\n"
        "### Selection Process followed a staged funnel.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "SECTION_BLOCK" not in out
    assert "<!--" not in out


def test_markdown_to_latex_merges_split_h3_heading_lines() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Results\n\n"
        "### Risk of\n"
        "Bias Assessment\n\n"
        "Findings text.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Risk of Bias Assessment}" in out


def test_markdown_to_latex_merges_split_heading_with_blank_line() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Results\n\n"
        "### Synthesis of\n\n"
        "Findings This section summarizes outcomes.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Synthesis of Findings}" in out


def test_markdown_to_latex_splits_lowercase_run_on_heading_body() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "### Eligibility Criteria for this systematic review were predefined.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Eligibility Criteria}" in out
    assert "for this systematic review were predefined." in out


def test_validate_ieee_no_abstract():
    tex = "\\begin{document}\\end{document}"
    bib = ""
    r = validate_ieee(tex, bib)
    assert not r.passed
    assert any("abstract" in e.lower() for e in r.errors)


def test_validate_ieee_accepts_comma_separated_cite_groups() -> None:
    tex = (
        "\\begin{abstract} " + "word " * 170 + "\\end{abstract}\n"
        "Evidence \\cite{Smith2020,Jones2021} and \\cite{Brown2022}."
    )
    bib = (
        "@article{Smith2020,title={A}}\n"
        "@article{Jones2021,title={B}}\n"
        "@article{Brown2022,title={C}}\n"
    )
    result = validate_ieee(tex, bib)
    assert result.passed, result.errors
    assert all("Unresolved citations" not in err for err in result.errors)


def test_validate_ieee_word_count_ignores_latex_command_tokens() -> None:
    tex = (
        "\\begin{abstract} "
        + ("alpha " * 240)
        + "\\cite{Smith2020,Jones2021} "
        + ("beta " * 8)
        + "\\end{abstract}\n"
    )
    bib = "@article{Smith2020,title={A}}\n@article{Jones2021,title={B}}\n"
    result = validate_ieee(tex, bib)
    assert result.passed, result.errors
    assert all("Abstract too long" not in err for err in result.errors)


def test_validate_prisma_basic():
    md = "This systematic review examines objectives and methods. We searched PubMed and MEDLINE."
    r = validate_prisma(None, md)
    assert r.reported_count >= 1
    assert r.items


# ---------------------------------------------------------------------------
# _escape_latex: property-based sustainability tests
#
# These tests use Hypothesis to generate arbitrary Unicode text rather than
# maintaining a hand-picked list of example characters.  The invariant being
# tested is structural ("the output is always ASCII-clean") not example-based
# ("these specific characters map to these specific commands"), which means
# the tests never need updating as new Unicode chars appear in LLM output.
# ---------------------------------------------------------------------------

# Characters the LLM writing model (Gemini) realistically produces:
# - BMP text (most common: Latin, Greek, accented letters, common symbols)
# - Typographic punctuation (smart quotes, dashes)
# Surrogate code points (U+D800-U+DFFF) are excluded because Python strings
# should never contain them -- they are encoding artefacts.
_LLM_TEXT = st.text(
    alphabet=st.characters(
        exclude_categories=("Cs",),  # exclude surrogates
    ),
    min_size=0,
    max_size=200,
)


@given(_LLM_TEXT)
@settings(max_examples=500)
def test_escape_latex_always_ascii_output(text: str) -> None:
    """PROPERTY: _escape_latex(any_unicode) must always produce ASCII-only output.

    This is the key regression guard.  If a new Unicode character appears in
    LLM output that has no LaTeX mapping, the last-resort guard in _escape_latex
    replaces it with [?] and logs a warning rather than silently passing a
    non-ASCII char through to pdflatex.
    """
    result = _escape_latex(text)
    non_ascii = [c for c in result if ord(c) > 126]
    assert non_ascii == [], f"Non-ASCII chars remain in _escape_latex output: {non_ascii!r} (input was: {text!r})"


# ---------------------------------------------------------------------------
# Specific behavioural assertions (NOT example-based, but spec assertions):
# these test the CONTRACT of the function, not specific Unicode codepoints.
# ---------------------------------------------------------------------------


@given(st.just("\u2014"))
def test_escape_latex_emdash_uses_triple_dash(dash: str) -> None:
    """CONTRACT: em-dash must become --- (IEEEtran convention), not \\textemdash."""
    result = _escape_latex(f"word{dash}word")
    assert "---" in result
    assert "\\textemdash" not in result


@given(st.just("\u2013"))
def test_escape_latex_endash_uses_double_dash(dash: str) -> None:
    """CONTRACT: en-dash must become -- (IEEEtran convention), not \\textendash."""
    result = _escape_latex(f"word{dash}word")
    assert "--" in result
    assert "\\textendash" not in result


def test_escape_latex_smart_quotes_use_standard_ligatures() -> None:
    """CONTRACT: smart quotes must become standard LaTeX ligatures, not \\text* commands."""
    assert "``" in _escape_latex("\u201chello\u201d")
    assert "''" in _escape_latex("\u201chello\u201d")
    assert "\\textquotedblleft" not in _escape_latex("\u201c")
    assert "\\textquotedblright" not in _escape_latex("\u201d")


@given(st.from_regex(r"\\(?:cite|textbf|textit|emph)\{[A-Za-z0-9_:]+\}", fullmatch=True))
def test_escape_latex_preserves_latex_commands(cmd: str) -> None:
    """PROPERTY: any \\cite{...} / \\textbf{...} command must survive unchanged.

    Hypothesis generates arbitrary valid LaTeX command strings so we test the
    protect/restore mechanism against a wide variety of citekeys and arguments,
    not just the specific example we happened to encounter in real manuscripts.
    """
    result = _escape_latex(f"prefix {cmd} suffix_word")
    assert cmd in result, f"LaTeX command {cmd!r} was corrupted by _escape_latex.\nOutput: {result!r}"


def test_escape_latex_special_chars_are_escaped() -> None:
    """CONTRACT: the five LaTeX special chars must always be escaped."""
    s = "50% cost & benefit #1 x_y $10"
    result = _escape_latex(s)
    assert "\\%" in result
    assert "\\&" in result
    assert "\\#" in result
    assert "\\_" in result
    assert "\\$" in result


# ---------------------------------------------------------------------------
# Table generation -- tabularx invariants
# ---------------------------------------------------------------------------


def test_md_table_uses_tabularx() -> None:
    """_convert_md_table_to_latex must emit tabularx, never bare tabular."""
    lines = ["| A | B | C |", "|---|---|---|", "| x | y | z |"]
    out = "\n".join(_convert_md_table_to_latex(lines, set(), {}))
    assert "tabularx" in out
    # \end{tabular} (without the 'x') must not appear -- would be malformed
    assert "\\end{tabular}" not in out
    # Table must always fill the full page width
    assert "\\textwidth" in out


def test_md_table_wide_cols_uses_tabcolsep() -> None:
    """Tables with more than 5 columns emit a tabcolsep override."""
    header = "| " + " | ".join(f"H{i}" for i in range(9)) + " |"
    sep = "| " + " | ".join(["---"] * 9) + " |"
    row = "| " + " | ".join(f"v{i}" for i in range(9)) + " |"
    out = "\n".join(_convert_md_table_to_latex([header, sep, row], set(), {}))
    assert "tabcolsep" in out


def test_md_table_narrow_no_tabcolsep() -> None:
    """Tables with 5 or fewer columns do NOT inject a tabcolsep override."""
    lines = ["| A | B | C |", "|---|---|---|", "| x | y | z |"]
    out = "\n".join(_convert_md_table_to_latex(lines, set(), {}))
    assert "tabcolsep" not in out


def test_md_table_arraystretch_always_present() -> None:
    """arraystretch is emitted for all tables regardless of column count."""
    lines = ["| A | B |", "|---|---|", "| 1 | 2 |"]
    out = "\n".join(_convert_md_table_to_latex(lines, set(), {}))
    assert "arraystretch" in out


def test_md_table_empty_returns_empty() -> None:
    """An empty input produces no output without raising."""
    assert _convert_md_table_to_latex([], set(), {}) == []


def test_markdown_to_latex_splits_known_run_on_methods_heading() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Methods\n\n"
        "### Eligibility Criteria Studies were included between 2000 and 2026.\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Eligibility Criteria}" in out
    assert "Studies were included between 2000 and 2026." in out


def test_markdown_to_latex_strips_numeric_citations_from_headings() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Results\n\n"
        "### Synthesis of Findings [6] [8]\n"
    )
    out = markdown_to_latex(md, citekeys={"RefA", "RefB"}, num_to_citekey={"6": "RefA", "8": "RefB"})
    assert "\\subsection{Synthesis of Findings}" in out
    assert "[6]" not in out
    assert "[8]" not in out


def test_markdown_to_latex_trims_oversized_heading_spillover() -> None:
    md = (
        "# Title\n\n"
        "**Background:** Background.\n"
        "**Objectives:** Objective.\n"
        "**Methods:** Methods.\n"
        "**Results:** Results.\n"
        "**Conclusion:** Conclusion.\n"
        "**Keywords:** a, b\n\n"
        "## Results\n\n"
        "### Synthesis of Findings Due to heterogeneity and methodological differences across included studies\n"
    )
    out = markdown_to_latex(md, citekeys=set())
    assert "\\subsection{Synthesis of Findings}" in out


def test_normalize_subsection_heading_layout_joins_connector_with_next_title_line() -> None:
    text = "### Data Collection Process and\n\nData Items\nData extraction was standardized."
    out = _normalize_subsection_heading_layout(text)
    assert "### Data Collection Process and Data Items" in out
    assert "Data extraction was standardized." in out


def test_normalize_subsection_heading_layout_moves_spill_token_into_body() -> None:
    text = "### Synthesis of Findings Due\n\nto heterogeneity, meta-analysis was not feasible."
    out = _normalize_subsection_heading_layout(text)
    assert "### Synthesis of Findings" in out
    assert "Due to heterogeneity, meta-analysis was not feasible." in out


def test_normalize_subsection_heading_layout_splits_such_as_run_on_heading() -> None:
    text = "#### Other Outcomes such as feasibility and utility considerations."
    out = _normalize_subsection_heading_layout(text)
    assert "#### Other Outcomes" in out
    assert "such as feasibility and utility considerations." in out


def test_normalize_subsection_heading_layout_preserves_joined_title_fragment() -> None:
    text = "### Data Collection Process and Data Items"
    out = _normalize_subsection_heading_layout(text)
    assert "### Data Collection Process and Data Items" in out
    assert "\n\nData Items\n" not in out


@pytest.mark.asyncio
async def test_copy_included_study_pdfs_copies_only_included_pdf_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    papers_dir = run_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    (papers_dir / "paper-1.pdf").write_bytes(b"pdf-1")
    (papers_dir / "paper-2.txt").write_text("text-2", encoding="utf-8")
    (papers_dir / "paper-3.pdf").write_bytes(b"pdf-3")

    manifest = {
        "paper-1": {"file_path": str(papers_dir / "paper-1.pdf"), "file_type": "pdf"},
        "paper-2": {"file_path": str(papers_dir / "paper-2.txt"), "file_type": "txt"},
        "paper-3": {"file_path": str(papers_dir / "paper-3.pdf"), "file_type": "pdf"},
    }
    (run_dir / "data_papers_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    workflow_id = "wf-copy-pdfs"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        for paper_id in ("paper-1", "paper-2", "paper-3"):
            await db.execute(
                """
                INSERT INTO papers (paper_id, title, authors, year, source_database, doi, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (paper_id, paper_id, "Author", 2024, "testdb", None, None),
            )
        await db.execute(
            """
            INSERT INTO dual_screening_results
                (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-1", "fulltext", 1, "include", 0),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results
                (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-2", "fulltext", 1, "include", 0),
        )
        await db.execute(
            """
            INSERT INTO dual_screening_results
                (workflow_id, paper_id, stage, agreement, final_decision, adjudication_needed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "paper-3", "fulltext", 1, "exclude", 0),
        )
        await db.commit()

    dst_dir = run_dir / "submission" / "study_pdfs"
    copied = await _copy_included_study_pdfs(str(db_path), workflow_id, run_dir, dst_dir)
    assert copied == 1
    assert (dst_dir / "paper-1.pdf").exists()
    assert not (dst_dir / "paper-2.pdf").exists()
    assert not (dst_dir / "paper-3.pdf").exists()


@pytest.mark.asyncio
async def test_copy_included_study_pdfs_missing_manifest_returns_zero(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "runtime.db"
    workflow_id = "wf-no-manifest"
    async with get_db(str(db_path)) as db:
        await db.execute(
            "INSERT INTO workflows (workflow_id, topic, config_hash, status) VALUES (?, ?, ?, ?)",
            (workflow_id, "Topic", "hash", "completed"),
        )
        await db.commit()
    dst_dir = run_dir / "submission" / "study_pdfs"
    copied = await _copy_included_study_pdfs(str(db_path), workflow_id, run_dir, dst_dir)
    assert copied == 0
    assert dst_dir.exists()
