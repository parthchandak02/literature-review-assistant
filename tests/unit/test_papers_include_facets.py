import pytest

from src.web.routers.database_explorer import _parse_papers_include


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        ("", set()),
        ("facets", {"facets"}),
        ("facets,", {"facets"}),
        (" facets ", {"facets"}),
        ("facets,other", {"facets", "other"}),
        ("other,facets", {"other", "facets"}),
    ],
)
def test_parse_papers_include(include: str, expected: set[str]) -> None:
    assert _parse_papers_include(include) == expected
