"""
Title/Abstract Screening Agent

Screens papers based on title and abstract using LLM with structured outputs.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from fuzzywuzzy import fuzz
from pydantic import ValidationError

from ..config.debug_config import DebugLevel
from ..schemas.llm_response_schemas import ScreeningResultSchema
from ..schemas.screening_schemas import (
    InclusionDecision as SchemaInclusionDecision,
)
from ..utils.log_context import agent_log_context
from .base_agent import BaseScreeningAgent, InclusionDecision, ScreeningResult

logger = logging.getLogger(__name__)


class TitleAbstractScreener(BaseScreeningAgent):
    """Screens papers based on title and abstract."""

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> ScreeningResult:
        """
        Screen a paper based on title and abstract.

        Args:
            title: Paper title
            abstract: Paper abstract
            inclusion_criteria: List of inclusion criteria
            exclusion_criteria: List of exclusion criteria
            topic_context: Optional topic context (if None, uses instance topic_context)

        Returns:
            ScreeningResult with decision and reasoning
        """
        # Handle edge cases
        title = title or ""
        abstract = abstract or ""

        # If both title and abstract are missing/empty, return uncertain
        if not title.strip() and not abstract.strip():
            logger.warning(f"[{self.role}] Paper has no title or abstract, returning UNCERTAIN")
            return ScreeningResult(
                decision=InclusionDecision.UNCERTAIN,
                confidence=0.3,
                reasoning="Paper has no title or abstract available for screening",
            )

        # If title/abstract is very short, log warning
        if len(title.strip()) < 5 and len(abstract.strip()) < 50:
            logger.warning(
                f"[{self.role}] Paper has very short title/abstract, may affect screening quality"
            )

        # Validate criteria
        if not inclusion_criteria:
            logger.warning(f"[{self.role}] No inclusion criteria provided")
        if not exclusion_criteria:
            logger.warning(f"[{self.role}] No exclusion criteria provided")

        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        with agent_log_context(self.role, "screen_paper", paper_title=title[:50]):
            if is_verbose:
                logger.debug(
                    f'[{self.role}] Screening paper "{title[:60]}..." - '
                    f"Building prompt with {len(inclusion_criteria)} inclusion criteria, "
                    f"{len(exclusion_criteria)} exclusion criteria"
                )

            prompt = self._build_screening_prompt(
                title, abstract, inclusion_criteria, exclusion_criteria
            )

            if not self.llm_client:
                if is_verbose:
                    logger.debug(f"[{self.role}] Using fallback keyword matching")
                result = self._fallback_screen(
                    title, abstract, inclusion_criteria, exclusion_criteria
                )
            else:
                # Use new _call_llm_with_schema method with automatic retry logic
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Using structured output with {self.llm_model}"
                    )

                try:
                    schema_result = self._call_llm_with_schema(
                        prompt=prompt,
                        response_model=ScreeningResultSchema,
                    )
                    result = self._convert_schema_to_result(schema_result)
                except (ValidationError, json.JSONDecodeError, Exception) as e:
                    # Keep schema path authoritative. Route to manual adjudication on parse failure.
                    logger.error(
                        f"[{self.role}] Schema-based LLM call failed after retries. "
                        f"Returning UNCERTAIN for manual review. Error: {type(e).__name__}: {e}"
                    )
                    result = ScreeningResult(
                        decision=InclusionDecision.UNCERTAIN,
                        confidence=0.0,
                        reasoning=(
                            "Automated screening failed due to structured-output parsing errors. "
                            "Manual adjudication required."
                        ),
                        exclusion_reason=None,
                    )

                logger.info(
                    f"[{self.role}] Screening decision: {result.decision.value} "
                    f"(confidence: {result.confidence:.2f})"
                )
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Structured response validated successfully"
                    )

            # Log decision details if debug enabled
            if is_verbose:
                logger.debug(
                    f"[{self.role}] Decision: {result.decision.value.upper()}, "
                    f"Confidence: {result.confidence:.2f}"
                )
                logger.debug(f"[{self.role}] Reasoning: {result.reasoning[:100]}...")
                if result.exclusion_reason:
                    logger.debug(f"[{self.role}] Exclusion reason: {result.exclusion_reason}")

            # Restore original context
            if topic_context:
                self.topic_context = original_context

            return result

    def _build_screening_prompt(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> str:
        """Build prompt for LLM screening."""
        prompt = f"""You are screening research papers for a systematic review. Evaluate the following paper:

