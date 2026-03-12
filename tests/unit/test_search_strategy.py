from __future__ import annotations

from src.models import ReviewConfig, ReviewType
from src.search.embase import EmbaseConnector
from src.search.pubmed import PubMedConnector
from src.search.scopus import ScopusConnector
from src.search.strategy import build_database_query
from src.search.web_of_science import WebOfScienceConnector
from src.screening.prompts import _quality_criteria_block


def _review() -> ReviewConfig:
    return ReviewConfig(
        research_question="Does intervention improve outcomes?",
        review_type=ReviewType.SYSTEMATIC,
        pico={
            "population": "adults",
            "intervention": "digital health intervention",
            "comparison": "usual care",
            "outcome": "clinical outcomes",
        },
        keywords=[
            "digital health",
            "telemedicine",
            "remote monitoring",
            "clinical outcomes",
            "adherence",
        ],
        domain="health",
        scope="systematic review scope",
        inclusion_criteria=["primary empirical studies"],
        exclusion_criteria=["secondary reviews"],
        date_range_start=2018,
        date_range_end=2025,
        target_databases=["pubmed", "scopus", "web_of_science", "embase"],
    )


def test_build_database_query_pubmed_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "pubmed")
    assert '"systematic review"[Publication Type]' in query
    assert '"meta-analysis"[Publication Type]' in query
    assert '"review"[Publication Type]' in query


def test_build_database_query_scopus_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "scopus")
    assert "TITLE-ABS-KEY" in query
    assert "AND NOT DOCTYPE(re)" in query


def test_build_database_query_wos_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "web_of_science")
    assert "TS=" in query
    assert "AND NOT DT=Review" in query


def test_build_database_query_embase_primary_only_exclusion() -> None:
    query = build_database_query(_review(), "embase")
    assert "TITLE-ABS-KEY" in query
    assert "AND NOT DOCTYPE(re)" in query


def test_primary_filter_mode_detection() -> None:
    assert PubMedConnector._primary_filter_mode('"x AND "systematic review"[Publication Type]') == "query_exclusion"
    assert PubMedConnector._primary_filter_mode("x") == "screening_only"
    assert ScopusConnector._primary_filter_mode("TITLE-ABS-KEY(x) AND NOT DOCTYPE(re)") == "query_exclusion"
    assert ScopusConnector._primary_filter_mode("TITLE-ABS-KEY(x)") == "screening_only"
    assert WebOfScienceConnector._primary_filter_mode('TS="x" AND NOT DT=Review') == "query_exclusion"
    assert WebOfScienceConnector._primary_filter_mode('TS="x"') == "screening_only"
    assert EmbaseConnector._primary_filter_mode("TITLE-ABS-KEY(x) AND NOT DOCTYPE(re)") == "query_exclusion"
    assert EmbaseConnector._primary_filter_mode("TITLE-ABS-KEY(x)") == "screening_only"


def test_screening_quality_block_preserves_secondary_review_guard() -> None:
    block = _quality_criteria_block()
    assert "secondary review" in block
    assert "Apply these criteria even if database-level query filters were used." in block
