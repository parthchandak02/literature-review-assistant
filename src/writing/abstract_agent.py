"""
Abstract Generator Agent

Generates structured or unstructured abstracts for systematic reviews.
"""

from typing import List, Optional, Dict, Any
import logging
from pydantic import BaseModel, Field

from ..utils.log_context import agent_log_context
from ..search.connectors.base import Paper

logger = logging.getLogger(__name__)


class AbstractSchema(BaseModel):
    """Schema for abstract output."""
    abstract: str = Field(description="The complete abstract text")


class AbstractGenerator:
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
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key
        self.topic_context = topic_context
        self.config = config or {}
        self.structured = self.config.get("structured", True)
        self.word_limit = self.config.get("word_limit", 250)

    @agent_log_context(role="abstract_generator")
    def generate(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
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
        if self.structured:
            return self._generate_structured_abstract(
                research_question, included_papers, article_sections
            )
        else:
            return self._generate_unstructured_abstract(
                research_question, included_papers, article_sections
            )

    def _generate_structured_abstract(
        self,
        research_question: str,
        included_papers: List[Paper],
        article_sections: Dict[str, str],
    ) -> str:
        """Generate structured abstract (Background, Objective, Methods, Results, Conclusions)."""
        from ..tools.tool_registry import get_llm_tool

        llm_tool = get_llm_tool(self.llm_provider, self.llm_api_key)

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
            response = llm_tool.generate_structured_output(
                prompt=prompt,
                schema=AbstractSchema,
                temperature=0.3,
            )
            abstract = response.abstract
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
    ) -> str:
        """Generate unstructured abstract (single paragraph)."""
        from ..tools.tool_registry import get_llm_tool

        llm_tool = get_llm_tool(self.llm_provider, self.llm_api_key)

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
            response = llm_tool.generate_structured_output(
                prompt=prompt,
                schema=AbstractSchema,
                temperature=0.3,
            )
            abstract = response.abstract
            logger.info(f"Generated unstructured abstract ({len(abstract.split())} words)")
            return abstract
        except Exception as e:
            logger.error(f"Error generating abstract: {e}", exc_info=True)
            return self._fallback_abstract(research_question, included_papers)

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
