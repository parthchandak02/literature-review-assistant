"""
Unit tests for Pydantic structured output schemas.

Tests validation logic, field constraints, and error handling for all LLM response schemas.
"""

import pytest
from pydantic import ValidationError

from src.schemas.llm_response_schemas import (
    AbstractResponse,
    DiscussionResponse,
    HumanizationResponse,
    IntroductionResponse,
    MethodsResponse,
    QualityAssessmentResponse,
    QueryBuilderResponse,
    ResultsResponse,
    ScreeningResultSchema,
    SearchStrategyResponse,
    StudyTypeDetectionResponse,
)


class TestScreeningResultSchema:
    """Tests for ScreeningResultSchema validation."""

    def test_valid_screening_response(self):
        """Test that valid screening responses are accepted."""
        response = ScreeningResultSchema(
            decision="include",
            confidence=0.95,
            reasoning="This study directly addresses the research question",
        )
        assert response.decision.value == "include"
        assert response.confidence == 0.95
        assert "research question" in response.reasoning

    def test_confidence_bounds_validation(self):
        """Test that confidence must be between 0.0 and 1.0."""
        # Valid bounds
        ScreeningResultSchema(decision="include", confidence=0.0, reasoning="Test")
        ScreeningResultSchema(decision="include", confidence=1.0, reasoning="Test")

        # Invalid - too high
        with pytest.raises(ValidationError) as exc_info:
            ScreeningResultSchema(decision="include", confidence=1.5, reasoning="Test")
        assert "confidence" in str(exc_info.value).lower()

        # Invalid - negative
        with pytest.raises(ValidationError) as exc_info:
            ScreeningResultSchema(decision="include", confidence=-0.1, reasoning="Test")
        assert "confidence" in str(exc_info.value).lower()

    def test_decision_enum_validation(self):
        """Test that decision must be one of the valid values."""
        # Valid decisions
        ScreeningResultSchema(decision="include", confidence=0.9, reasoning="Test")
        ScreeningResultSchema(decision="exclude", confidence=0.9, reasoning="Test")
        ScreeningResultSchema(decision="uncertain", confidence=0.5, reasoning="Test")

        # Invalid decision
        with pytest.raises(ValidationError):
            ScreeningResultSchema(decision="maybe", confidence=0.5, reasoning="Test")

    def test_exclusion_reason_optional(self):
        """Test that exclusion_reason is optional."""
        response = ScreeningResultSchema(
            decision="include", confidence=0.9, reasoning="Meets criteria"
        )
        assert response.exclusion_reason is None

        response_with_reason = ScreeningResultSchema(
            decision="exclude",
            confidence=0.9,
            reasoning="Does not meet criteria",
            exclusion_reason="Wrong study design",
        )
        assert response_with_reason.exclusion_reason == "Wrong study design"


class TestAbstractResponse:
    """Tests for AbstractResponse validation."""

    def test_valid_abstract_response(self):
        """Test that valid abstract responses are accepted."""
        response = AbstractResponse(
            abstract_content="Background: This study examined telemedicine usability. " * 20,
            word_count=240,
            structured_sections={
                "Background": "Context here",
                "Methods": "Methods here",
                "Results": "Results here",
                "Conclusions": "Conclusions here",
            },
            keywords=["telemedicine", "usability", "accessibility"],
        )
        assert len(response.abstract_content) >= 150
        assert response.word_count == 240
        assert len(response.keywords) == 3

    def test_abstract_min_length_validation(self):
        """Test that abstract must be at least 150 characters."""
        with pytest.raises(ValidationError) as exc_info:
            AbstractResponse(
                abstract_content="Too short",
                word_count=2,
            )
        assert "at least 150 characters" in str(exc_info.value).lower()

    def test_abstract_max_length_validation(self):
        """Test that abstract must not exceed 350 words."""
        # Create a 400-word abstract (should fail)
        long_abstract = " ".join(["word"] * 400)

        with pytest.raises(ValidationError) as exc_info:
            AbstractResponse(
                abstract_content=long_abstract,
                word_count=400,
            )
        assert "at most 350 characters" in str(exc_info.value).lower()

    def test_abstract_word_count_validation(self):
        """Test that word count must match actual content."""
        abstract = "This is a test abstract. " * 10  # ~50 words
        actual_count = len(abstract.split())

        # Should pass with accurate count (within 10-word tolerance)
        AbstractResponse(
            abstract_content=abstract,
            word_count=actual_count,
        )

        # Should fail with significantly mismatched count
        with pytest.raises(ValidationError):
            AbstractResponse(
                abstract_content=abstract,
                word_count=actual_count + 50,  # 50 words off
            )


