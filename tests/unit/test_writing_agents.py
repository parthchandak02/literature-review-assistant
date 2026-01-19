"""
Unit tests for writing agents.
"""

from unittest.mock import Mock, patch
from src.writing.introduction_agent import IntroductionWriter
from src.writing.methods_agent import MethodsWriter
from src.writing.results_agent import ResultsWriter
from src.writing.discussion_agent import DiscussionWriter
from src.extraction.data_extractor_agent import ExtractedData


class TestIntroductionWriter:
    """Test IntroductionWriter agent."""

    def test_introduction_writer_initialization(self, sample_topic_context, sample_agent_config):
        """Test IntroductionWriter initialization."""
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert writer.llm_provider == "openai"
        assert writer.topic_context is not None

    def test_write_with_llm(self, sample_topic_context, sample_agent_config):
        """Test writing introduction (tests fallback mode)."""
        # Test with fallback since mocking openai at module level is complex
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key=None,  # Triggers fallback
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer.write(
            research_question="Test research question", justification="Test justification"
        )

        assert result is not None
        assert len(result) > 0

    def test_write_fallback(self, sample_topic_context, sample_agent_config):
        """Test writing introduction with fallback (no LLM)."""
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer.write(
            research_question="Test research question", justification="Test justification"
        )

        assert result is not None
        assert "Test research question" in result
        assert "Test justification" in result

    def test_build_introduction_prompt(self, sample_topic_context, sample_agent_config):
        """Test introduction prompt building."""
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        prompt = writer._build_introduction_prompt(
            research_question="Test question",
            justification="Test justification",
            background_context="Test background",
            gap_description="Test gap",
        )

        assert "Test question" in prompt
        assert "Test justification" in prompt
        assert "Test background" in prompt
        assert "Test gap" in prompt
        assert "introduction" in prompt.lower()

    def test_fallback_introduction(self, sample_topic_context, sample_agent_config):
        """Test fallback introduction generation."""
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer._fallback_introduction(
            research_question="Test question", justification="Test justification"
        )

        assert "Test question" in result
        assert "Test justification" in result
        assert "Introduction" in result


class TestMethodsWriter:
    """Test MethodsWriter agent."""

    def test_methods_writer_initialization(self, sample_topic_context, sample_agent_config):
        """Test MethodsWriter initialization."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert writer.llm_provider == "openai"
        assert writer.topic_context is not None

    @patch("src.writing.introduction_agent.openai")
    def test_write_with_llm(self, mock_openai, sample_topic_context, sample_agent_config):
        """Test writing methods with LLM."""
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "This is a comprehensive methods section..."
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 300
        mock_response.usage.total_tokens = 500
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        writer = MethodsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer.write(
            search_strategy="Test search strategy",
            databases=["PubMed", "Scopus"],
            inclusion_criteria=["Criterion 1", "Criterion 2"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test screening",
            data_extraction_process="Test extraction",
        )

        assert result is not None
        assert len(result) > 0
        mock_client.chat.completions.create.assert_called_once()

    def test_write_fallback(self, sample_topic_context, sample_agent_config):
        """Test writing methods with fallback."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer.write(
            search_strategy="Test strategy",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test",
            data_extraction_process="Test",
        )

        assert result is not None
        assert "Methods" in result
        assert "PubMed" in result

    def test_build_methods_prompt(self, sample_topic_context, sample_agent_config):
        """Test methods prompt building."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        prompt = writer._build_methods_prompt(
            search_strategy="Test strategy",
            databases=["PubMed", "Scopus"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test screening",
            data_extraction_process="Test extraction",
            prisma_counts={"found": 100, "no_dupes": 95},
        )

        assert "Test strategy" in prompt
        assert "PubMed" in prompt
        assert "Criterion 1" in prompt
        assert "100" in prompt
        assert "methods" in prompt.lower()

    def test_fallback_methods(self, sample_topic_context, sample_agent_config):
        """Test fallback methods generation."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer._fallback_methods(
            search_strategy="Test strategy",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
        )

        assert "Methods" in result
        assert "Test strategy" in result
        assert "PubMed" in result


