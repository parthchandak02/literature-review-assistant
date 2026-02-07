"""
Unit tests for state serialization utilities.
"""

from src.extraction.data_extractor_agent import ExtractedData
from src.screening.base_agent import InclusionDecision, ScreeningResult
from src.search.connectors.base import Paper
from src.utils.state_serialization import StateSerializer


class TestStateSerializer:
    """Test state serialization utilities."""

    def test_serialize_deserialize_papers(self):
        """Test Paper serialization and deserialization."""
        papers = [
            Paper(
                title="Test Paper 1",
                abstract="Abstract 1",
                authors=["Author A", "Author B"],
                year=2020,
                doi="10.1000/test1",
                journal="Journal A",
                database="PubMed",
            ),
            Paper(
                title="Test Paper 2",
                abstract="Abstract 2",
                authors=["Author C"],
                year=2021,
            ),
        ]

        # Serialize
        serialized = StateSerializer.serialize_papers(papers)
        assert len(serialized) == 2
        assert serialized[0]["title"] == "Test Paper 1"
        assert serialized[0]["year"] == 2020

        # Deserialize
        deserialized = StateSerializer.deserialize_papers(serialized)
        assert len(deserialized) == 2
        assert deserialized[0].title == "Test Paper 1"
        assert deserialized[0].year == 2020
        assert deserialized[1].title == "Test Paper 2"
        assert deserialized[1].year == 2021

    def test_serialize_deserialize_screening_results(self):
        """Test ScreeningResult serialization and deserialization."""
        results = [
            ScreeningResult(
                decision=InclusionDecision.INCLUDE,
                confidence=0.9,
                reasoning="Relevant paper",
            ),
            ScreeningResult(
                decision=InclusionDecision.EXCLUDE,
                confidence=0.7,
                reasoning="Not relevant",
                exclusion_reason="Wrong topic",
            ),
        ]

        # Serialize
        serialized = StateSerializer.serialize_screening_results(results)
        assert len(serialized) == 2
        assert serialized[0]["decision"] == "include"
        assert serialized[0]["confidence"] == 0.9

        # Deserialize
        deserialized = StateSerializer.deserialize_screening_results(serialized)
        assert len(deserialized) == 2
        assert deserialized[0].decision == InclusionDecision.INCLUDE
        assert deserialized[0].confidence == 0.9
        assert deserialized[1].decision == InclusionDecision.EXCLUDE
        assert deserialized[1].exclusion_reason == "Wrong topic"

    def test_serialize_deserialize_extracted_data(self):
        """Test ExtractedData serialization and deserialization."""
        extracted = [
            ExtractedData(
                title="Test Paper",
                authors=["Author A"],
                year=2020,
                study_objectives=["Objective 1"],
                methodology="Test methodology",
                outcomes=["Outcome 1"],
                key_findings=["Finding 1"],
            ),
        ]

        # Serialize
        serialized = StateSerializer.serialize_extracted_data(extracted)
        assert len(serialized) == 1
        assert serialized[0]["title"] == "Test Paper"

        # Deserialize
        deserialized = StateSerializer.deserialize_extracted_data(serialized)
        assert len(deserialized) == 1
        assert deserialized[0].title == "Test Paper"
        assert deserialized[0].year == 2020