class TestWritingSectionResponses:
    """Tests for writing section response schemas."""

    def test_introduction_response(self):
        """Test IntroductionResponse validation."""
        response = IntroductionResponse(
            section_content="## Introduction\n\nThis systematic review examines..." * 10,
            key_citations=["Smith2020", "Jones2019"],
            subsection_headers=["Background", "Research Gap"],
            word_count=450,
            research_gap_identified=True,
            background_coverage="comprehensive",
        )
        assert response.research_gap_identified is True
        assert response.background_coverage == "comprehensive"

    def test_methods_response(self):
        """Test MethodsResponse validation."""
        response = MethodsResponse(
            section_content="## Methods\n\nWe conducted a systematic review..." * 10,
            key_citations=["PRISMA2020"],
            subsection_headers=["Search Strategy", "Screening"],
            word_count=500,
            methodology_clarity="clear",
            reproducibility_score=0.95,
        )
        assert response.methodology_clarity == "clear"
        assert 0.0 <= response.reproducibility_score <= 1.0

    def test_results_response(self):
        """Test ResultsResponse validation."""
        response = ResultsResponse(
            section_content="## Results\n\nWe identified 23 studies..." * 10,
            key_citations=["Study1", "Study2"],
            subsection_headers=["Search Results", "Study Characteristics"],
            word_count=600,
            tables_mentioned=["Table 1", "Table 2"],
            figures_mentioned=["Figure 1"],
            statistical_tests_reported=True,
        )
        assert len(response.tables_mentioned) == 2
        assert response.statistical_tests_reported is True

    def test_discussion_response(self):
        """Test DiscussionResponse validation."""
        response = DiscussionResponse(
            section_content="## Discussion\n\nOur findings suggest..." * 10,
            key_citations=["Smith2020"],
            subsection_headers=["Main Findings", "Limitations"],
            word_count=700,
            limitations_addressed=True,
            future_directions_provided=True,
            implications_discussed=True,
        )
        assert response.limitations_addressed is True
        assert response.future_directions_provided is True

    def test_section_content_min_length(self):
        """Test that all section content must be at least 100 characters."""
        with pytest.raises(ValidationError):
            IntroductionResponse(
                section_content="Too short",  # < 100 chars
                key_citations=[],
                subsection_headers=[],
                word_count=2,
            )


