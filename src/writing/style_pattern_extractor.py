"""
Style Pattern Extractor

Extracts writing style patterns from eligible papers in the workflow.
Reuses full-text already retrieved during screening/extraction.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from ..screening.base_agent import BaseScreeningAgent
from ..search.connectors.base import Paper
from ..utils.pdf_retriever import PDFRetriever
from .style_reference import StylePatterns

logger = logging.getLogger(__name__)


class StylePatternExtractor(BaseScreeningAgent):
    """Extracts writing style patterns from papers."""

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - pattern extractor doesn't screen papers."""
        from ..screening.base_agent import InclusionDecision, ScreeningResult

        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Pattern extractor - screening not applicable",
        )

    def __init__(
        self,
        llm_provider: str = "gemini",
        api_key: Optional[str] = None,
        agent_config: Optional[Dict[str, Any]] = None,
        pdf_retriever: Optional[PDFRetriever] = None,
    ):
        """
        Initialize style pattern extractor.

        Args:
            llm_provider: LLM provider name
            api_key: API key for LLM provider
            agent_config: Agent configuration
            pdf_retriever: PDFRetriever instance (reuses cached full-text)
        """
        super().__init__(
            llm_provider=llm_provider,
            api_key=api_key,
            agent_config=agent_config or {},
        )
        self.pdf_retriever = pdf_retriever or PDFRetriever()

    def extract_patterns(
        self,
        papers: List[Paper],
        domain: Optional[str] = None,
        max_papers: Optional[int] = None,
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Extract writing style patterns from papers.

        Args:
            papers: List of eligible papers
            domain: Domain/topic area
            max_papers: Maximum number of papers to analyze (None = all)

        Returns:
            Dictionary of style patterns by section type
        """
        if not papers:
            logger.warning("No papers provided for pattern extraction")
            return StylePatterns().to_dict()

        # Limit papers if specified
        papers_to_analyze = papers[:max_papers] if max_papers else papers
        logger.info(
            f"Extracting style patterns from {len(papers_to_analyze)} papers "
            f"(out of {len(papers)} total)"
        )

        style_patterns = StylePatterns()

        for i, paper in enumerate(papers_to_analyze):
            try:
                logger.debug(
                    f"Extracting patterns from paper {i + 1}/{len(papers_to_analyze)}: {paper.title[:50]}..."
                )

                # Retrieve full-text from cache (already extracted during screening)
                full_text = self.pdf_retriever.retrieve_full_text(paper, max_length=100000)

                if not full_text:
                    logger.debug(f"No full-text available for paper: {paper.title}")
                    continue

                # Extract sections using LLM
                sections = self._extract_sections(full_text, paper.title)

                if not sections:
                    logger.debug(f"Could not extract sections from paper: {paper.title}")
                    continue

                # Analyze patterns from each section
                for section_type, section_text in sections.items():
                    if section_text:
                        self._analyze_section_patterns(
                            section_type, section_text, style_patterns, domain
                        )

            except Exception as e:
                logger.warning(
                    f"Error extracting patterns from paper {paper.title}: {e}",
                    exc_info=True,
                )
                continue

        logger.info(
            f"Extracted patterns: "
            f"Introduction: {len(style_patterns.get_patterns('introduction', 'sentence_openings'))} openings, "
            f"Methods: {len(style_patterns.get_patterns('methods', 'sentence_openings'))} openings, "
            f"Results: {len(style_patterns.get_patterns('results', 'sentence_openings'))} openings, "
            f"Discussion: {len(style_patterns.get_patterns('discussion', 'sentence_openings'))} openings"
        )

        return style_patterns.to_dict()

    def _extract_sections(self, full_text: str, paper_title: str) -> Dict[str, str]:
        """
        Extract sections from full-text using LLM.

        Args:
            full_text: Full text of the paper
            paper_title: Title of the paper

        Returns:
            Dictionary mapping section types to extracted text
        """
        prompt = self._build_section_extraction_prompt(full_text, paper_title)

        try:
            response = self._call_llm(prompt)
            return self._parse_section_extraction(response)
        except Exception as e:
            logger.warning(f"Error extracting sections: {e}", exc_info=True)
            return {}

    def _build_section_extraction_prompt(self, full_text: str, paper_title: str) -> str:
        """Build prompt for section extraction."""
        # Truncate if too long
        max_length = 50000
        if len(full_text) > max_length:
            full_text = full_text[:max_length] + "... [truncated]"

        prompt = f"""Extract the following sections from this academic paper:

Title: {paper_title}

Full Text:
{full_text}

Please extract and return ONLY the text content for each of these sections:

1. Introduction section - Include background, objectives, research question, and justification
2. Methods section - Include study design, data collection methods, and analysis approach
3. Results section - Include findings, outcomes, and data presentation
4. Discussion section - Include interpretation, implications, and limitations

For each section that exists in the paper, return the text content. If a section is not present or cannot be identified, return an empty string for that section.

Format your response as:
INTRODUCTION:
[text content or empty]

METHODS:
[text content or empty]

RESULTS:
[text content or empty]

DISCUSSION:
[text content or empty]

Do not include any meta-commentary or explanations - only the section text content."""

        return prompt

    def _parse_section_extraction(self, response: str) -> Dict[str, str]:
        """Parse LLM response to extract sections."""
        sections = {
            "introduction": "",
            "methods": "",
            "results": "",
            "discussion": "",
        }

        # Try to extract sections using regex
        patterns = {
            "introduction": r"INTRODUCTION:\s*(.*?)(?=METHODS:|RESULTS:|DISCUSSION:|$)",
            "methods": r"METHODS:\s*(.*?)(?=RESULTS:|DISCUSSION:|INTRODUCTION:|$)",
            "results": r"RESULTS:\s*(.*?)(?=DISCUSSION:|INTRODUCTION:|METHODS:|$)",
            "discussion": r"DISCUSSION:\s*(.*?)(?=INTRODUCTION:|METHODS:|RESULTS:|$)",
        }

        for section_type, pattern in patterns.items():
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1).strip()
                if text and len(text) > 50:  # Minimum length check
                    sections[section_type] = text

        return sections

    def _analyze_section_patterns(
        self,
        section_type: str,
        section_text: str,
        style_patterns: StylePatterns,
        domain: Optional[str] = None,
    ):
        """
        Analyze writing patterns from a section.

        Args:
            section_type: Type of section (introduction, methods, results, discussion)
            section_text: Text content of the section
            style_patterns: StylePatterns object to add patterns to
            domain: Domain/topic area
        """
        # Extract sentence openings (first 10-20 words of each sentence)
        sentences = re.split(r"[.!?]\s+", section_text)
        for sentence in sentences[:20]:  # Limit to first 20 sentences
            sentence = sentence.strip()
            if len(sentence) > 30:  # Minimum length
                # Extract opening phrase (first 10-15 words)
                words = sentence.split()[:15]
                opening = " ".join(words)
                if len(opening) > 20:
                    style_patterns.add_pattern(section_type, "sentence_openings", opening)

        # Extract citation patterns
        citation_patterns = re.findall(
            r"\[.*?\d+.*?\]|\(.*?\d{4}.*?\)|et al\.\s*\[?\d+\]?",
            section_text,
        )
        for pattern in citation_patterns[:10]:  # Limit examples
            style_patterns.add_pattern(section_type, "citation_patterns", pattern)

        # Extract transition phrases
        transition_words = [
            "however",
            "furthermore",
            "moreover",
            "additionally",
            "consequently",
            "therefore",
            "nevertheless",
            "in contrast",
            "on the other hand",
            "in addition",
            "specifically",
            "particularly",
            "notably",
            "importantly",
        ]

        for transition in transition_words:
            pattern = rf"\b{transition}\b"
            matches = re.findall(pattern, section_text, re.IGNORECASE)
            if matches:
                # Extract context around transition (5 words before and after)
                for match in re.finditer(pattern, section_text, re.IGNORECASE):
                    start = max(0, match.start() - 50)
                    end = min(len(section_text), match.end() + 50)
                    context = section_text[start:end].strip()
                    if len(context) > 20:
                        style_patterns.add_pattern(section_type, "transitions", context[:100])
                        break  # One example per transition word

        # Extract domain-specific vocabulary (academic terms, technical terms)
        # Simple heuristic: words that appear multiple times and are capitalized or technical
        words = re.findall(r"\b[A-Z][a-z]+\b|\b[a-z]{8,}\b", section_text)
        word_freq = {}
        for word in words:
            word_lower = word.lower()
            if word_lower not in [
                "the",
                "this",
                "that",
                "these",
                "those",
                "which",
                "where",
                "when",
                "what",
            ]:
                word_freq[word_lower] = word_freq.get(word_lower, 0) + 1

        # Add frequently used words as vocabulary patterns
        for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]:
            if freq >= 2 and len(word) > 6:  # Technical/academic terms
                style_patterns.add_pattern(section_type, "vocabulary", word)
