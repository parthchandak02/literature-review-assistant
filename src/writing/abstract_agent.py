"""
Abstract Generator Agent

Generates structured or unstructured abstracts for systematic reviews.
"""

from typing import List, Optional, Dict, Any
import logging
import json
from pydantic import BaseModel, Field

from ..utils.log_context import agent_log_context
from ..search.connectors.base import Paper
from ..screening.base_agent import BaseScreeningAgent

logger = logging.getLogger(__name__)


class AbstractSchema(BaseModel):
    """Schema for abstract output."""
    abstract: str = Field(description="The complete abstract text")


class PRISMA2020AbstractSchema(BaseModel):
    """Schema for PRISMA 2020 structured abstract with 12 elements."""
    background: str = Field(description="Brief context and rationale")
    objectives: str = Field(description="Explicit statement of main objective(s) or question(s)")
    eligibility_criteria: str = Field(description="Inclusion and exclusion criteria")
    information_sources: str = Field(description="Information sources (databases, registers) and dates searched")
    risk_of_bias: str = Field(description="Methods used to assess risk of bias")
    synthesis_methods: str = Field(description="Methods used to present and synthesize results")
    results: str = Field(description="Number of included studies, participants, and main results")
    limitations: str = Field(description="Limitations of the evidence included in the review")
    interpretation: str = Field(description="General interpretation of results and important implications")
    funding: str = Field(description="Primary source of funding for the review")
    registration: str = Field(description="Register name and registration number")


