from src.models.papers import CandidatePaper, clean_abstract, strip_abstract_markup


def test_strips_jats_paragraphs_and_leading_abstract_title():
    raw = "<jats:title>Abstract</jats:title><jats:p>First   point.</jats:p><jats:p>Second <jats:italic>point</jats:italic>.</jats:p>"
    assert strip_abstract_markup(raw) == "First point.\n\nSecond point."


def test_plain_text_is_unchanged():
    assert strip_abstract_markup("No markup here; a < b stays.") == "No markup here; a < b stays."


def test_comparison_operators_are_not_treated_as_tags():
    assert strip_abstract_markup("<p>p < 0.05 and n > 10</p>") == "p < 0.05 and n > 10"


def test_clean_abstract_decodes_entities_then_strips():
    assert clean_abstract("&lt;jats:p&gt;Caf&amp;eacute; study&lt;/jats:p&gt;") == "Café study"
    assert clean_abstract(None) is None


def test_candidate_paper_cleans_abstract_on_ingest():
    paper = CandidatePaper(title="T", authors=["A"], source_database="crossref", abstract="<jats:p>Hello</jats:p>")
    assert paper.abstract == "Hello"
