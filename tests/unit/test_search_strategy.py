"""
Unit tests for search strategy builder.
"""

from src.search.search_strategy import SearchStrategyBuilder, SearchTerm


class TestSearchTerm:
    """Test SearchTerm class."""

    def test_search_term_creation(self):
        """Test creating a SearchTerm."""
        term = SearchTerm(
            main_term="telemedicine",
            synonyms=["telehealth", "remote healthcare"],
            mesh_terms=["Telemedicine"],
        )

        assert term.main_term == "telemedicine"
        assert len(term.synonyms) == 2
        assert term.mesh_terms == ["Telemedicine"]

    def test_search_term_to_query_generic(self):
        """Test converting SearchTerm to generic query."""
        term = SearchTerm(main_term="telemedicine", synonyms=["telehealth"])

        query = term.to_query("generic")
        assert "telemedicine" in query
        assert "telehealth" in query
        assert "OR" in query

    def test_search_term_to_query_pubmed(self):
        """Test converting SearchTerm to PubMed query."""
        term = SearchTerm(
            main_term="telemedicine", synonyms=["telehealth"], mesh_terms=["Telemedicine"]
        )

        query = term.to_query("pubmed")
        assert "telemedicine" in query
        assert "[MeSH Terms]" in query


class TestSearchStrategyBuilder:
    """Test SearchStrategyBuilder class."""

    def test_search_strategy_builder_initialization(self):
        """Test SearchStrategyBuilder initialization."""
        builder = SearchStrategyBuilder()

        assert len(builder.term_groups) == 0
        assert builder.language == "English"

    def test_add_term_group(self):
        """Test adding term group."""
        builder = SearchStrategyBuilder()

        builder.add_term_group(
            main_term="telemedicine", synonyms=["telehealth"], mesh_terms=["Telemedicine"]
        )

        assert len(builder.term_groups) == 1
        assert builder.term_groups[0].main_term == "telemedicine"

    def test_set_date_range(self):
        """Test setting date range."""
        builder = SearchStrategyBuilder()

        builder.set_date_range(start_year=2020, end_year=2023)

        assert builder.date_range == (2020, 2023)

    def test_set_language(self):
        """Test setting language."""
        builder = SearchStrategyBuilder()

        builder.set_language("Spanish")

        assert builder.language == "Spanish"

    def test_build_query_simple(self):
        """Test building simple query."""
        builder = SearchStrategyBuilder()
        builder.add_term_group("telemedicine", ["telehealth"])

        query = builder.build_query()

        assert "telemedicine" in query
        assert "telehealth" in query
        assert "AND" in query or "OR" in query

    def test_build_query_with_date_range(self):
        """Test building query with date range."""
        builder = SearchStrategyBuilder()
        builder.add_term_group("telemedicine", ["telehealth"])
        builder.set_date_range(start_year=2020, end_year=2023)

        query = builder.build_query()

        assert "2020" in query
        assert "2023" in query

    def test_build_query_multiple_groups(self):
        """Test building query with multiple term groups."""
        builder = SearchStrategyBuilder()
        builder.add_term_group("telemedicine", ["telehealth"])
        builder.add_term_group("UX", ["user experience"])

        query = builder.build_query()

        assert "telemedicine" in query
        assert "UX" in query
        assert "AND" in query

    def test_build_database_specific_query_pubmed(self):
        """Test building PubMed-specific query."""
        builder = SearchStrategyBuilder()
        builder.add_term_group("telemedicine", ["telehealth"], mesh_terms=["Telemedicine"])

        query = builder.build_database_specific_query("pubmed")

        assert "telemedicine" in query.lower()

    def test_build_database_specific_query_scopus(self):
        """Test building Scopus-specific query."""
        builder = SearchStrategyBuilder()
        builder.add_term_group("telemedicine", ["telehealth"])

        query = builder.build_database_specific_query("scopus")

        assert "telemedicine" in query.lower()