class AbstractGenerator(BaseScreeningAgent):
    """Generates abstracts for systematic reviews."""

    def __init__(
        self,
        llm_provider: str,
        llm_api_key: Optional[str],
        topic_context: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize abstract generator.

        Args:
            llm_provider: LLM provider name
            llm_api_key: API key for LLM
            topic_context: Topic context dictionary
            config: Optional configuration
        """
        # Initialize BaseScreeningAgent with minimal config
        agent_config = {
            "role": "Abstract Generator",
            "goal": "Generate abstracts for systematic reviews",
            "backstory": "Expert academic writer specializing in systematic review abstracts",
            "temperature": 0.3,
        }
        super().__init__(
            llm_provider=llm_provider,
            api_key=llm_api_key,
            topic_context=topic_context,
            agent_config=agent_config,
        )
        self.config = config or {}
        self.structured = self.config.get("structured", True)
        self.word_limit = self.config.get("word_limit", 250)
        self.prisma_2020_format = self.config.get("prisma_2020_format", True)  # Default to PRISMA 2020

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - abstract generator doesn't screen papers."""
        from ..screening.base_agent import ScreeningResult, InclusionDecision

        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Abstract generator - screening not applicable",
        )

    def generate(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """
        Generate abstract from research question and article sections.

        Args:
            research_question: The research question
            included_papers: List of included papers
            article_sections: Dictionary with article sections (introduction, methods, results, discussion)

        Returns:
            Generated abstract text
        """
        with agent_log_context("abstract_generator", "generate"):
            if self.structured:
                if self.prisma_2020_format:
                    return self._generate_prisma_2020_abstract(
                        research_question, included_papers, article_sections, style_patterns
                    )
                else:
                    return self._generate_structured_abstract(
                        research_question, included_papers, article_sections, style_patterns
                    )
            else:
                return self._generate_unstructured_abstract(
                    research_question, included_papers, article_sections, style_patterns
                )

    def _generate_prisma_2020_abstract(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """Generate PRISMA 2020 structured abstract with 12 elements."""
        methods_text = article_sections.get("methods", "")
        results_text = article_sections.get("results", "")
        discussion_text = article_sections.get("discussion", "")
        
        # Extract protocol registration info from config (unified location in topic section)
        if self.config:
            protocol_info = self.config.get("topic", {}).get("protocol", {})
        else:
            protocol_info = self.topic_context.get("protocol", {}) if isinstance(self.topic_context, dict) else {}
        registration_number = protocol_info.get("registration_number", "")
        registry = protocol_info.get("registry", "PROSPERO")
        
        # Extract funding info from config (unified location in topic section)
        if self.config:
            funding_info = self.config.get("topic", {}).get("funding", {})
        else:
            funding_info = self.topic_context.get("funding", {}) if isinstance(self.topic_context, dict) else {}
        funding_source = funding_info.get("source", "No funding received")

        prompt = f"""Generate a PRISMA 2020 structured abstract for a systematic review with exactly 12 elements:

1. Background: Brief context and rationale (2-3 sentences)
2. Objectives: Explicit statement of main objective(s) or question(s) (1-2 sentences)
3. Eligibility criteria: Inclusion and exclusion criteria (1-2 sentences)
4. Information sources: Information sources (databases, registers) and dates searched (1-2 sentences)
5. Risk of bias: Methods used to assess risk of bias (1 sentence)
6. Synthesis methods: Methods used to present and synthesize results (1-2 sentences)
7. Results: Number of included studies, participants, and main results (2-3 sentences)
8. Limitations: Limitations of the evidence included in the review (1-2 sentences)
9. Interpretation: General interpretation of results and important implications (1-2 sentences)
10. Funding: Primary source of funding for the review (1 sentence)
11. Registration: Register name and registration number (1 sentence)

Research Question: {research_question}

Methods Summary: {methods_text[:1000] if methods_text else "Not available"}

Results Summary: {results_text[:1000] if results_text else "Not available"}

Discussion Summary: {discussion_text[:500] if discussion_text else "Not available"}

Number of included studies: {len(included_papers)}

Registration: {registry} {registration_number if registration_number else "(not registered)"}

Funding: {funding_source}

Generate a structured abstract with all 12 elements clearly labeled. Total word limit: 250-300 words. Format each element on a new line with the label followed by a colon."""

        # Add style guidelines if patterns available (use introduction patterns for abstract)
        if style_patterns and "introduction" in style_patterns:
            intro_patterns = style_patterns["introduction"]
            style_guidelines = "\n\nSTYLE GUIDELINES (based on analysis of included papers):\n"
            style_guidelines += "- Use natural academic vocabulary with domain-specific terms\n"
            style_guidelines += "- Vary sentence structures\n"
            style_guidelines += "- Maintain scholarly tone: precise but not robotic\n"
            prompt += style_guidelines

        # If no LLM client, use fallback immediately
        if not self.llm_client:
            return self._fallback_prisma_2020_abstract(research_question, included_papers, registration_number, registry, funding_source)
        
        # Try to use LLM if available, otherwise fallback
        try:
            # Use _call_llm from BaseScreeningAgent
            response_text = self._call_llm(prompt)
            # Try to parse as JSON if it looks like JSON, otherwise use as-is
            try:
                response_json = json.loads(response_text)
                if isinstance(response_json, dict) and "abstract" in response_json:
                    abstract = response_json["abstract"]
                else:
                    abstract = response_text
            except json.JSONDecodeError:
                abstract = response_text
            
            logger.info(f"Generated PRISMA 2020 structured abstract ({len(abstract.split())} words)")
            return abstract
        except Exception as e:
            logger.warning(f"Could not generate PRISMA 2020 abstract with LLM, using fallback: {e}")
            return self._fallback_prisma_2020_abstract(research_question, included_papers, registration_number, registry, funding_source)

    def _generate_structured_abstract(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """Generate structured abstract (Background, Objective, Methods, Results, Conclusions)."""
        # If no LLM client, use fallback
        if not self.llm_client:
            return self._fallback_abstract(research_question, included_papers)

        methods_text = article_sections.get("methods", "")
        results_text = article_sections.get("results", "")
        discussion_text = article_sections.get("discussion", "")

        prompt = f"""Generate a structured abstract for a systematic review following this format:

Background: Brief context and rationale
Objective: State the research question/objective
Methods: Brief description of search strategy, databases, selection criteria, and synthesis approach
Results: Key findings (number of studies, main results)
Conclusions: Main conclusions and implications

Research Question: {research_question}

Methods Summary: {methods_text[:1000] if methods_text else "Not available"}

Results Summary: {results_text[:1000] if results_text else "Not available"}

Discussion Summary: {discussion_text[:500] if discussion_text else "Not available"}

Number of included studies: {len(included_papers)}

Generate a structured abstract with these sections. Total word limit: approximately {self.word_limit} words."""

        try:
            response_text = self._call_llm(prompt)
            # Try to parse as JSON if it looks like JSON, otherwise use as-is
            try:
                response_json = json.loads(response_text)
                if isinstance(response_json, dict) and "abstract" in response_json:
                    abstract = response_json["abstract"]
                else:
                    abstract = response_text
            except json.JSONDecodeError:
                abstract = response_text
            
            logger.info(f"Generated structured abstract ({len(abstract.split())} words)")
            return abstract
        except Exception as e:
            logger.error(f"Error generating abstract: {e}", exc_info=True)
            return self._fallback_abstract(research_question, included_papers)

    def _generate_unstructured_abstract(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
        style_patterns: Optional[Dict[str, Dict[str, List[str]]]] = None,
    ) -> str:
        """Generate unstructured abstract (single paragraph)."""
        # If no LLM client, use fallback
        if not self.llm_client:
            return self._fallback_abstract(research_question, included_papers)

        methods_text = article_sections.get("methods", "")
        results_text = article_sections.get("results", "")
        discussion_text = article_sections.get("discussion", "")

        prompt = f"""Generate a concise abstract for a systematic review (single paragraph, approximately {self.word_limit} words).

Research Question: {research_question}

Methods Summary: {methods_text[:1000] if methods_text else "Not available"}

Results Summary: {results_text[:1000] if results_text else "Not available"}

Discussion Summary: {discussion_text[:500] if discussion_text else "Not available"}

Number of included studies: {len(included_papers)}

Generate a single-paragraph abstract that summarizes the background, objective, methods, results, and conclusions."""

        try:
            response_text = self._call_llm(prompt)
            # Try to parse as JSON if it looks like JSON, otherwise use as-is
            try:
                response_json = json.loads(response_text)
                if isinstance(response_json, dict) and "abstract" in response_json:
                    abstract = response_json["abstract"]
                else:
                    abstract = response_text
            except json.JSONDecodeError:
                abstract = response_text
            
            logger.info(f"Generated unstructured abstract ({len(abstract.split())} words)")
            return abstract
        except Exception as e:
            logger.error(f"Error generating abstract: {e}", exc_info=True)
            return self._fallback_abstract(research_question, included_papers)

    def _fallback_prisma_2020_abstract(
        self, research_question: str, included_papers: List[Paper], 
        registration_number: str = "", registry: str = "PROSPERO", 
        funding_source: str = "No funding received"
    ) -> str:
        """Generate a fallback PRISMA 2020 abstract if LLM generation fails."""
        registration_text = f"{registry} {registration_number}" if registration_number else f"{registry} (not registered)"
        return f"""Background: This systematic review addresses an important research question in health informatics.

Objectives: {research_question}

Eligibility criteria: Studies were included based on predefined inclusion and exclusion criteria.

Information sources: A comprehensive search was conducted across multiple databases from inception to present.

Risk of bias: Risk of bias was assessed using appropriate tools for each study design.

Synthesis methods: Results were synthesized narratively.

Results: {len(included_papers)} studies met the inclusion criteria and were included in this review.

Limitations: Limitations include potential publication bias and heterogeneity in study designs.

Interpretation: The findings provide insights into the research question and have implications for practice and future research.

Funding: {funding_source}

Registration: {registration_text}"""

    def _fallback_abstract(
        self, research_question: str, included_papers: List[Paper]
    ) -> str:
        """Generate a simple fallback abstract if LLM generation fails."""
        if self.structured:
            return f"""Background: This systematic review addresses an important research question in health informatics.

Objective: {research_question}

Methods: A comprehensive search was conducted across multiple databases. Studies were screened and assessed for eligibility.

Results: {len(included_papers)} studies met the inclusion criteria and were included in this review.

Conclusions: The findings provide insights into the research question and have implications for practice and future research."""
        else:
            return f"This systematic review addresses the research question: {research_question}. A comprehensive search was conducted across multiple databases, and {len(included_papers)} studies met the inclusion criteria. The findings provide insights with implications for practice and future research."
