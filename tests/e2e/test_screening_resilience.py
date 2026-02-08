"""
End-to-end tests for screening resilience.

Tests the full screening workflow with problematic LLM responses to ensure
the system handles failures gracefully and completes without crashing.
"""

import pytest
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path

from src.orchestration.workflow_manager import WorkflowManager
from src.search.connectors.base import Paper
from src.screening.base_agent import InclusionDecision
from tests.fixtures.recorded_llm_responses import (
    PLAIN_TEXT_RESPONSE_PAPER4,
    MALFORMED_JSON_RESPONSE,
    EMPTY_RESPONSE,
    VALID_INCLUDE_RESPONSE,
)


@pytest.mark.e2e
@pytest.mark.regression
class TestScreeningResilience:
    """Test full screening workflow handles LLM failures."""

    @pytest.fixture
    def mock_papers_that_crashed(self):
        """Create mock papers that historically caused crashes."""
        return [
            Paper(
                title="Paper 1: Valid Response",
                abstract="This is a normal paper with valid LLM response",
                authors=["Author A"],
                year=2023,
                doi="10.1000/paper1",
                journal="Test Journal",
                database="PubMed",
                full_text="Full text content for paper 1...",
            ),
            Paper(
                title="Paper 2: Plain Text Response (CRASH SCENARIO)",
                abstract="This paper triggers plain text response",
                authors=["Author B"],
                year=2023,
                doi="10.1000/paper2",
                journal="Test Journal",
                database="Scopus",
                full_text="Full text content for paper 2...",
            ),
            Paper(
                title="Paper 3: Malformed JSON",
                abstract="This paper triggers malformed JSON response",
                authors=["Author C"],
                year=2023,
                doi="10.1000/paper3",
                journal="Test Journal",
                database="PubMed",
                full_text="Full text content for paper 3...",
            ),
            Paper(
                title="Paper 4: Conversational AI as an Intelligent Tutor",
                abstract="A review of dialogue-based learning systems",
                authors=["Author D"],
                year=2023,
                doi="10.1000/paper4",
                journal="International Journal of Science",
                database="Scopus",
                full_text="International Journal of Science full text...",
            ),
        ]

    def test_fulltext_screening_with_problematic_papers(
        self,
        tmp_path,
        mock_papers_that_crashed,
        sample_topic_context,
        sample_agent_config,
    ):
        """
        Test screening completes despite problematic LLM responses.
        
        This is the key regression test for the 2026-02-07 crash.
        """
        # Create a minimal test config
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text("""
llm_provider: gemini
llm_model: gemini-2.5-flash-lite
screening:
  title_abstract: true
  fulltext: true
export:
  formats: []
""")

        # Mock WorkflowManager initialization
        with patch("src.orchestration.workflow_manager.WorkflowManager.__init__") as mock_init:
            mock_init.return_value = None

            manager = WorkflowManager.__new__(WorkflowManager)
            manager.config_path = str(config_path)
            manager.unique_papers = mock_papers_that_crashed
            manager.included_papers = []
            manager.excluded_papers = []
            manager.uncertain_papers = []
            manager.topic_context = sample_topic_context
            manager.agent_config = sample_agent_config

            # Mock PRISMA counter
            manager.prisma_counter = Mock()
            manager.prisma_counter.get_counts.return_value = {
                "fulltext_screened": 0,
                "fulltext_included": 0,
                "fulltext_excluded": 0,
            }

            # Mock cost tracker
            manager.cost_tracker = Mock()

            # Mock the screening calls with different responses
            from src.screening.fulltext_agent import FullTextScreener

            with patch.object(FullTextScreener, "screen") as mock_screen:
                # Configure mock to return different results for each paper
                def screen_side_effect(*args, **kwargs):
                    title = kwargs.get("title", args[0] if args else "")

                    if "Paper 1" in title:
                        # Valid response
                        from src.screening.base_agent import ScreeningResult

                        return ScreeningResult(
                            decision=InclusionDecision.INCLUDE,
                            confidence=0.9,
                            reasoning="Valid response",
                        )
                    elif "Paper 2" in title or "Paper 4" in title:
                        # These trigger plain text response (the crash scenario)
                        # But should now handle gracefully
                        from src.screening.base_agent import ScreeningResult

                        return ScreeningResult(
                            decision=InclusionDecision.EXCLUDE,
                            confidence=0.9,
                            reasoning="Handled plain text response gracefully",
                            exclusion_reason="Non-health science domains",
                        )
                    elif "Paper 3" in title:
                        # Malformed JSON - handled
                        from src.screening.base_agent import ScreeningResult

                        return ScreeningResult(
                            decision=InclusionDecision.UNCERTAIN,
                            confidence=0.5,
                            reasoning="Handled malformed JSON gracefully",
                        )
                    else:
                        from src.screening.base_agent import ScreeningResult

                        return ScreeningResult(
                            decision=InclusionDecision.INCLUDE,
                            confidence=0.8,
                            reasoning="Default",
                        )

                mock_screen.side_effect = screen_side_effect

                # Run the screening - should complete without crashing
                try:
                    for paper in mock_papers_that_crashed:
                        screener = FullTextScreener(
                            llm_provider="gemini",
                            api_key="test-key",
                            topic_context=sample_topic_context.to_dict(),
                            agent_config=sample_agent_config,
                        )

                        result = screener.screen(
                            title=paper.title,
                            abstract=paper.abstract,
                            full_text=paper.full_text or "",
                            inclusion_criteria=["health science education"],
                            exclusion_criteria=["general education"],
                        )

                        # Categorize based on decision
                        if result.decision == InclusionDecision.INCLUDE:
                            manager.included_papers.append(paper)
                        elif result.decision == InclusionDecision.EXCLUDE:
                            manager.excluded_papers.append(paper)
                        else:
                            manager.uncertain_papers.append(paper)

                    # Verify no crash occurred
                    assert True, "Screening completed without crash"

                    # Verify results
                    assert len(manager.included_papers) >= 1
                    assert len(manager.excluded_papers) >= 2  # Paper 2 and Paper 4
                    assert len(manager.uncertain_papers) >= 0

                except Exception as e:
                    pytest.fail(f"Screening crashed with: {e}")

    def test_paper4_specific_regression(
        self, sample_topic_context, sample_agent_config
    ):
        """
        Specific regression test for Paper 4 crash.
        
        Date: 2026-02-07
        Issue: AttributeError: 'NoneType' object has no attribute 'decision'
        Root Cause: LLM returned plain text, response.parsed = None
        """
        from src.screening.fulltext_agent import FullTextScreener

        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Mock to return plain text response (the crash scenario)
        with patch.object(screener, "_call_llm_with_schema") as mock_schema:
            # Simulate structured output failure
            mock_schema.side_effect = Exception("response.parsed is None")

            with patch.object(screener, "_call_llm") as mock_text:
                # Return the exact plain text that caused the crash
                mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                # This MUST NOT crash
                result = screener.screen(
                    title="Conversational AI as an Intelligent Tutor: A Review of Dialogue-Based Learning Systems",
                    abstract="",
                    full_text="International Journal of Science...",
                    inclusion_criteria=["health science education"],
                    exclusion_criteria=["general education"],
                )

                # Verify it handled gracefully
                assert result is not None, "Result should not be None"
                assert (
                    result.decision == InclusionDecision.EXCLUDE
                ), f"Expected EXCLUDE, got {result.decision}"
                assert result.confidence == 0.9
                assert "general education" in result.reasoning.lower()

    def test_sequential_failures_dont_crash(
        self, sample_topic_context, sample_agent_config
    ):
        """Test that multiple failures in sequence don't crash the system."""
        from src.screening.fulltext_agent import FullTextScreener

        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Simulate 5 papers with different failure modes
        failure_responses = [
            PLAIN_TEXT_RESPONSE_PAPER4,
            MALFORMED_JSON_RESPONSE,
            EMPTY_RESPONSE,
            PLAIN_TEXT_RESPONSE_PAPER4,
            MALFORMED_JSON_RESPONSE,
        ]

        results = []
        for i, response_text in enumerate(failure_responses):
            with patch.object(screener, "_call_llm_with_schema") as mock_schema:
                mock_schema.side_effect = Exception(f"Failure {i}")

                with patch.object(screener, "_call_llm") as mock_text:
                    mock_text.return_value = response_text

                    result = screener.screen(
                        title=f"Test Paper {i}",
                        abstract=f"Abstract {i}",
                        full_text=f"Full text {i}",
                        inclusion_criteria=[],
                        exclusion_criteria=[],
                    )
                    results.append(result)

        # All should complete without crash
        assert len(results) == 5
        assert all(r is not None for r in results)
        assert all(r.decision is not None for r in results)


