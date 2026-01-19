"""
Unit tests for Pydantic schemas.
"""

import pytest
from pydantic import ValidationError
from src.schemas.screening_schemas import (
    ScreeningResultSchema,
    InclusionDecision,
    ScreeningRequestSchema,
)
from src.schemas.extraction_schemas import ExtractedDataSchema, ExtractionRequestSchema


def test_screening_result_schema_valid():
    """Test valid screening result schema."""
    result = ScreeningResultSchema(
        decision=InclusionDecision.INCLUDE,
        confidence=0.85,
        reasoning="Meets inclusion criteria",
        exclusion_reason=None,
    )

    assert result.decision == InclusionDecision.INCLUDE
    assert result.confidence == 0.85
    assert result.reasoning == "Meets inclusion criteria"


def test_screening_result_schema_confidence_bounds():
    """Test confidence bounds validation."""
    # Valid confidence
    result = ScreeningResultSchema(
        decision=InclusionDecision.INCLUDE, confidence=0.5, reasoning="Test"
    )
    assert result.confidence == 0.5

    # Confidence too high (should clamp or raise)
    with pytest.raises(ValidationError):
        ScreeningResultSchema(
            decision=InclusionDecision.INCLUDE,
            confidence=1.5,  # > 1.0
            reasoning="Test",
        )

    # Confidence too low
    with pytest.raises(ValidationError):
        ScreeningResultSchema(
            decision=InclusionDecision.INCLUDE,
            confidence=-0.1,  # < 0.0
            reasoning="Test",
        )


def test_screening_result_schema_exclusion_reason():
    """Test exclusion reason field."""
    result = ScreeningResultSchema(
        decision=InclusionDecision.EXCLUDE,
        confidence=0.8,
        reasoning="Does not meet criteria",
        exclusion_reason="Editorial piece",
    )

    assert result.exclusion_reason == "Editorial piece"


def test_screening_request_schema():
    """Test screening request schema."""
    request = ScreeningRequestSchema(
        title="Test Paper",
        abstract="Test abstract",
        inclusion_criteria=["Criterion 1", "Criterion 2"],
        exclusion_criteria=["Exclusion 1"],
        full_text="Full text content",
    )

    assert request.title == "Test Paper"
    assert len(request.inclusion_criteria) == 2
    assert request.full_text == "Full text content"


def test_extracted_data_schema_valid():
    """Test valid extracted data schema."""
    data = ExtractedDataSchema(
        title="Test Paper",
        authors=["Author 1", "Author 2"],
        year=2022,
        study_objectives=["Objective 1"],
        methodology="RCT",
        outcomes=["Outcome 1"],
        key_findings=["Finding 1"],
    )

    assert data.title == "Test Paper"
    assert len(data.authors) == 2
    assert data.year == 2022


def test_extracted_data_schema_defaults():
    """Test extracted data schema defaults."""
    data = ExtractedDataSchema(title="Test Paper", methodology="Test")

    assert data.authors == []
    assert data.year is None
    assert data.study_objectives == []
    assert data.outcomes == []


def test_extraction_request_schema():
    """Test extraction request schema."""
    request = ExtractionRequestSchema(
        title="Test Paper",
        abstract="Test abstract",
        full_text="Full text",
        extraction_fields=["methodology", "outcomes"],
    )

    assert request.title == "Test Paper"
    assert request.extraction_fields == ["methodology", "outcomes"]


def test_schema_serialization():
    """Test schema serialization to dict/JSON."""
    result = ScreeningResultSchema(
        decision=InclusionDecision.INCLUDE, confidence=0.85, reasoning="Test"
    )

    data = result.model_dump()
    assert data["decision"] == "include"
    assert data["confidence"] == 0.85

    json_str = result.model_dump_json()
    assert "include" in json_str
    assert "0.85" in json_str
