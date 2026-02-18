"""Unit tests for export package."""

from __future__ import annotations

import pytest

from src.export.bibtex_builder import build_bibtex
from src.export.ieee_latex import markdown_to_latex
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
    assert "Test Title" in out
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