Title: {title}

Abstract: {abstract}

Inclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in inclusion_criteria)}

Exclusion Criteria:
{chr(10).join(f"- {criterion}" for criterion in exclusion_criteria)}

IMPORTANT SCREENING GUIDELINES:
- A paper should be INCLUDED if it meets SUFFICIENT inclusion criteria (not necessarily all criteria)
- For title/abstract screening, be INCLUSIVE. Only exclude papers that CLEARLY do not meet criteria
- When in doubt, err on the side of INCLUSION for full-text review
- Exclusion requires CLEAR violation of exclusion criteria
- Be permissive at this stage - borderline papers should be included for full-text review

Please provide your evaluation as a JSON object with the following structure:
{{
  "decision": "include" | "exclude" | "uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of your decision",
  "exclusion_reason": "If excluding, specify which exclusion criterion applies" (or null if including)
}}

Return ONLY valid JSON."""
        return prompt

    def _call_llm_structured(self, prompt: str) -> str:
        """
        Call LLM with structured output request (JSON mode).

        Args:
            prompt: Prompt with JSON format instructions

        Returns:
            JSON string response
        """
        if not self.llm_client:
            raise ValueError("LLM client not available")

        enhanced_prompt = self._inject_topic_context(prompt)

        # Validate provider (Gemini only)
        if self.llm_provider != "gemini":
            raise ValueError(
                f"Structured JSON output only supported with Gemini. "
                f"Current provider: {self.llm_provider}"
            )

        # Use Gemini structured output
        if self.llm_provider == "gemini":
            # Gemini - request JSON in prompt, parse response
            from google.genai import types

            json_prompt = enhanced_prompt + "\n\nReturn your response as valid JSON only."
            response = self.llm_client.models.generate_content(
                model=getattr(self, "llm_model_name", self.llm_model),
                contents=json_prompt,
                config=types.GenerateContentConfig(temperature=self.temperature),
            )
            content = response.text if hasattr(response, "text") else "{}"
            # Extract JSON from response if wrapped in markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            return content
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def _convert_schema_to_result(self, schema_result: ScreeningResultSchema) -> ScreeningResult:
        """Convert Pydantic schema to ScreeningResult dataclass."""
        # Handle None case (should not happen if _call_llm_with_schema works correctly)
        if schema_result is None:
            logger.error(
                f"[{self.role}] Received None schema_result, returning UNCERTAIN decision"
            )
            return ScreeningResult(
                decision=InclusionDecision.UNCERTAIN,
                confidence=0.3,
                reasoning="LLM response parsing failed - unable to determine decision",
            )

        # Map schema enum to dataclass enum
        decision_map = {
            SchemaInclusionDecision.INCLUDE: InclusionDecision.INCLUDE,
            SchemaInclusionDecision.EXCLUDE: InclusionDecision.EXCLUDE,
            SchemaInclusionDecision.UNCERTAIN: InclusionDecision.UNCERTAIN,
        }

        return ScreeningResult(
            decision=decision_map.get(schema_result.decision, InclusionDecision.UNCERTAIN),
            confidence=schema_result.confidence,
            reasoning=schema_result.reasoning,
            exclusion_reason=schema_result.exclusion_reason,
        )

    def _parse_llm_response(self, response: str) -> ScreeningResult:
        """Parse LLM response into ScreeningResult."""
        decision = InclusionDecision.UNCERTAIN
        confidence = 0.5
        reasoning = response
        exclusion_reason = None

        lines = response.split("\n")
        for line in lines:
            line_upper = line.upper().strip()
            if line_upper.startswith("DECISION:"):
                decision_str = line.split(":", 1)[1].strip().upper()
                if "INCLUDE" in decision_str:
                    decision = InclusionDecision.INCLUDE
                elif "EXCLUDE" in decision_str:
                    decision = InclusionDecision.EXCLUDE
                else:
                    decision = InclusionDecision.UNCERTAIN
            elif line_upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass
            elif line_upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line_upper.startswith("EXCLUSION_REASON:"):
                exclusion_reason = line.split(":", 1)[1].strip()

        return ScreeningResult(
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            exclusion_reason=exclusion_reason,
        )

    def _extract_keywords_from_criteria(
        self, criteria: List[str], min_word_length: int = 3
    ) -> Set[str]:
        """
        Extract keywords from criteria text.

        Args:
            criteria: List of criteria strings
            min_word_length: Minimum word length to include

        Returns:
            Set of extracted keywords
        """
        keywords = set()
        for criterion in criteria:
            # Split into words and filter
            words = re.findall(r"\b\w+\b", criterion.lower())
            keywords.update(word for word in words if len(word) >= min_word_length)
        return keywords

    def _build_keyword_sets(
        self,
        search_terms: Optional[Dict[str, List[str]]] = None,
        inclusion_criteria: Optional[List[str]] = None,
        exclusion_criteria: Optional[List[str]] = None,
    ) -> Dict[str, Set[str]]:
        """
        Build comprehensive keyword sets from search_terms and criteria.

        Args:
            search_terms: Dictionary of search term groups from config
            inclusion_criteria: List of inclusion criteria
            exclusion_criteria: List of exclusion criteria

        Returns:
            Dictionary with 'inclusion_groups' and 'exclusion_keywords' sets
        """
        keyword_sets = {
            "inclusion_groups": [],  # List of sets, each set is a concept group (OR within, AND between)
            "exclusion_keywords": set(),  # Set of exclusion keywords (any match excludes)
        }

        # Build inclusion keyword groups from search_terms
        if search_terms:
            for _group_name, synonyms in search_terms.items():
                # Each group is a set of synonyms (OR logic within group)
                group_keywords = set()
                for synonym in synonyms:
                    # Split multi-word synonyms and add individual words
                    words = re.findall(r"\b\w+\b", synonym.lower())
                    group_keywords.update(word for word in words if len(word) >= 3)
                    # Also add the full phrase as a potential match
                    if len(synonym.split()) > 1:
                        group_keywords.add(synonym.lower())
                if group_keywords:
                    keyword_sets["inclusion_groups"].append(group_keywords)

        # Extract keywords from inclusion criteria and add as additional groups
        if inclusion_criteria:
            for criterion in inclusion_criteria:
                criterion_keywords = self._extract_keywords_from_criteria([criterion])
                if criterion_keywords:
                    keyword_sets["inclusion_groups"].append(criterion_keywords)

        # Build exclusion keywords - use explicit phrases only, not generic words
        if exclusion_criteria:
            # Only match explicit exclusion phrases, not individual words
            explicit_exclusion_phrases = [
                "rule-based",
                "rule based",
                "non-llm",
                "non llm",
                "without chatbot",
                "no chatbot",
                "case study",
                "case studies",
                "opinion piece",
                "non-peer-reviewed",
                "conference abstract",
            ]
            keyword_sets["exclusion_keywords"].update(
                phrase.lower() for phrase in explicit_exclusion_phrases
            )

            # Extract only meaningful exclusion phrases from criteria (not generic words)
            for criterion in exclusion_criteria:
                criterion_lower = criterion.lower()
                # Look for specific exclusion patterns
                if "rule-based" in criterion_lower or "rule based" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("rule-based")
                if "non-llm" in criterion_lower or "non llm" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("non-llm")
                if "without chatbot" in criterion_lower or "no chatbot" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("without chatbot")
                if "case study" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("case study")
                if "opinion" in criterion_lower and "piece" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("opinion piece")
                if "non-peer-reviewed" in criterion_lower:
                    keyword_sets["exclusion_keywords"].add("non-peer-reviewed")

        return keyword_sets

    def _fuzzy_match_keywords(
        self, text: str, keywords: Set[str], threshold: float = 0.75
    ) -> List[tuple]:
        """
        Perform fuzzy matching of keywords against text.

        Args:
            text: Text to search in
            keywords: Set of keywords to match
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            List of (keyword, similarity_score) tuples for matches above threshold
        """
        matches = []
        text_lower = text.lower()

        for keyword in keywords:
            # For single words, use simple substring match first (faster)
            if len(keyword.split()) == 1:
                if keyword in text_lower:
                    matches.append((keyword, 1.0))
                else:
                    # Use fuzzy matching for variations
                    # Check against individual words in text
                    text_words = re.findall(r"\b\w+\b", text_lower)
                    for word in text_words:
                        if len(word) >= 3:  # Skip very short words
                            similarity = fuzz.ratio(keyword, word) / 100.0
                            if similarity >= threshold:
                                matches.append((keyword, similarity))
                                break
            else:
                # For phrases, use token_sort_ratio for better matching
                similarity = fuzz.token_sort_ratio(keyword, text_lower) / 100.0
                if similarity >= threshold:
                    matches.append((keyword, similarity))

        return matches

    def _fallback_screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
        search_terms: Optional[Dict[str, List[str]]] = None,
    ) -> ScreeningResult:
        """
        Enhanced fallback screening using comprehensive keyword matching with fuzzy matching.

        Args:
            title: Paper title
            abstract: Paper abstract
            inclusion_criteria: List of inclusion criteria
            exclusion_criteria: List of exclusion criteria
            search_terms: Optional dictionary of search term groups from config

        Returns:
            ScreeningResult with decision and confidence
        """
        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        text = (title + " " + abstract).lower()

        if is_verbose:
            logger.debug(f"[{self.role}] Keyword matching: Checking exclusion keywords...")

        # Build comprehensive keyword sets
        keyword_sets = self._build_keyword_sets(
            search_terms=search_terms,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
        )

        # STAGE 1: Check exclusion criteria first (strict filtering)
        # Only exclude if explicit exclusion phrases are found (not generic words)
        exclusion_matches = self._fuzzy_match_keywords(
            text,
            keyword_sets["exclusion_keywords"],
            threshold=0.80,  # Higher threshold for exclusions
        )

        if exclusion_matches:
            # Only exclude if we have clear exclusion matches (not just generic words)
            # Check if matches are meaningful exclusion phrases
            meaningful_exclusions = [
                kw
                for kw, score in exclusion_matches
                if any(
                    phrase in kw
                    for phrase in [
                        "rule-based",
                        "non-llm",
                        "without chatbot",
                        "case study",
                        "opinion",
                    ]
                )
            ]

            if meaningful_exclusions:
                confidence = min(0.9, 0.75 + (len(meaningful_exclusions) * 0.05))
                matched_keywords = meaningful_exclusions[:3]
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Exclusion keywords matched: {', '.join(matched_keywords)}"
                    )
                return ScreeningResult(
                    decision=InclusionDecision.EXCLUDE,
                    confidence=confidence,
                    reasoning=f"Matched explicit exclusion phrases: {', '.join(matched_keywords)}",
                    exclusion_reason=f"Exclusion phrases: {', '.join(matched_keywords)}",
                )

        if is_verbose:
            logger.debug(f"[{self.role}] No exclusion matches. Checking inclusion groups...")

        # STAGE 2: Check inclusion criteria (permissive matching)
        # Use Boolean logic: OR within concept groups, AND between groups
        inclusion_groups = keyword_sets["inclusion_groups"]

        if not inclusion_groups:
            # No inclusion groups defined, use basic keyword matching from criteria
            inclusion_keywords = self._extract_keywords_from_criteria(inclusion_criteria)
            inclusion_matches = self._fuzzy_match_keywords(text, inclusion_keywords, threshold=0.75)

            if is_verbose:
                logger.debug(
                    f"[{self.role}] Matched {len(inclusion_matches)}/{len(inclusion_criteria)} inclusion keywords"
                )

            if len(inclusion_matches) >= len(inclusion_criteria) * 0.5:
                confidence = min(0.8, 0.6 + (len(inclusion_matches) * 0.05))
                return ScreeningResult(
                    decision=InclusionDecision.INCLUDE,
                    confidence=confidence,
                    reasoning=f"Matched {len(inclusion_matches)} inclusion keywords",
                )
            else:
                # Low confidence, should go to LLM
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Insufficient matches ({len(inclusion_matches)}/{len(inclusion_criteria)}), needs LLM review"
                    )
                return ScreeningResult(
                    decision=InclusionDecision.UNCERTAIN,
                    confidence=0.5,
                    reasoning="Insufficient keyword matches, needs LLM review",
                )

        # Check each inclusion group (must match at least one keyword from each group)
        matched_groups = 0
        total_group_matches = []

        for i, group in enumerate(inclusion_groups):
            group_matches = self._fuzzy_match_keywords(text, group, threshold=0.75)
            if group_matches:
                matched_groups += 1
                total_group_matches.extend(group_matches)
                if is_verbose:
                    matched_kws = [kw for kw, _ in group_matches[:2]]
                    logger.debug(
                        f"[{self.role}] Matched inclusion group {i + 1}/{len(inclusion_groups)}: {matched_kws}"
                    )

        # Calculate confidence based on how many groups matched
        total_groups = len(inclusion_groups)
        group_match_ratio = matched_groups / total_groups if total_groups > 0 else 0

        if is_verbose:
            logger.debug(
                f"[{self.role}] Matched {matched_groups}/{total_groups} inclusion groups "
                f"(ratio: {group_match_ratio:.2f})"
            )

        # High confidence include: matched keywords from multiple concept groups
        # Tightened: Require at least 3 groups OR 60% of groups (more conservative to reduce off-topic auto-inclusion)
        min_groups_required = max(3, int(total_groups * 0.6))
        if matched_groups >= min_groups_required:
            confidence = min(0.75, 0.65 + (group_match_ratio * 0.1))  # Reduced max confidence
            matched_keywords = [kw for kw, _ in total_group_matches[:5]]  # Top 5
            if is_verbose:
                logger.debug(
                    f"[{self.role}] High confidence INCLUDE: matched {matched_groups} groups "
                    f"(required: {min_groups_required}), confidence: {confidence:.2f}"
                )
            return ScreeningResult(
                decision=InclusionDecision.INCLUDE,
                confidence=confidence,
                reasoning=f"Matched {matched_groups}/{total_groups} inclusion concept groups: {', '.join(matched_keywords[:3])}",
            )
        # Medium confidence: some groups matched (send to LLM for review)
        elif matched_groups >= 1:
            confidence = 0.5  # Lower confidence, definitely needs LLM review
            matched_keywords = [kw for kw, _ in total_group_matches[:3]]
            if is_verbose:
                logger.debug(
                    f"[{self.role}] Medium confidence UNCERTAIN: matched {matched_groups} groups, "
                    f"needs LLM review"
                )
            return ScreeningResult(
                decision=InclusionDecision.UNCERTAIN,
                confidence=confidence,
                reasoning=f"Matched {matched_groups}/{total_groups} inclusion groups: {', '.join(matched_keywords)}. Needs LLM review.",
            )
        # Low confidence: few/no matches
        else:
            if is_verbose:
                logger.debug(
                    f"[{self.role}] Low confidence UNCERTAIN: no matches, needs LLM review"
                )
            return ScreeningResult(
                decision=InclusionDecision.UNCERTAIN,
                confidence=0.4,
                reasoning="Few or no keyword matches, needs LLM review",
            )
