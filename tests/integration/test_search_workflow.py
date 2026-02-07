"""
Integration tests for search workflow.
"""

from src.search.cache import SearchCache
from src.search.database_connectors import MockConnector, MultiDatabaseSearcher
from src.search.search_logger import SearchLogger


class TestSearchWorkflow:
    """Test end-to-end search workflow."""

    def test_multi_database_search(self):
        """Test searching across multiple databases."""
        searcher = MultiDatabaseSearcher()
        searcher.add_connector(MockConnector("DB1"))
        searcher.add_connector(MockConnector("DB2"))

        results = searcher.search_all("test query", max_results_per_db=5)

        assert "DB1" in results
        assert "DB2" in results
        assert len(results["DB1"]) > 0
        assert len(results["DB2"]) > 0

    def test_search_with_cache(self, tmp_path):
        """Test search with caching enabled."""
        cache = SearchCache(cache_dir=str(tmp_path), ttl_hours=1)

        # First search - should hit API
        connector = MockConnector("TestDB")
        connector.cache = cache

        results1 = connector.search("test query", max_results=5)

        # Second search - should use cache
        results2 = connector.search("test query", max_results=5)

        assert len(results1) == len(results2)
        assert results1[0].title == results2[0].title

    def test_search_logging(self, tmp_path):
        """Test PRISMA-compliant search logging."""
        logger = SearchLogger(output_dir=str(tmp_path))

        logger.start_search("test query", "TestDB", max_results=10)

        papers = MockConnector("TestDB").search("test query", max_results=5)
        logger.log_result(papers)
        logger.finish_search()

        stats = logger.get_statistics()
        assert stats["total_searches"] == 1
        assert stats["total_results"] == len(papers)

        # Generate report
        report_path = logger.generate_prisma_report()
        assert report_path.exists()

    def test_error_handling_in_workflow(self):
        """Test error handling in search workflow."""
        searcher = MultiDatabaseSearcher()

        # Add connectors that might fail
        searcher.add_connector(MockConnector("DB1"))

        # Should continue even if one fails
        results = searcher.search_all("test query", max_results_per_db=5)

        # At least one database should return results
        assert len(results) > 0