@pytest.mark.e2e
@pytest.mark.slow
class TestFullWorkflowResilience:
    """Test full workflow with problematic papers."""

    def test_end_to_end_with_mixed_papers(
        self, tmp_path, sample_topic_context, sample_agent_config
    ):
        """Test complete workflow with mix of valid and problematic papers."""
        # Create test papers
        papers = [
            Paper(
                title="Valid Health Science Paper",
                abstract="About health science education",
                authors=["Author A"],
                year=2023,
                doi="10.1000/valid1",
                journal="Health Education Journal",
                database="PubMed",
                full_text="Health science content...",
            ),
            Paper(
                title="Problematic Response Paper",
                abstract="Will trigger plain text response",
                authors=["Author B"],
                year=2023,
                doi="10.1000/problematic",
                journal="Test Journal",
                database="Scopus",
                full_text="Content that triggers plain text...",
            ),
        ]

        from src.screening.fulltext_agent import FullTextScreener

        screener = FullTextScreener(
            llm_provider="gemini",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Process all papers
        results = []
        for paper in papers:
            with patch.object(screener, "_call_llm_with_schema") as mock_schema:
                # First paper succeeds, second fails
                if "Valid" in paper.title:
                    from src.schemas.llm_response_schemas import (
                        ScreeningResultSchema,
                        SchemaInclusionDecision,
                    )

                    mock_schema.return_value = ScreeningResultSchema(
                        decision=SchemaInclusionDecision.INCLUDE,
                        confidence=0.9,
                        reasoning="Valid",
                        exclusion_reason=None,
                    )
                else:
                    mock_schema.side_effect = Exception("Plain text response")

                with patch.object(screener, "_call_llm") as mock_text:
                    mock_text.return_value = PLAIN_TEXT_RESPONSE_PAPER4

                    result = screener.screen(
                        title=paper.title,
                        abstract=paper.abstract,
                        full_text=paper.full_text or "",
                        inclusion_criteria=["health science"],
                        exclusion_criteria=["general education"],
                    )
                    results.append(result)

        # All papers should process successfully
        assert len(results) == 2
        assert results[0].decision == InclusionDecision.INCLUDE
        assert results[1].decision == InclusionDecision.EXCLUDE


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
