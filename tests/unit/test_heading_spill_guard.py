import pytest

from src.writing.orchestration import _sanitize_section_headings


@pytest.mark.parametrize(
    "heading",
    [
        "Principal Findings",
        "Strengths and Limitations",
        "Comparison with Prior Work",
        "Implications for Practice",
        "Implications for Research",
        "Evidence Gaps",
    ],
)
def test_required_subheadings_are_not_split(heading: str) -> None:
    out = _sanitize_section_headings("discussion", f"### {heading}\n\nBody text.")
    assert out.splitlines()[0] == f"### {heading}"


def test_run_on_prose_still_splits_out_of_heading() -> None:
    out = _sanitize_section_headings(
        "results", "### Study Characteristics The included studies were small and heterogeneous."
    )
    assert out.splitlines()[0] == "### Study Characteristics"
    assert "The included studies were small and heterogeneous." in out
