from src.models import CandidatePaper
from src.writing.citation_catalog import _citation_entries_from_papers


def _paper(authors, display_label=None, year=2026):
    return CandidatePaper(
        title="The Physical and Cognitive Benefits of Pickleball Participation in Older Adults",
        authors=authors,
        year=year,
        source_database="openalex",
        display_label=display_label,
    )


def test_citekey_uses_surname_when_display_label_missing() -> None:
    entries = _citation_entries_from_papers([_paper(["Anna Janzen", "Gillian L. Hatfield"])])
    assert entries[0][0] == "Janzen2026"


def test_citekey_matches_db_display_label_path() -> None:
    without_label = _citation_entries_from_papers([_paper(["Sandra C. Webber"], year=2023)])
    with_label = _citation_entries_from_papers([_paper(["Sandra C. Webber"], display_label="Webber", year=2023)])
    assert without_label[0][0] == with_label[0][0] == "Webber2023"
