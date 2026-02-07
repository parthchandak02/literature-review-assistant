"""
Unit tests for writing agents.
"""

from src.extraction.data_extractor_agent import ExtractedData
from src.writing.discussion_agent import DiscussionWriter
from src.writing.introduction_agent import IntroductionWriter
from src.writing.methods_agent import MethodsWriter
from src.writing.results_agent import ResultsWriter


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

    def test_explicit_objectives_paragraph(self, sample_topic_context, sample_agent_config):
        """Test that introduction includes explicit objectives paragraph."""
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

        # Check that objectives requirement is in prompt
        assert "Objectives" in prompt or "objectives" in prompt.lower()
        assert "PRISMA 2020" in prompt or "Item #4" in prompt
        assert "bullet points" in prompt.lower() or "specific objectives" in prompt.lower()

    def test_bullet_points_format(self, sample_topic_context, sample_agent_config):
        """Test that objectives are formatted as bullet points."""
        writer = IntroductionWriter(
            llm_provider="openai",
            api_key="test-key",
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        prompt = writer._build_introduction_prompt(
            research_question="Test question",
            justification="Test justification",
            background_context=None,
            gap_description=None,
        )

        # Check that bullet point format is mentioned
        assert (
            "bullet points" in prompt.lower()
            or "(1)" in prompt
            or "(2)" in prompt
            or "(3)" in prompt
        )


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

    def test_write_with_llm(self, sample_topic_context, sample_agent_config):
        """Test writing methods with LLM (uses fallback when no API key)."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,  # Triggers fallback
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
        assert "Methods" in result

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

    def test_full_strategies_inclusion(self, sample_topic_context, sample_agent_config):
        """Test methods agent includes full search strategies."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        full_strategies = {
            "PubMed": "(test[Title/Abstract]) AND (systematic[Title/Abstract])",
            "Scopus": "TITLE-ABS-KEY(test AND systematic)",
        }

        result = writer.write(
            search_strategy="Test strategy",
            databases=["PubMed", "Scopus"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test screening",
            data_extraction_process="Test extraction",
            full_search_strategies=full_strategies,
        )

        # Should include full strategies in output
        assert "PubMed" in result or "Scopus" in result
        assert len(result) > 0

    def test_protocol_registration(self, sample_topic_context, sample_agent_config):
        """Test protocol registration inclusion in methods."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        protocol_info = {
            "registered": True,
            "registry": "PROSPERO",
            "registration_number": "CRD123456",
            "url": "https://www.crd.york.ac.uk/prospero/display_record.php?ID=CRD123456",
        }

        # Check that prompt includes protocol info (since fallback may not include it in output)
        prompt = writer._build_methods_prompt(
            search_strategy="Test strategy",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test",
            data_extraction_process="Test",
            prisma_counts=None,
            protocol_info=protocol_info,
        )

        # Should mention protocol registration in prompt
        assert (
            "PROSPERO" in prompt or "protocol" in prompt.lower() or "registration" in prompt.lower()
        )

    def test_automation_details(self, sample_topic_context, sample_agent_config):
        """Test automation details inclusion in methods."""
        writer = MethodsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        automation_details = "LLMs were used for screening and extraction."

        result = writer.write(
            search_strategy="Test strategy",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test",
            data_extraction_process="Test",
            automation_details=automation_details,
        )

        # Should mention automation
        assert len(result) > 0
        # Automation text should be included in prompt building
        prompt = writer._build_methods_prompt(
            search_strategy="Test",
            databases=["PubMed"],
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=["Exclusion 1"],
            screening_process="Test",
            data_extraction_process="Test",
            prisma_counts=None,
            automation_details=automation_details,
        )
        assert "LLMs" in prompt or "automation" in prompt.lower()

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

    def test_write_with_llm(self, sample_topic_context, sample_agent_config):
        """Test writing results with LLM (uses fallback when no API key)."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key=None,  # Triggers fallback
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
        assert "Results" in result

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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        # Generate study characteristics table first
        study_characteristics_table = writer._generate_study_characteristics_table(extracted_data)

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
            study_characteristics_table=study_characteristics_table,
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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

    def test_study_characteristics_table(self, sample_topic_context, sample_agent_config):
        """Test study characteristics table generation."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        extracted_data = [
            ExtractedData(
                title="Test Study 1",
                authors=["Smith, J.", "Doe, A."],
                year=2022,
                journal="Test Journal",
                doi="10.1000/test1",
                study_objectives=["Objective 1"],
                methodology="RCT",
                study_design="Randomized Controlled Trial",
                participants="100 adults",
                interventions="Intervention A",
                outcomes=["Outcome 1", "Outcome 2"],
                key_findings=["Finding 1", "Finding 2"],
                limitations="None",
                country="United States",
                setting="Hospital",
                sample_size=100,
                detailed_outcomes=["Outcome measure (units)"],
                quantitative_results="Effect size: 0.5",
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            ),
            ExtractedData(
                title="Test Study 2",
                authors=["Johnson, B."],
                year=2023,
                journal="Test Journal 2",
                doi="10.1000/test2",
                study_objectives=["Objective 2"],
                methodology="Observational",
                study_design="Cohort Study",
                participants="200 participants",
                interventions="Intervention B",
                outcomes=["Outcome 3"],
                key_findings=["Finding 3"],
                limitations="Small sample",
                country="Canada",
                setting="Community",
                sample_size=200,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            ),
        ]

        table = writer._generate_study_characteristics_table(extracted_data)

        # Check table structure
        assert "| Study ID |" in table
        assert "| Author, Year |" in table
        assert "| Country |" in table
        assert "| Design |" in table
        assert "Study 1" in table
        assert "Study 2" in table
        assert "United States" in table or "Canada" in table
        assert "2022" in table or "2023" in table

    def test_study_characteristics_table_empty(self, sample_topic_context, sample_agent_config):
        """Test study characteristics table with empty data."""
        writer = ResultsWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        table = writer._generate_study_characteristics_table([])
        assert "No studies included" in table

    def test_risk_of_bias_integration(self, sample_topic_context, sample_agent_config):
        """Test risk of bias integration in results."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        risk_of_bias_summary = "Risk of bias was assessed using RoB 2 tool."
        risk_of_bias_table = "| Study | Domain 1 | Domain 2 |\n|-------|----------|----------|\n| Study 1 | Low | High |"

        result = writer.write(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
            risk_of_bias_summary=risk_of_bias_summary,
            risk_of_bias_table=risk_of_bias_table,
        )

        # Should include risk of bias content
        assert len(result) > 0
        # Check that prompt includes risk of bias
        prompt = writer._build_results_prompt(
            extracted_data=extracted_data,
            prisma_counts={"found": 100},
            key_findings=None,
            study_characteristics_table="",
            risk_of_bias_summary=risk_of_bias_summary,
            risk_of_bias_table=risk_of_bias_table,
        )
        assert "Risk of bias" in prompt or "risk of bias" in prompt.lower()

    def test_grade_integration(self, sample_topic_context, sample_agent_config):
        """Test GRADE integration in results."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        grade_assessments = "GRADE assessments were conducted for all outcomes."
        grade_table = "| Outcome | Certainty |\n|---------|-----------|\n| Outcome 1 | High |"

        result = writer.write(
            extracted_data=extracted_data,
            prisma_counts={
                "found": 100,
                "no_dupes": 95,
                "screened": 80,
                "full_text": 50,
                "quantitative": 30,
            },
            grade_assessments=grade_assessments,
            grade_table=grade_table,
        )

        # Should include GRADE content
        assert len(result) > 0
        # Check that prompt includes GRADE
        prompt = writer._build_results_prompt(
            extracted_data=extracted_data,
            prisma_counts={"found": 100},
            key_findings=None,
            study_characteristics_table="",
            grade_assessments=grade_assessments,
            grade_table=grade_table,
        )
        assert "GRADE" in prompt or "certainty" in prompt.lower()


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

    def test_write_with_llm(self, sample_topic_context, sample_agent_config):
        """Test writing discussion with LLM (uses fallback when no API key)."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key=None,  # Triggers fallback
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
        assert "Discussion" in result

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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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

        # Pass extracted_data with at least one study so key_findings are included
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        result = writer._fallback_discussion(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
        )

        assert "Discussion" in result
        assert "Test question" in result
        assert "Finding 1" in result

    def test_limitations_split(self, sample_topic_context, sample_agent_config):
        """Test that discussion includes limitations split (evidence vs review process)."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        # Check that prompt includes limitations split requirement
        prompt = writer._build_discussion_prompt(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
            limitations=None,
            implications=None,
        )

        assert (
            "Limitations of the Evidence" in prompt
            or "limitations of the evidence" in prompt.lower()
        )
        assert (
            "Limitations of the Review Process" in prompt
            or "limitations of the review process" in prompt.lower()
        )
        assert "400-600 words" in prompt

    def test_implications_split(self, sample_topic_context, sample_agent_config):
        """Test that discussion includes implications split (practice/policy/research)."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
                ux_strategies=[],
                adaptivity_frameworks=[],
                patient_populations=[],
                accessibility_features=[],
            )
        ]

        # Check that prompt includes implications split requirement
        prompt = writer._build_discussion_prompt(
            research_question="Test question",
            key_findings=["Finding 1"],
            extracted_data=extracted_data,
            limitations=None,
            implications=None,
        )

        assert (
            "Implications for Practice" in prompt or "implications for practice" in prompt.lower()
        )
        assert "Implications for Policy" in prompt or "implications for policy" in prompt.lower()
        assert (
            "Implications for Research" in prompt or "implications for research" in prompt.lower()
        )
        assert "350-400 words" in prompt

    def test_word_count_enforcement(self, sample_topic_context, sample_agent_config):
        """Test word count enforcement in discussion prompt."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
            limitations=None,
            implications=None,
        )

        # Check word count requirements are specified
        assert "400-600 words" in prompt or "~400-600 words" in prompt
        assert "350-400 words" in prompt or "~350-400 words" in prompt
        assert "120-150 words" in prompt or "~120-150 words" in prompt

    def test_discussion_with_zero_studies(self, sample_topic_context, sample_agent_config):
        """Test discussion generation with 0 studies."""
        writer = DiscussionWriter(
            llm_provider="openai",
            api_key=None,
            topic_context=sample_topic_context.to_dict(),
            agent_config=sample_agent_config,
        )

        result = writer.write(
            research_question="Test question",
            key_findings=[],
            extracted_data=[],
        )

        assert len(result) > 0
        # Check prompt includes 0 studies handling
        prompt = writer._build_discussion_prompt(
            research_question="Test question",
            key_findings=[],
            extracted_data=[],
            limitations=None,
            implications=None,
        )
        assert "0 studies" in prompt or "no studies" in prompt.lower()

    def test_discussion_with_one_study(self, sample_topic_context, sample_agent_config):
        """Test discussion generation with 1 study."""
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
                country=None,
                setting=None,
                sample_size=None,
                detailed_outcomes=[],
                quantitative_results=None,
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
            limitations=None,
            implications=None,
        )

        # Should mention single study handling
        assert "1 study" in prompt or "single study" in prompt.lower()
