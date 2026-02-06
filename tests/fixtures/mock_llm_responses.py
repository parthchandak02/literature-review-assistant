"""
Mock LLM responses for testing.
"""

from typing import Dict, Any
from unittest.mock import Mock


def create_mock_gemini_response(content: str, tokens: Dict[str, int] = None) -> Mock:
    """
    Create mock Gemini API response.

    Args:
        content: Response content
        tokens: Token usage dict with 'prompt', 'completion', 'total'

    Returns:
        Mock response object
    """
    if tokens is None:
        tokens = {"prompt": 100, "completion": 50, "total": 150}

    mock_response = Mock()
    mock_response.text = content

    # Add usage_metadata
    mock_usage = Mock()
    mock_usage.prompt_token_count = tokens.get("prompt", 100)
    mock_usage.candidates_token_count = tokens.get("completion", 50)
    mock_usage.total_token_count = tokens.get("total", 150)
    mock_response.usage_metadata = mock_usage

    return mock_response


def get_mock_screening_response(decision: str = "include", confidence: float = 0.85) -> str:
    """Get mock screening response in JSON format."""
    return f'''{{
  "decision": "{decision}",
  "confidence": {confidence},
  "reasoning": "Paper meets inclusion criteria",
  "exclusion_reason": null
}}'''


def get_mock_extraction_response() -> str:
    """Get mock extraction response in JSON format."""
    return """{
  "title": "Test Paper",
  "authors": ["Author 1", "Author 2"],
  "year": 2022,
  "journal": "Test Journal",
  "doi": "10.1000/test",
  "study_objectives": ["Objective 1", "Objective 2"],
  "methodology": "Randomized controlled trial",
  "study_design": "RCT",
  "participants": "100 participants",
  "interventions": "Test intervention",
  "outcomes": ["Outcome 1", "Outcome 2"],
  "key_findings": ["Finding 1", "Finding 2"],
  "limitations": "Small sample size",
  "ux_strategies": ["Strategy 1"],
  "adaptivity_frameworks": ["Framework 1"],
  "patient_populations": ["Population 1"],
  "accessibility_features": ["Feature 1"]
}"""


def get_mock_tool_calling_response(tool_name: str, arguments: Dict[str, Any]) -> Mock:
    """Get mock tool calling response."""
    mock_response = Mock()
    mock_tool_call = Mock()
    mock_tool_call.function = Mock()
    mock_tool_call.function.name = tool_name
    mock_tool_call.function.arguments = str(arguments).replace("'", '"')
    mock_tool_call.id = "call_123"

    mock_message = Mock()
    mock_message.tool_calls = [mock_tool_call]
    mock_message.content = None

    mock_choice = Mock()
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    return mock_response