class TestHumanizationResponse:
    """Tests for HumanizationResponse validation."""

    def test_valid_humanization_response(self):
        """Test valid humanization response."""
        response = HumanizationResponse(
            humanized_content="The findings suggest that telemedicine platforms..." * 10,
            changes_made=["Replaced passive voice", "Added transitions"],
            naturalness_score_before=0.65,
            naturalness_score_after=0.88,
            tone_adjustments=["reduced formality", "improved flow"],
        )
        assert response.naturalness_score_after > response.naturalness_score_before
        assert len(response.changes_made) == 2

    def test_naturalness_score_bounds(self):
        """Test that naturalness scores must be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            HumanizationResponse(
                humanized_content="Test content here that is long enough for validation" * 5,
                changes_made=["test"],
                naturalness_score_before=1.5,  # Invalid
                naturalness_score_after=0.9,
                tone_adjustments=[],
            )

    def test_naturalness_must_improve_or_maintain(self):
        """Test that naturalness score must not decrease."""
        with pytest.raises(ValidationError) as exc_info:
            HumanizationResponse(
                humanized_content="Test content here that is long enough for validation" * 5,
                changes_made=["test"],
                naturalness_score_before=0.8,
                naturalness_score_after=0.6,  # Decreased - invalid!
                tone_adjustments=[],
            )
        assert "should be" in str(exc_info.value).lower()


class TestQualityAssessmentResponse:
    """Tests for QualityAssessmentResponse validation."""

    def test_valid_quality_assessment(self):
        """Test valid quality assessment response."""
        response = QualityAssessmentResponse(
            overall_quality="moderate",
            casp_scores={
                "clearly_focused_question": "yes",
                "appropriate_method": "yes",
                "acceptable_recruitment": "unclear",
            },
            risk_of_bias="moderate",
            recommendations=["Interpret with caution"],
            strengths=["Rigorous methodology"],
            limitations=["Small sample size"],
            confidence_in_findings="moderate",
        )
        assert response.overall_quality == "moderate"
        assert len(response.casp_scores) == 3

    def test_casp_scores_validation(self):
        """Test that CASP scores must use valid values."""
        # Valid scores
        response = QualityAssessmentResponse(
            overall_quality="high",
            casp_scores={
                "criterion1": "yes",
                "criterion2": "no",
                "criterion3": "unclear",
                "criterion4": "not_applicable",
            },
            risk_of_bias="low",
            confidence_in_findings="high",
        )
        assert len(response.casp_scores) == 4

        # Invalid score value
        with pytest.raises(ValidationError):
            QualityAssessmentResponse(
                overall_quality="high",
                casp_scores={
                    "criterion1": "maybe",  # Invalid!
                },
                risk_of_bias="low",
                confidence_in_findings="high",
            )


class TestStudyTypeDetectionResponse:
    """Tests for StudyTypeDetectionResponse validation."""

    def test_valid_study_type_detection(self):
        """Test valid study type detection response."""
        response = StudyTypeDetectionResponse(
            study_type="randomized_controlled_trial",
            casp_checklist="casp_rct",
            confidence=0.95,
            reasoning="Study mentions randomization, control group, and intervention",
            key_indicators=["Random allocation", "Control group", "Blinded assessment"],
        )
        assert response.study_type == "randomized_controlled_trial"
        assert response.casp_checklist == "casp_rct"
        assert response.confidence == 0.95

    def test_confidence_validation(self):
        """Test confidence score validation."""
        with pytest.raises(ValidationError):
            StudyTypeDetectionResponse(
                study_type="cohort_study",
                casp_checklist="casp_cohort",
                confidence=1.5,  # Invalid
                reasoning="Test reasoning here with more than thirty characters",
            )

    def test_reasoning_min_length(self):
        """Test that reasoning must be at least 30 characters."""
        with pytest.raises(ValidationError):
            StudyTypeDetectionResponse(
                study_type="cohort_study",
                casp_checklist="casp_cohort",
                confidence=0.9,
                reasoning="Too short",  # < 30 chars
            )


class TestSearchStrategyResponse:
    """Tests for SearchStrategyResponse validation."""

    def test_valid_search_strategy(self):
        """Test valid search strategy response."""
        response = SearchStrategyResponse(
            search_terms=["telemedicine", "user experience", "accessibility"],
            boolean_operators=["AND", "OR"],
            search_string="(telemedicine OR telehealth) AND (user experience)",
            databases_recommended=["PubMed", "Scopus"],
            expected_results=250,
            search_rationale="Broad terms combined with specific focus on accessibility",
        )
        assert len(response.search_terms) >= 3
        assert response.expected_results == 250

    def test_search_terms_min_length(self):
        """Test that at least 3 search terms are required."""
        with pytest.raises(ValidationError):
            SearchStrategyResponse(
                search_terms=["term1", "term2"],  # Only 2 terms
                search_string="term1 AND term2",
                search_rationale="Test rationale here with enough characters",
            )

    def test_expected_results_positive(self):
        """Test that expected_results must be positive if provided."""
        with pytest.raises(ValidationError):
            SearchStrategyResponse(
                search_terms=["term1", "term2", "term3"],
                search_string="term1 AND term2 AND term3",
                expected_results=-10,  # Invalid
                search_rationale="Test rationale here with enough characters",
            )


class TestQueryBuilderResponse:
    """Tests for QueryBuilderResponse validation."""

    def test_valid_query_builder(self):
        """Test valid query builder response."""
        response = QueryBuilderResponse(
            optimized_query="(telemedicine[MeSH] OR telehealth) AND usability",
            query_components={
                "primary_concept": ["telemedicine", "telehealth"],
                "secondary_concept": ["usability", "user experience"],
            },
            filters_suggested={"date_range": "2018-2024", "publication_type": "Journal Article"},
            expansion_terms=["remote healthcare", "digital health"],
        )
        assert len(response.optimized_query) >= 10
        assert "telemedicine" in response.optimized_query
        assert len(response.query_components) == 2


class TestFieldConstraints:
    """Test field constraints across all schemas."""

    def test_min_length_fields(self):
        """Test that min_length constraints are enforced."""
        # ScreeningResultSchema reasoning
        with pytest.raises(ValidationError):
            ScreeningResultSchema(decision="include", confidence=0.9, reasoning="")

        # AbstractResponse content
        with pytest.raises(ValidationError):
            AbstractResponse(abstract_content="Short", word_count=1)

    def test_default_values(self):
        """Test that default values work correctly."""
        response = ScreeningResultSchema(decision="include", confidence=0.9, reasoning="Valid")
        assert response.exclusion_reason is None  # Default

        response = IntroductionResponse(
            section_content="Test content here with more than one hundred characters" * 3,
            key_citations=[],
            subsection_headers=[],
            word_count=100,
        )
        assert response.research_gap_identified is True  # Default
        assert response.background_coverage == "adequate"  # Default

    def test_list_field_defaults(self):
        """Test that list fields default to empty lists."""
        response = AbstractResponse(
            abstract_content="Background: Test. " * 20,
            word_count=40,
        )
        assert response.keywords == []
        assert response.structured_sections == {}


class TestSchemaValidation:
    """Test validation logic in schemas."""

    def test_abstract_word_count_tolerance(self):
        """Test that abstract word count has 10-word tolerance."""
        abstract = "word " * 50  # 50 words

        # Within tolerance (should pass)
        AbstractResponse(abstract_content=abstract, word_count=55)  # +5 words
        AbstractResponse(abstract_content=abstract, word_count=45)  # -5 words

        # Outside tolerance (should fail)
        with pytest.raises(ValidationError):
            AbstractResponse(abstract_content=abstract, word_count=70)  # +20 words

    def test_casp_scores_valid_values(self):
        """Test that CASP scores only accept valid values."""
        # Valid values
        QualityAssessmentResponse(
            overall_quality="high",
            casp_scores={"q1": "yes", "q2": "no", "q3": "unclear", "q4": "not_applicable"},
            risk_of_bias="low",
            confidence_in_findings="high",
        )

        # Invalid value
        with pytest.raises(ValidationError):
            QualityAssessmentResponse(
                overall_quality="high",
                casp_scores={"q1": "invalid_value"},
                risk_of_bias="low",
                confidence_in_findings="high",
            )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_optional_fields(self):
        """Test that optional fields can be None or empty."""
        response = ScreeningResultSchema(
            decision="include",
            confidence=0.9,
            reasoning="Valid reasoning",
            exclusion_reason=None,
        )
        assert response.exclusion_reason is None

    def test_field_type_coercion(self):
        """Test that Pydantic coerces types where appropriate."""
        # String to enum
        response = ScreeningResultSchema(
            decision="include",  # String -> Enum
            confidence=0.9,
            reasoning="Test",
        )
        assert hasattr(response.decision, "value")

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored by default."""
        response = ScreeningResultSchema(
            decision="include",
            confidence=0.9,
            reasoning="Test",
            extra_field="should be ignored",  # Extra field
        )
        assert not hasattr(response, "extra_field")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
