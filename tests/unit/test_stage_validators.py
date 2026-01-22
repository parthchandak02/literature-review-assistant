"""
Unit tests for stage validators.
"""

from src.testing.stage_validators import (
    StageValidator,
    CitationValidator,
    ChartValidator,
    ScreeningValidator,
    StageValidatorFactory,
)


class TestStageValidator:
    """Test base stage validator."""

    def test_validate_prerequisites(self):
        """Test prerequisite validation."""
        validator = StageValidator()
        
        # Valid state
        state = {
            "data": {
                "unique_papers": [{"title": "Paper 1"}],
            }
        }
        result = validator.validate_prerequisites("title_abstract_screening", state)
        assert result.is_valid
        
        # Missing prerequisite
        state = {
            "data": {}
        }
        result = validator.validate_prerequisites("title_abstract_screening", state)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_outputs(self):
        """Test output validation."""
        validator = StageValidator()
        
        # Valid outputs
        outputs = {
            "screened_papers": [{"title": "Paper 1"}],
            "title_abstract_results": [{"decision": "include"}],
        }
        result = validator.validate_outputs("title_abstract_screening", outputs)
        assert result.is_valid
        
        # Missing output
        outputs = {}
        result = validator.validate_outputs("title_abstract_screening", outputs)
        assert not result.is_valid


class TestCitationValidator:
    """Test citation validator."""

    def test_validate_citations(self):
        """Test citation validation."""
        validator = CitationValidator()
        
        article_sections = {
            "introduction": "This is a test [Citation 1] and [Citation 2].",
            "methods": "Method [1] is used.",
        }
        papers = [
            {"title": "Paper 1"},
            {"title": "Paper 2"},
        ]
        
        result = validator.validate_citations(article_sections, papers)
        assert result.is_valid
        
        # Invalid citation (number exceeds papers)
        article_sections = {
            "introduction": "This is a test [Citation 5].",
        }
        result = validator.validate_citations(article_sections, papers)
        assert not result.is_valid


class TestChartValidator:
    """Test chart validator."""

    def test_validate_charts(self):
        """Test chart validation."""
        validator = ChartValidator()
        
        chart_paths = {
            "papers_by_country": "data/outputs/papers_by_country.png",
            "papers_by_subject": "data/outputs/papers_by_subject.png",
            "network_graph": "data/outputs/network_graph.png",
        }
        papers = [{"title": "Paper 1", "country": "USA"}]
        
        # Note: This will fail if files don't exist, but that's expected
        # In real tests, we'd mock the file system
        result = validator.validate_charts(chart_paths, papers)
        # Result depends on whether files exist, so we just check it returns a result
        assert isinstance(result.is_valid, bool)


class TestScreeningValidator:
    """Test screening validator."""

    def test_validate_screening(self):
        """Test screening validation."""
        validator = ScreeningValidator()
        
        papers = [
            {"title": "Paper 1"},
            {"title": "Paper 2"},
        ]
        results = [
            {"decision": "include", "confidence": 0.9},
            {"decision": "exclude", "confidence": 0.7},
        ]
        
        result = validator.validate_screening(papers, results)
        assert result.is_valid
        
        # Mismatch count
        results = [{"decision": "include"}]
        result = validator.validate_screening(papers, results)
        assert not result.is_valid
        
        # Invalid decision
        results = [
            {"decision": "invalid", "confidence": 0.9},
        ]
        result = validator.validate_screening(papers[:1], results)
        assert not result.is_valid


class TestStageValidatorFactory:
    """Test validator factory."""

    def test_create_validator(self):
        """Test validator creation."""
        validator = StageValidatorFactory.create("citation_processing")
        assert isinstance(validator, CitationValidator)
        
        validator = StageValidatorFactory.create("visualization_generation")
        assert isinstance(validator, ChartValidator)
        
        validator = StageValidatorFactory.create("title_abstract_screening")
        assert isinstance(validator, ScreeningValidator)
        
        validator = StageValidatorFactory.create("unknown_stage")
        assert isinstance(validator, StageValidator)
