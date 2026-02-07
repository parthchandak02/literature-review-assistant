"""
Mock Paper objects for testing.
"""

from typing import List

from src.search.database_connectors import Paper


def create_mock_papers(count: int = 5) -> List[Paper]:
    """
    Create mock papers for testing.

    Args:
        count: Number of papers to create

    Returns:
        List of Paper objects
    """
    papers = []
    for i in range(count):
        papers.append(
            Paper(
                title=f"Test Paper {i + 1}",
                abstract=f"This is abstract {i + 1} for testing purposes.",
                authors=[f"Author {i + 1}A", f"Author {i + 1}B"],
                year=2020 + (i % 3),
                doi=f"10.1000/test{i + 1}",
                journal=f"Test Journal {i + 1}",
                database=["PubMed", "Scopus", "Web of Science"][i % 3],
                keywords=[f"keyword{i + 1}a", f"keyword{i + 1}b"],
            )
        )
    return papers


def create_duplicate_papers() -> List[Paper]:
    """Create papers with duplicates for deduplication testing."""
    base_paper = Paper(
        title="Adaptive Interface Design",
        abstract="This paper discusses adaptive interfaces.",
        authors=["Smith, J."],
        year=2022,
        doi="10.1000/duplicate",
        journal="Test Journal",
        database="PubMed",
    )

    # Exact duplicate (different database)
    duplicate1 = Paper(
        title="Adaptive Interface Design",
        abstract="This paper discusses adaptive interfaces.",
        authors=["Smith, J."],
        year=2022,
        doi="10.1000/duplicate",  # Same DOI
        journal="Test Journal",
        database="Scopus",  # Different database
    )

    # Similar title (fuzzy match)
    duplicate2 = Paper(
        title="Adaptive Interface Design in Healthcare",
        abstract="This paper discusses adaptive interfaces in healthcare.",
        authors=["Smith, J."],
        year=2022,
        doi=None,  # No DOI
        journal="Test Journal",
        database="Web of Science",
    )

    return [base_paper, duplicate1, duplicate2]


def create_papers_for_screening() -> List[Paper]:
    """Create papers specifically for screening tests."""
    return [
        # Should be included
        Paper(
            title="Telemedicine UX Design for Diverse Populations",
            abstract="This study explores user experience design in telemedicine for diverse patient populations.",
            authors=["Researcher, A."],
            year=2022,
            doi="10.1000/include1",
            journal="UX Journal",
            database="PubMed",
        ),
        # Should be excluded
        Paper(
            title="Technical Implementation of Telemedicine Systems",
            abstract="This paper focuses on technical aspects without user experience considerations.",
            authors=["Engineer, B."],
            year=2021,
            doi="10.1000/exclude1",
            journal="Tech Journal",
            database="Scopus",
        ),
        # Uncertain
        Paper(
            title="Healthcare Interface Design",
            abstract="General interface design in healthcare settings.",
            authors=["Designer, C."],
            year=2020,
            doi="10.1000/uncertain1",
            journal="Design Journal",
            database="PubMed",
        ),
    ]
