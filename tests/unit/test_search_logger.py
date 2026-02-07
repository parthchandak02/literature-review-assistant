"""
Unit tests for search logger.
"""

from pathlib import Path

from src.search.database_connectors import Paper
from src.search.search_logger import SearchLogger


class TestSearchLogger:
    """Test SearchLogger class."""

    def test_search_logger_initialization(self, tmp_path):
        """Test SearchLogger initialization."""
        logger = SearchLogger(output_dir=str(tmp_path))

        assert logger.output_dir == Path(tmp_path)
        assert logger.output_dir.exists()
        assert len(logger.search_history) == 0

    def test_start_search(self, tmp_path):
        """Test starting a search."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search(query="test query", database="PubMed", max_results=100)

        assert logger.current_search is not None
        assert logger.current_search["query"] == "test query"
        assert logger.current_search["database"] == "PubMed"

    def test_log_result(self, tmp_path):
        """Test logging search results."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "PubMed")

        papers = [
            Paper(
                title="Paper 1",
                abstract="Abstract 1",
                authors=["Author 1"],
                year=2020,
                doi="10.1000/test1",
            ),
            Paper(title="Paper 2", abstract="Abstract 2", authors=["Author 2"], year=2021),
        ]

        logger.log_result(papers)

        assert logger.current_search["total_found"] == 2
        assert len(logger.current_search["results"]) == 2

    def test_log_result_with_error(self, tmp_path):
        """Test logging search error."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "PubMed")

        error = ValueError("Test error")
        logger.log_result([], error=error)

        assert len(logger.current_search["errors"]) == 1
        assert logger.current_search["errors"][0]["error_type"] == "ValueError"

    def test_finish_search(self, tmp_path):
        """Test finishing a search."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "PubMed")
        logger.log_result([Paper(title="Paper 1", abstract="Abstract", authors=["Author"])])
        logger.finish_search()

        assert logger.current_search is None
        assert len(logger.search_history) == 1

    def test_get_statistics(self, tmp_path):
        """Test getting search statistics."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("query1", "PubMed")
        logger.log_result([Paper(title="Paper 1", abstract="Abstract", authors=["Author"])])
        logger.finish_search()

        logger.start_search("query2", "Scopus")
        logger.log_result([])
        logger.finish_search()

        stats = logger.get_statistics()

        assert stats["total_searches"] == 2
        assert stats["total_results"] == 1

    def test_generate_prisma_report(self, tmp_path):
        """Test generating PRISMA report."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "PubMed")
        logger.log_result([Paper(title="Paper 1", abstract="Abstract", authors=["Author"])])
        logger.finish_search()

        report_path = logger.generate_prisma_report()

        assert report_path.exists()
        assert report_path.suffix == ".json"

    def test_generate_csv_summary(self, tmp_path):
        """Test generating CSV summary."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "PubMed")
        logger.log_result([Paper(title="Paper 1", abstract="Abstract", authors=["Author"])])
        logger.finish_search()

        csv_path = logger.generate_search_summary_csv()

        assert csv_path.exists()
        assert csv_path.suffix == ".csv"
