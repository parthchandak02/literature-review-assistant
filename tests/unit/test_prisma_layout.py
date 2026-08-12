"""Unit tests for adaptive PRISMA layout helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.models import PRISMACounts
from src.prisma.diagram import render_prisma_diagram
from src.prisma.layout import compute_next_row_center, compute_start_y_center, row_extent


def test_row_extent_uses_taller_column() -> None:
    bottom, top = row_extent(5.0, 1.0, 2.4)
    assert bottom == 3.8
    assert top == 6.2


def test_compute_start_y_center_pushes_tall_identification_down() -> None:
    short_y = compute_start_y_center(0.8, 0.8, header_y=8.4, header_h=0.3)
    tall_y = compute_start_y_center(2.8, 1.2, header_y=8.4, header_h=0.3)
    assert tall_y < short_y
    _, tall_top = row_extent(tall_y, 2.8, 1.2)
    assert tall_top <= 8.25 - 0.15


def test_compute_next_row_center_respects_vertical_gap() -> None:
    center = compute_next_row_center(4.0, 1.0, 2.0, v_gap=0.6)
    bottom, top = row_extent(center, 1.0, 2.0)
    assert top <= 4.0 - 0.6


def test_render_many_database_sources_without_overlap_regression() -> None:
    """wf-0108-style identification breakdown should render without layout errors."""
    counts = PRISMACounts(
        databases_records={
            "crossref": 500,
            "europepmc": 5,
            "ieee_xplore": 200,
            "openalex": 11,
            "pubmed": 32,
            "scopus": 58,
            "semantic_scholar": 500,
        },
        other_sources_records={},
        total_identified_databases=1306,
        total_identified_other=0,
        duplicates_removed=79,
        automation_excluded=86,
        records_screened=1227,
        records_excluded_screening=1211,
        reports_sought=16,
        reports_not_retrieved=9,
        reports_assessed=7,
        reports_excluded_with_reasons={"None identified": 0},
        studies_included_qualitative=0,
        studies_included_quantitative=7,
        arithmetic_valid=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prisma_many_sources.png"
        result = render_prisma_diagram(counts, str(out))
        assert result.exists()
        assert result.stat().st_size > 10_000
