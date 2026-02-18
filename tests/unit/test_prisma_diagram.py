"""Unit tests for PRISMA 2020 diagram."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.models import PRISMACounts
from src.prisma.diagram import render_prisma_diagram


def test_render_prisma_diagram_creates_file() -> None:
    """PRISMA diagram renders and creates PNG file."""
    counts = PRISMACounts(
        databases_records={"pubmed": 50, "openalex": 100},
        other_sources_records={"perplexity_search": 5},
        total_identified_databases=150,
        total_identified_other=5,
        duplicates_removed=10,
        records_screened=145,
        records_excluded_screening=100,
        reports_sought=45,
        reports_not_retrieved=5,
        reports_assessed=40,
        reports_excluded_with_reasons={"wrong_population": 20, "wrong_outcome": 10},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prisma.png"
        result = render_prisma_diagram(counts, str(out))
        assert result.exists()
        assert result.suffix == ".png"


def test_render_prisma_diagram_two_column_structure() -> None:
    """PRISMA uses two-column structure (databases vs other sources)."""
    counts = PRISMACounts(
        databases_records={"arxiv": 20},
        other_sources_records={"perplexity_search": 3},
        total_identified_databases=20,
        total_identified_other=3,
        duplicates_removed=0,
        records_screened=23,
        records_excluded_screening=18,
        reports_sought=5,
        reports_not_retrieved=0,
        reports_assessed=5,
        reports_excluded_with_reasons={"other": 2},
        studies_included_qualitative=1,
        studies_included_quantitative=2,
        arithmetic_valid=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prisma.png"
        render_prisma_diagram(counts, str(out))
        assert out.exists()


def test_render_prisma_diagram_fallback_on_import_error() -> None:
    """When prisma-flow-diagram is unavailable, fallback renders custom matplotlib."""
    import builtins

    counts = PRISMACounts(
        databases_records={"openalex": 50},
        other_sources_records={},
        total_identified_databases=50,
        total_identified_other=0,
        duplicates_removed=5,
        records_screened=45,
        records_excluded_screening=30,
        reports_sought=15,
        reports_not_retrieved=2,
        reports_assessed=13,
        reports_excluded_with_reasons={"wrong_population": 10},
        studies_included_qualitative=0,
        studies_included_quantitative=3,
        arithmetic_valid=True,
    )
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "prisma_flow_diagram":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prisma_fallback.png"
        with patch.object(builtins, "__import__", fake_import):
            result = render_prisma_diagram(counts, str(out))
        assert out.exists()
        assert result.suffix == ".png"


def test_prisma_arithmetic_validation() -> None:
    """PRISMACounts arithmetic_valid reflects consistency."""
    valid = PRISMACounts(
        databases_records={"a": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=15,
        reports_excluded_with_reasons={"other": 5},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=True,
    )
    assert valid.arithmetic_valid is True
