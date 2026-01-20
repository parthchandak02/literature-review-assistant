"""
State Serialization Utilities

Serialize and deserialize workflow state objects (Paper, ScreeningResult, ExtractedData).
"""

from typing import List, Dict, Any, Optional
from dataclasses import asdict, dataclass
import json
from enum import Enum

from ..search.connectors.base import Paper
from ..screening.base_agent import ScreeningResult, InclusionDecision
from ..extraction.data_extractor_agent import ExtractedData


class StateSerializer:
    """Serialize/deserialize workflow state objects."""

    @staticmethod
    def serialize_papers(papers: List[Paper]) -> List[Dict[str, Any]]:
        """Convert Paper objects to JSON-serializable dicts."""
        return [asdict(paper) for paper in papers]

    @staticmethod
    def deserialize_papers(data: List[Dict[str, Any]]) -> List[Paper]:
        """Convert dicts back to Paper objects."""
        papers = []
        for paper_dict in data:
            # Handle None values for optional fields
            paper = Paper(
                title=paper_dict.get("title", ""),
                abstract=paper_dict.get("abstract", ""),
                authors=paper_dict.get("authors", []),
                year=paper_dict.get("year"),
                doi=paper_dict.get("doi"),
                journal=paper_dict.get("journal"),
                database=paper_dict.get("database"),
                url=paper_dict.get("url"),
                keywords=paper_dict.get("keywords"),
                affiliations=paper_dict.get("affiliations"),
                subjects=paper_dict.get("subjects"),
                country=paper_dict.get("country"),
            )
            papers.append(paper)
        return papers

    @staticmethod
    def serialize_screening_results(results: List[ScreeningResult]) -> List[Dict[str, Any]]:
        """Serialize screening results."""
        serialized = []
        for result in results:
            serialized.append({
                "decision": result.decision.value if isinstance(result.decision, Enum) else result.decision,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "exclusion_reason": result.exclusion_reason,
            })
        return serialized

    @staticmethod
    def deserialize_screening_results(data: List[Dict[str, Any]]) -> List[ScreeningResult]:
        """Deserialize screening results."""
        results = []
        for result_dict in data:
            decision_str = result_dict.get("decision", "exclude")
            # Convert string to InclusionDecision enum
            if isinstance(decision_str, str):
                decision = InclusionDecision(decision_str)
            else:
                decision = decision_str
            
            result = ScreeningResult(
                decision=decision,
                confidence=result_dict.get("confidence", 0.0),
                reasoning=result_dict.get("reasoning", ""),
                exclusion_reason=result_dict.get("exclusion_reason"),
            )
            results.append(result)
        return results

    @staticmethod
    def serialize_extracted_data(data: List[ExtractedData]) -> List[Dict[str, Any]]:
        """Serialize extracted data."""
        return [item.to_dict() for item in data]

    @staticmethod
    def deserialize_extracted_data(data: List[Dict[str, Any]]) -> List[ExtractedData]:
        """Deserialize extracted data."""
        extracted = []
        for item_dict in data:
            extracted_item = ExtractedData(
                title=item_dict.get("title", ""),
                authors=item_dict.get("authors", []),
                year=item_dict.get("year"),
                journal=item_dict.get("journal"),
                doi=item_dict.get("doi"),
                study_objectives=item_dict.get("study_objectives", []),
                methodology=item_dict.get("methodology", ""),
                study_design=item_dict.get("study_design"),
                participants=item_dict.get("participants"),
                interventions=item_dict.get("interventions"),
                outcomes=item_dict.get("outcomes", []),
                key_findings=item_dict.get("key_findings", []),
                limitations=item_dict.get("limitations"),
                country=item_dict.get("country"),
                setting=item_dict.get("setting"),
                sample_size=item_dict.get("sample_size"),
                detailed_outcomes=item_dict.get("detailed_outcomes", []),
                quantitative_results=item_dict.get("quantitative_results"),
                ux_strategies=item_dict.get("ux_strategies", []),
                adaptivity_frameworks=item_dict.get("adaptivity_frameworks", []),
                patient_populations=item_dict.get("patient_populations", []),
                accessibility_features=item_dict.get("accessibility_features", []),
            )
            extracted.append(extracted_item)
        return extracted

    @staticmethod
    def serialize_dict(obj: Any) -> Any:
        """Recursively serialize objects to JSON-compatible types."""
        if isinstance(obj, dict):
            return {k: StateSerializer.serialize_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [StateSerializer.serialize_dict(item) for item in obj]
        elif isinstance(obj, Enum):
            return obj.value
        elif hasattr(obj, "__dict__"):
            return StateSerializer.serialize_dict(obj.__dict__)
        elif hasattr(obj, "to_dict"):
            return obj.to_dict()
        else:
            return obj
