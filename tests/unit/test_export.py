"""Unit tests for export package."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.export.bibtex_builder import build_bibtex
from src.export.ieee_latex import _convert_md_table_to_latex, _escape_latex, markdown_to_latex
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


def test_markdown_to_latex_basic():
    md = "**Title:** My Review\n\n**Abstract**\n\nShort abstract.\n\n## Introduction\n\nSome text."
    out = markdown_to_latex(md, citekeys=set())
    assert "\\documentclass" in out
    assert "My Review" in out
    assert "Introduction" in out and ("\\section{" in out or "\\subsection{" in out)


def test_validate_ieee_no_abstract():
    tex = "\\begin{document}\\end{document}"
    bib = ""
    r = validate_ieee(tex, bib)
    assert not r.passed
    assert any("abstract" in e.lower() for e in r.errors)


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
