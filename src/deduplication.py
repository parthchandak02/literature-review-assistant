"""
Deduplication Module

Removes duplicate studies across databases using fuzzy matching.
"""

import pandas as pd
from typing import List, Optional
from fuzzywuzzy import fuzz
from dataclasses import dataclass
from src.search.database_connectors import Paper


@dataclass
class DeduplicationResult:
    """Result of deduplication process."""

    unique_papers: List[Paper]
    duplicates_removed: int
    duplicate_groups: List[List[int]]  # Groups of duplicate indices


class Deduplicator:
    """Removes duplicate papers using fuzzy matching."""

    def __init__(self, similarity_threshold: int = 85):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Minimum similarity score (0-100) to consider papers duplicates
        """
        self.similarity_threshold = similarity_threshold

    def deduplicate_papers(self, papers: List[Paper]) -> DeduplicationResult:
        """
        Remove duplicates from list of papers with intelligent record prioritization.

        Args:
            papers: List of Paper objects

        Returns:
            DeduplicationResult with unique papers and metadata
        """
        if not papers:
            return DeduplicationResult([], 0, [])

        # Convert to DataFrame for easier manipulation
        df = self._papers_to_dataframe(papers)

        # Find duplicates
        duplicate_groups = self._find_duplicates(df)

        # Keep best paper from each duplicate group using prioritization
        unique_indices = set()
        for group in duplicate_groups:
            best_index = self._select_best_paper(papers, group)
            unique_indices.add(best_index)

        # Add papers that weren't in any duplicate group
        all_indices_in_groups = set()
        for group in duplicate_groups:
            all_indices_in_groups.update(group)

        for i in range(len(papers)):
            if i not in all_indices_in_groups:
                unique_indices.add(i)

        # Create list of unique papers
        unique_papers = [papers[i] for i in sorted(unique_indices)]
        duplicates_removed = len(papers) - len(unique_papers)

        return DeduplicationResult(
            unique_papers=unique_papers,
            duplicates_removed=duplicates_removed,
            duplicate_groups=duplicate_groups,
        )

    def _select_best_paper(self, papers: List[Paper], indices: List[int]) -> int:
        """
        Select the best paper from a duplicate group based on prioritization rules.

        Priority order:
        1. DOI present
        2. Complete abstract
        3. More complete author list
        4. More recent publication date
        5. More authoritative source (PubMed > Semantic Scholar > Crossref > arXiv > Scopus > Others)

        Args:
            papers: List of all papers
            indices: List of indices in the duplicate group

        Returns:
            Index of the best paper
        """
        if len(indices) == 1:
            return indices[0]

        # Database priority (higher number = higher priority)
        db_priority = {
            "PubMed": 6,
            "Semantic Scholar": 5,
            "Crossref": 4,
            "arXiv": 3,
            "Scopus": 2,
        }

        def score_paper(idx: int) -> tuple:
            """Calculate priority score for a paper. Higher is better."""
            paper = papers[idx]

            # Score components (higher is better)
            has_doi = 1 if paper.doi else 0
            has_abstract = 1 if paper.abstract and len(paper.abstract) > 50 else 0
            abstract_length = len(paper.abstract) if paper.abstract else 0
            author_count = len(paper.authors) if paper.authors else 0
            year_score = paper.year if paper.year else 0
            db_score = db_priority.get(paper.database or "", 0)

            # Weighted score
            return (
                has_doi * 1000,  # DOI is most important
                has_abstract * 100,
                abstract_length,  # Longer abstracts preferred
                author_count * 10,
                year_score,  # More recent preferred
                db_score,  # Authoritative source preferred
            )

        # Score all papers in the group
        scored = [(idx, score_paper(idx)) for idx in indices]

        # Sort by score (descending) and return best index
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _papers_to_dataframe(self, papers: List[Paper]) -> pd.DataFrame:
        """Convert list of papers to DataFrame."""
        data = []
        for i, paper in enumerate(papers):
            data.append(
                {
                    "index": i,
                    "title": paper.title.lower() if paper.title else "",
                    "abstract": paper.abstract.lower() if paper.abstract else "",
                    "doi": paper.doi.lower() if paper.doi else "",
                    "authors": "; ".join(paper.authors).lower() if paper.authors else "",
                    "year": paper.year,
                    "journal": paper.journal.lower() if paper.journal else "",
                }
            )
        return pd.DataFrame(data)

    def _find_duplicates(self, df: pd.DataFrame) -> List[List[int]]:
        """Find groups of duplicate papers."""
        duplicate_groups = []
        processed = set()

        for i in range(len(df)):
            if i in processed:
                continue

            current_group = [i]
            current_title = df.iloc[i]["title"]
            current_doi = df.iloc[i]["doi"]

            # Check against remaining papers
            for j in range(i + 1, len(df)):
                if j in processed:
                    continue

                other_title = df.iloc[j]["title"]
                other_doi = df.iloc[j]["doi"]

                # Check DOI match (exact)
                if current_doi and other_doi and current_doi == other_doi:
                    current_group.append(j)
                    processed.add(j)
                    continue

                # Check title similarity
                if current_title and other_title:
                    title_similarity = fuzz.ratio(current_title, other_title)

                    # Also check token set ratio for better matching
                    title_token_similarity = fuzz.token_set_ratio(current_title, other_title)

                    # Check partial ratio for partial matches
                    title_partial_similarity = fuzz.partial_ratio(current_title, other_title)

                    if (
                        title_similarity >= self.similarity_threshold
                        or title_token_similarity >= self.similarity_threshold
                        or title_partial_similarity >= self.similarity_threshold
                    ):
                        # Additional check: compare abstracts if available
                        current_abstract = df.iloc[i]["abstract"]
                        other_abstract = df.iloc[j]["abstract"]

                        if current_abstract and other_abstract:
                            abstract_similarity = fuzz.token_set_ratio(
                                current_abstract[:500],  # First 500 chars
                                other_abstract[:500],
                            )
                            if abstract_similarity >= 70:  # Lower threshold for abstracts
                                current_group.append(j)
                                processed.add(j)
                        else:
                            # If no abstracts, rely on title match
                            current_group.append(j)
                            processed.add(j)

                    # Also check author similarity for additional validation
                    elif title_similarity >= 70:  # Lower threshold for author check
                        current_authors = df.iloc[i]["authors"]
                        other_authors = df.iloc[j]["authors"]

                        if current_authors and other_authors:
                            author_similarity = fuzz.token_set_ratio(current_authors, other_authors)
                            if author_similarity >= 60:  # Author names can vary
                                current_group.append(j)
                                processed.add(j)

            if len(current_group) > 1:
                duplicate_groups.append(current_group)
                processed.update(current_group)

        return duplicate_groups

    def deduplicate_dataframe(
        self, df: pd.DataFrame, title_col: str = "title", doi_col: Optional[str] = "doi"
    ) -> pd.DataFrame:
        """
        Deduplicate a pandas DataFrame.

        Args:
            df: DataFrame with paper data
            title_col: Column name for titles
            doi_col: Column name for DOIs (optional)

        Returns:
            Deduplicated DataFrame
        """
        if len(df) == 0:
            return df

        # Normalize titles
        df = df.copy()
        df["_title_normalized"] = df[title_col].astype(str).str.lower()

        # Find duplicates
        duplicate_groups = []
        processed = set()

        for i in range(len(df)):
            if i in processed:
                continue

            current_group = [i]
            current_title = df.iloc[i]["_title_normalized"]
            current_doi = (
                df.iloc[i][doi_col].astype(str).lower() if doi_col and doi_col in df.columns else ""
            )

            for j in range(i + 1, len(df)):
                if j in processed:
                    continue

                other_title = df.iloc[j]["_title_normalized"]
                other_doi = (
                    df.iloc[j][doi_col].astype(str).lower()
                    if doi_col and doi_col in df.columns
                    else ""
                )

                # Check DOI match
                if current_doi and other_doi and current_doi == other_doi and current_doi != "nan":
                    current_group.append(j)
                    processed.add(j)
                    continue

                # Check title similarity
                if current_title and other_title:
                    similarity = fuzz.ratio(current_title, other_title)
                    if similarity >= self.similarity_threshold:
                        current_group.append(j)
                        processed.add(j)

            if len(current_group) > 1:
                duplicate_groups.append(current_group)
                processed.update(current_group)

        # Keep first paper from each group
        indices_to_keep = set()
        for group in duplicate_groups:
            indices_to_keep.add(group[0])

        # Add papers not in any duplicate group
        all_duplicate_indices = set()
        for group in duplicate_groups:
            all_duplicate_indices.update(group)

        for i in range(len(df)):
            if i not in all_duplicate_indices:
                indices_to_keep.add(i)

        # Drop normalization column and return
        result_df = df.iloc[sorted(indices_to_keep)].copy()
        result_df = result_df.drop(columns=["_title_normalized"], errors="ignore")

        return result_df.reset_index(drop=True)


def deduplicate_papers(papers: List[Paper], similarity_threshold: int = 85) -> DeduplicationResult:
    """
    Convenience function to deduplicate papers.

    Args:
        papers: List of Paper objects
        similarity_threshold: Minimum similarity score (0-100)

    Returns:
        DeduplicationResult
    """
    deduplicator = Deduplicator(similarity_threshold)
    return deduplicator.deduplicate_papers(papers)