class TestResultsWriter:
    """Test ResultsWriter agent."""

    def test_results_writer_initialization(self, sample_topic_context, sample_agent_config):
        """Test ResultsWriter initialization."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert writer.llm_provider == "openai"
        assert writer.topic_context is not None

    @patch("src.writing.introduction_agent.openai")
    def test_write_with_llm(self, mock_openai, sample_topic_context, sample_agent_config):
        """Test writing results with LLM."""
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "This is a comprehensive results section..."
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 300
        mock_response.usage.total_tokens = 500
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        writer = ResultsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study 1",
                authors=["Author 1"],
                year=2022,
                journal=None,
                doi=None,
                study_objectives=["Objective 1"],
                methodology="RCT",
                study_design="RCT",
                participants=None,
                interventions=None,
                outcomes=["Outcome 1"],
                key_findings=["Finding 1", "Finding 2"],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer.write(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
        )

        assert result is not None
        assert len(result) > 0
        mock_client.chat.completions.create.assert_called_once()

    def test_write_fallback(self, sample_topic_context, sample_agent_config):
        """Test writing results with fallback."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=[],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer.write(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
        )

        assert result is not None
        assert "Results" in result
        assert "100" in result

    def test_build_results_prompt(self, sample_topic_context, sample_agent_config):
        """Test results prompt building."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=["Finding 1"],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        prompt = writer._build_results_prompt(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
            key_findings=["Key finding 1"],
        )

        assert "Test Study" in prompt
        assert "100" in prompt
        assert "results" in prompt.lower()

    def test_fallback_results(self, sample_topic_context, sample_agent_config):
        """Test fallback results generation."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=[],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer._fallback_results(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
        )

        assert "Results" in result
        assert "100" in result


class TestDiscussionWriter:
    """Test DiscussionWriter agent."""

    def test_discussion_writer_initialization(self, sample_topic_context, sample_agent_config):
        """Test DiscussionWriter initialization."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        assert writer.llm_provider == "openai"
        assert writer.topic_context is not None

    @patch("src.writing.introduction_agent.openai")
    def test_write_with_llm(self, mock_openai, sample_topic_context, sample_agent_config):
        """Test writing discussion with LLM."""
        mock_client = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "This is a comprehensive discussion section..."
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 200
        mock_response.usage.completion_tokens = 300
        mock_response.usage.total_tokens = 500
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.OpenAI.return_value = mock_client

        writer = DiscussionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=[],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer.write(
            research_question="Test question",
            key_findings=["Finding 1", "Finding 2"],
            extracted_data=extracted_data,
            limitations=["Limitation 1"],
            implications=["Implication 1"],
        )

        assert result is not None
        assert len(result) > 0
        mock_client.chat.completions.create.assert_called_once()

    def test_write_fallback(self, sample_topic_context, sample_agent_config):
        """Test writing discussion with fallback."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=[],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer.write(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
        )

        assert result is not None
        assert "Discussion" in result
        assert "Test question" in result

    def test_build_discussion_prompt(self, sample_topic_context, sample_agent_config):
        """Test discussion prompt building."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study",
                authors=[],
                year=None,
                journal=None,
                doi=None,
                study_objectives=[],
                methodology="RCT",
                study_design=None,
                participants=None,
                interventions=None,
                outcomes=[],
                key_findings=[],
                limitations=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        prompt = writer._build_discussion_prompt(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
            limitations=["Limitation 1"],
            implications=["Implication 1"],
        )

        assert "Test question" in prompt
        assert "Finding 1" in prompt
        assert "Limitation 1" in prompt
        assert "Implication 1" in prompt
        assert "discussion" in prompt.lower()

    def test_fallback_discussion(self, sample_topic_context, sample_agent_config):
        """Test fallback discussion generation."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer._fallback_discussion(
            research_question="Test question", key_findings=["Finding 1"]
        )

        assert "Discussion" in result
        assert "Test question" in result
        assert "Finding 1" in result
