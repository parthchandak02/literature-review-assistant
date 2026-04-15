from __future__ import annotations

from pathlib import Path

from src.models import CandidatePaper, SourceCategory
from src.visualization.geographic import render_geographic


def _paper(paper_id: str, *, country: str | None, source_database: str = "openalex") -> CandidatePaper:
    return CandidatePaper(
        paper_id=paper_id,
        title=f"Study {paper_id}",
        authors=["Author"],
        year=2024,
        country=country,
        source_database=source_database,
        source_category=SourceCategory.DATABASE,
    )


def test_render_geographic_falls_back_to_database_when_countries_not_reported(tmp_path: Path) -> None:
    output = tmp_path / "geographic.png"
    render_geographic(
        [
            _paper("p1", country="NR", source_database="openalex"),
            _paper("p2", country="unknown", source_database="pubmed"),
        ],
        str(output),
    )
    caption = output.with_suffix(".caption").read_text(encoding="utf-8")
    assert "source database" in caption.lower()


def test_render_geographic_uses_country_chart_when_real_country_present(tmp_path: Path) -> None:
    output = tmp_path / "geographic.png"
    render_geographic(
        [
            _paper("p1", country="Kenya", source_database="openalex"),
            _paper("p2", country=None, source_database="pubmed"),
        ],
        str(output),
    )
    assert output.exists()
    assert not output.with_suffix(".caption").exists()
