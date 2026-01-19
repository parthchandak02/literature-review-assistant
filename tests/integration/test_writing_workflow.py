"""
Integration tests for writing workflow.
"""

from unittest.mock import Mock, patch
from src.writing.introduction_agent import IntroductionWriter
from src.writing.methods_agent import MethodsWriter
from src.writing.results_agent import ResultsWriter
from src.writing.discussion_agent import DiscussionWriter
from src.extraction.data_extractor_agent import ExtractedData


class TestWritingWorkflow:
    """Test writing workflow integration."""

    @patch("src.screening.base_agent.openai")
    def test_complete_writing_workflow(
        self, mock_openai, sample_topic_context, sample_agent_config
    ):
        """Test complete writing workflow."""
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Generated section content..."
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 300
        mock_response.usage.total_tokens = 500
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        # Create all writers
        intro_writer = IntroductionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        methods_writer = MethodsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        results_writer = ResultsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        discussion_writer = DiscussionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        # Write sections
        introduction = intro_writer.write(
            research_question="Test question", justification="Test justification"
        )

        methods = methods_writer.write(
            search_strategy="Test strategy",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test screening",
            data_extraction_process="Test extraction",
        )

        extracted_data = [ExtractedData(title="Test Study", methodology="RCT")]

        results = results_writer.write(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
        )

        discussion = discussion_writer.write(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
        )

        # Verify all sections were generated
        assert len(introduction) > 0
        assert len(methods) > 0
        assert len(results) > 0
        assert len(discussion) > 0
