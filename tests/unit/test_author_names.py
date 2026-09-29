import pytest

from src.models.papers import CandidatePaper, compute_display_label
from src.utils.author_names import family_name, first_author_family


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("Jennifer K. Roth", "Roth"),
        ("J. K. Roth", "Roth"),
        ("Roth, Jennifer K.", "Roth"),
        ("Roth J.", "Roth"),
        ("Roth JK", "Roth"),
        ("Roth J.K.", "Roth"),
        ("Yu, Jennifer", "Yu"),
        ("Zeng, Ziwei", "Zeng"),
        ("van der Berg, Anna", "van der Berg"),
        ("Anna van der Berg", "van der Berg"),
        ("Dr. John Smith Jr.", "Smith"),
        ("Nguyen Van An", "Nguyen"),
        ("Nguyễn Thị Lan", "Nguyễn"),
        ("彭淑敏", "彭淑敏"),
        ("彭 淑敏", "彭"),
        ("Paul McMillan", "McMillan"),
        ({"family": "Roth", "given": "Jennifer"}, "Roth"),
        ("", ""),
    ],
)
def test_family_name(author: object, expected: str) -> None:
    assert family_name(author) == expected


def test_first_author_family_json_array() -> None:
    assert first_author_family('["Yu, Jennifer", "Yendluri, Avanish"]') == ("Yu", True)
    assert first_author_family('["Zeng, Ziwei"]') == ("Zeng", False)
    assert first_author_family(["Jennifer K. Roth"]) == ("Roth", False)
    assert first_author_family("Roth J; Doe K") == ("Roth", True)
    assert first_author_family("") == ("", False)


def test_display_label_uses_family_name() -> None:
    def label(author: str) -> str:
        return compute_display_label(CandidatePaper(title="A trial", authors=[author], source_database="x"))

    assert label("Yu, Jennifer") == "Yu"
    assert label("Roth JK") == "Roth"
    assert label("Paul McMillan") == "McMillan"
