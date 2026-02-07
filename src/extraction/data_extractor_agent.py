"""
Data Extraction Agent

Extracts structured data from research papers using LLM with structured outputs.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
import logging
import time

from ..utils.rich_utils import (
    print_llm_request_panel,
    print_llm_response_panel,
)
from ..screening.base_agent import BaseScreeningAgent
from ..schemas.extraction_schemas import ExtractedDataSchema
from ..config.debug_config import DebugLevel

logger = logging.getLogger(__name__)


@dataclass
class ExtractedData:
    """Structured data extracted from a paper."""

    title: str
    authors: List[str]
    year: Optional[int]
    journal: Optional[str]
    doi: Optional[str]
    study_objectives: List[str]
    methodology: Optional[str]
    study_design: Optional[str]
    participants: Optional[str]
    interventions: Optional[str]
    outcomes: List[str]
    key_findings: List[str]
    limitations: Optional[str]
    # Additional fields for study characteristics table
    country: Optional[str]
    setting: Optional[str]
    sample_size: Optional[int]
    detailed_outcomes: List[str]
    quantitative_results: Optional[str]
    # Domain-specific fields
    ux_strategies: List[str]
    adaptivity_frameworks: List[str]
    patient_populations: List[str]
    accessibility_features: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class DataExtractorAgent(BaseScreeningAgent):
    """Extracts structured data from research papers."""

    def screen(
        self,
        title: str,
        abstract: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ):
        """Stub implementation - extraction agents don't screen papers."""
        from ..screening.base_agent import ScreeningResult, InclusionDecision

        return ScreeningResult(
            decision=InclusionDecision.UNCERTAIN,
            confidence=0.0,
            reasoning="Extraction agent - screening not applicable",
        )

    def extract(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str] = None,
        extraction_fields: Optional[List[str]] = None,
        topic_context: Optional[Dict[str, Any]] = None,
    ) -> ExtractedData:
        """
        Extract structured data from a paper.

        Args:
            title: Paper title
            abstract: Paper abstract
            full_text: Full text content (optional)
            extraction_fields: Specific fields to extract (if None, extracts all)
            topic_context: Optional topic context

        Returns:
            ExtractedData object
        """
        # Check if verbose mode is enabled
        is_verbose = self.debug_config.enabled and self.debug_config.level in [
            DebugLevel.DETAILED,
            DebugLevel.FULL,
        ]

        # Use provided topic_context or instance topic_context
        if topic_context:
            original_context = self.topic_context
            self.topic_context = topic_context

        prompt = self._build_extraction_prompt(title, abstract, full_text, extraction_fields)

        if is_verbose:
            fields_to_extract = extraction_fields or [
                "study_objectives",
                "methodology",
                "study_design",
                "participants",
                "interventions",
                "outcomes",
                "key_findings",
                "limitations",
                "ux_strategies",
                "adaptivity_frameworks",
                "patient_populations",
                "accessibility_features",
            ]
            logger.debug(
                f"[{self.role}] Extracting {len(fields_to_extract)} fields from paper: {title[:50]}..."
            )

        if not self.llm_client:
            if is_verbose:
                logger.debug(f"[{self.role}] LLM client not available, using fallback extraction")
            result = self._fallback_extract(title, abstract, full_text)
        else:
            # Try structured output first, fallback to parsing if needed
            try:
                if is_verbose:
                    logger.debug(f"[{self.role}] Attempting structured output extraction")
                response = self._call_llm_structured(prompt)

                # Normalize response before validation
                try:
                    normalized_data = self._normalize_extraction_response(response)
                    normalized_json = json.dumps(normalized_data)
                except Exception as norm_error:
                    logger.warning(
                        f"[{self.role}] Response normalization failed: {norm_error}. "
                        f"Attempting validation with original response."
                    )
                    normalized_json = response

                # Validate with Pydantic
                try:
                    schema_result = ExtractedDataSchema.model_validate_json(normalized_json)
                except Exception as validation_error:
                    # Extract detailed error information
                    error_msg = str(validation_error)
                    if hasattr(validation_error, "errors"):
                        # Pydantic v2 error format
                        error_details = []
                        for err in validation_error.errors():
                            field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
                            error_type = err.get("type", "unknown")
                            error_input = err.get("input", "N/A")
                            error_details.append(
                                f"Field '{field_path}': type={error_type}, received={error_input!r}"
                            )
                        detailed_error = "; ".join(error_details)
                        logger.warning(
                            f"[{self.role}] Pydantic validation failed: {detailed_error}. "
                            f"Response preview: {response[:200]}..."
                        )
                    else:
                        logger.warning(
                            f"[{self.role}] Pydantic validation failed: {error_msg}. "
                            f"Response preview: {response[:200]}..."
                        )
                    raise

                # Update with provided metadata
                schema_result.title = title
                result = self._convert_schema_to_extracted_data(schema_result)
                if is_verbose:
                    logger.debug(
                        f"[{self.role}] Structured extraction successful - "
                        f"extracted {len(result.study_objectives)} objectives, "
                        f"{len(result.outcomes)} outcomes, {len(result.key_findings)} findings"
                    )
            except Exception as e:
                logger.warning(
                    f"[{self.role}] Structured output failed, falling back to parsing: {e}"
                )
                if is_verbose:
                    logger.debug(f"[{self.role}] Falling back to text parsing extraction")
                response = self._call_llm(prompt)
                result = self._parse_extraction_response(response, title, abstract)
                if is_verbose:
                    logger.debug(f"[{self.role}] Parsed extraction completed")

        # Restore original context
        if topic_context:
            self.topic_context = original_context

        return result

    def _build_extraction_prompt(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str],
        extraction_fields: Optional[List[str]],
    ) -> str:
        """Build prompt for data extraction."""
        text_content = f"Title: {title}\n\nAbstract: {abstract}"
        if full_text:
            # Truncate if too long
            max_length = 10000
            if len(full_text) > max_length:
                full_text = full_text[:max_length] + "... [truncated]"
            text_content += f"\n\nFull Text: {full_text}"

        fields_to_extract = extraction_fields or [
            "study_objectives",
            "methodology",
            "study_design",
            "participants",
            "interventions",
            "outcomes",
            "key_findings",
            "limitations",
            "country",
            "setting",
            "sample_size",
            "detailed_outcomes",
            "quantitative_results",
            "ux_strategies",
            "adaptivity_frameworks",
            "patient_populations",
            "accessibility_features",
        ]

        prompt = f"""Extract structured data from the following research paper:

{text_content}

Please extract the following information and return it as a JSON object:

{chr(10).join(f"- {field}: " for field in fields_to_extract)}

IMPORTANT: For list fields (arrays), always return an empty array [] if no data is available.
Never return strings like "Not applicable." or "N/A" for list fields.

For each field:
- study_objectives: List of main research objectives (always return array, use [] if none found)
- methodology: Description of research methodology (use null if not available, NOT empty string "")
- study_design: Type of study (e.g., RCT, case study, survey) (use null if not available)
- participants: Description of study participants (use null if not available)
- interventions: Description of interventions or treatments (use null if not available)
- outcomes: List of measured outcomes (always return array, use [] if none found)
- key_findings: List of key findings/results (always return array, use [] if none found)
- limitations: Study limitations (use null if not available)
- country: Country where the study was conducted (use null if not available)
- setting: Study setting (e.g., hospital, community, online, academic medical center) (use null if not available)
- sample_size: Number of participants in the study (integer, use null if not available)
- detailed_outcomes: Detailed outcome measures with units and measurement methods (always return array, use [] if none found)
- quantitative_results: Quantitative results including effect sizes, confidence intervals, p-values, and statistical tests (e.g., "Mean score: 7.5 (95% CI: 7.1-7.9), p<0.001") (use null if not available)
- ux_strategies: UX design strategies mentioned (always return array, use [] if none found)
- adaptivity_frameworks: Adaptive/personalization frameworks used (always return array, use [] if none found)
- patient_populations: Patient populations studied (always return array, use [] if none found)
- accessibility_features: Accessibility features mentioned (always return array, use [] if none found)

Examples of correct format:
- If no outcomes found: "outcomes": [] (NOT "outcomes": "Not applicable.")
- If no authors found: "authors": [] (NOT "authors": "N/A")
- If no journal found: "journal": null (NOT "journal": "Not available")
- If no methodology found: "methodology": null (NOT "methodology": "" or "methodology": "Not available")

Return ONLY valid JSON matching this exact structure:
{{
  "title": "{title}",
  "authors": [],
  "year": null,
  "journal": null,
  "doi": null,
  "study_objectives": ["objective1", "objective2"],
  "methodology": "description" or null,
  "study_design": "type" or null,
  "participants": "description",
  "interventions": "description",
  "outcomes": ["outcome1", "outcome2"],
  "key_findings": ["finding1", "finding2"],
  "limitations": "description",
  "country": "United States",
  "setting": "Academic medical center",
  "sample_size": 100,
  "detailed_outcomes": ["Outcome measure (units)"],
  "quantitative_results": "Effect size: X (95% CI: Y-Z), p=0.XX",
  "ux_strategies": ["strategy1", "strategy2"],
  "adaptivity_frameworks": ["framework1"],
  "patient_populations": ["population1"],
  "accessibility_features": ["feature1"]
}}"""
        return prompt

    def _normalize_extraction_response(self, response: str) -> dict:
        """
        Normalize LLM response before Pydantic validation.

        Converts common "not available" strings to appropriate types:
        - List fields: "Not applicable." -> []
        - Optional fields: "N/A" -> null

        Args:
            response: JSON string response from LLM

        Returns:
            Normalized dictionary ready for Pydantic validation
        """
        try:
            # Parse JSON response
            data = json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Invalid JSON response: {e}") from e

        # List fields that should always be arrays
        list_fields = [
            "authors",
            "study_objectives",
            "outcomes",
            "detailed_outcomes",
            "key_findings",
            "ux_strategies",
            "adaptivity_frameworks",
            "patient_populations",
            "accessibility_features",
        ]

        # Common "not available" strings to normalize
        not_available_strings = [
            "not applicable",
            "not available",
            "n/a",
            "na",
            "none",
            "null",
            "",
        ]

        # Normalize list fields
        for field in list_fields:
            if field in data:
                value = data[field]
                # If it's a string that looks like "not available", convert to empty list
                if isinstance(value, str):
                    value_lower = value.lower().strip()
                    if value_lower in not_available_strings or value_lower.startswith("not "):
                        data[field] = []
                        logger.debug(f"Normalized {field}: '{value}' -> []")
                # If it's already a list, keep it
                elif isinstance(value, list):
                    pass
                # If it's None, convert to empty list
                elif value is None:
                    data[field] = []
                # Otherwise, try to convert to list if it's a single item
                else:
                    logger.warning(
                        f"Unexpected type for {field}: {type(value).__name__}, "
                        f"value: {value}. Converting to empty list."
                    )
                    data[field] = []

        # Normalize optional string fields (convert "not available" strings to None)
        optional_string_fields = [
            "journal",
            "doi",
            "methodology",
            "study_design",
            "participants",
            "interventions",
            "limitations",
            "country",
            "setting",
            "quantitative_results",
        ]

        for field in optional_string_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    value_lower = value.lower().strip()
                    if value_lower in not_available_strings or value_lower.startswith("not "):
                        data[field] = None
                        logger.debug(f"Normalized {field}: '{value}' -> None")

        # Normalize optional int fields
        optional_int_fields = ["year", "sample_size"]
        for field in optional_int_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str):
                    value_lower = value.lower().strip()
                    if value_lower in not_available_strings or value_lower.startswith("not "):
                        data[field] = None
                        logger.debug(f"Normalized {field}: '{value}' -> None")
                    else:
                        # Try to parse as int
                        try:
                            data[field] = int(value)
                        except (ValueError, TypeError):
                            logger.warning(
                                f"Could not parse {field} as int: {value}. Setting to None."
                            )
                            data[field] = None

        return data

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

        model_to_use = self.llm_model
        enhanced_prompt = self._inject_topic_context(prompt)

        # Enhanced logging with Rich console
        time.time()
        if self.debug_config.show_llm_calls or self.debug_config.enabled:
            prompt_preview = (
                enhanced_prompt[:200] + "..." if len(enhanced_prompt) > 200 else enhanced_prompt
            )
            print_llm_request_panel(
                model=model_to_use,
                provider=self.llm_provider,
                agent=self.role,
                temperature=self.temperature,
                prompt_length=len(enhanced_prompt),
                prompt_preview=prompt_preview,
            )

        # Validate provider (Gemini only)
        if self.llm_provider != "gemini":
            raise ValueError(
                f"Structured output only supported with Gemini. "
                f"Current provider: {self.llm_provider}"
            )

        # Use Gemini structured output
        call_start_time = time.time()
        if self.llm_provider == "gemini":
            # Gemini - request JSON in prompt, parse response
            from google.genai import types

            json_prompt = enhanced_prompt + "\n\nReturn your response as valid JSON only."
            response = self.llm_client.models.generate_content(
                model=getattr(self, "llm_model_name", self.llm_model),
                contents=json_prompt,
                config=types.GenerateContentConfig(temperature=self.temperature),
            )

            duration = time.time() - call_start_time
            content = response.text if hasattr(response, "text") else "{}"
            model_name = getattr(self, "llm_model_name", self.llm_model)
            # Extract JSON from response if wrapped in markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()

            # Extract usage_metadata and track cost
            cost = 0.0
            if self.debug_config.show_costs:
                from ..observability.cost_tracker import (
                    get_cost_tracker,
                    TokenUsage,
                    LLMCostTracker,
                )

                cost_tracker = get_cost_tracker()
                llm_cost_tracker = LLMCostTracker(cost_tracker)

                # Extract usage_metadata from Gemini response
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    usage_metadata = response.usage_metadata
                    prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0)
                    completion_tokens = getattr(usage_metadata, "candidates_token_count", 0)
                    total_tokens = getattr(usage_metadata, "total_token_count", 0)

                    # Track cost
                    llm_cost_tracker.track_gemini_response(
                        response, model_name, agent_name=self.role
                    )

                    # Calculate cost for display
                    cost = cost_tracker._calculate_cost(
                        "gemini",
                        model_name,
                        TokenUsage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                        ),
                    )

            # Enhanced logging with Rich console
            if self.debug_config.show_llm_calls or self.debug_config.enabled:
                response_preview = content[:200] + "..." if len(content) > 200 else content
                print_llm_response_panel(
                    duration=duration,
                    response_preview=response_preview,
                    tokens=None,
                    cost=cost,
                )

            return content
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def _convert_schema_to_extracted_data(
        self, schema_result: ExtractedDataSchema
    ) -> ExtractedData:
        """Convert Pydantic schema to ExtractedData dataclass."""
        return ExtractedData(
            title=schema_result.title,
            authors=schema_result.authors,
            year=schema_result.year,
            journal=schema_result.journal,
            doi=schema_result.doi,
            study_objectives=schema_result.study_objectives,
            methodology=schema_result.methodology,
            study_design=schema_result.study_design,
            participants=schema_result.participants,
            interventions=schema_result.interventions,
            outcomes=schema_result.outcomes,
            key_findings=schema_result.key_findings,
            limitations=schema_result.limitations,
            country=schema_result.country,
            setting=schema_result.setting,
            sample_size=schema_result.sample_size,
            detailed_outcomes=schema_result.detailed_outcomes,
            quantitative_results=schema_result.quantitative_results,
            ux_strategies=schema_result.ux_strategies,
            adaptivity_frameworks=schema_result.adaptivity_frameworks,
            patient_populations=schema_result.patient_populations,
            accessibility_features=schema_result.accessibility_features,
        )

    def _parse_extraction_response(self, response: str, title: str, abstract: str) -> ExtractedData:
        """Parse LLM response into ExtractedData."""
        # Try to extract JSON from response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            try:
                data = json.loads(json_str)
                return ExtractedData(
                    title=title,
                    authors=[],  # Would need to extract separately
                    year=None,
                    journal=None,
                    doi=None,
                    study_objectives=data.get("study_objectives", []),
                    methodology=data.get("methodology"),
                    study_design=data.get("study_design"),
                    participants=data.get("participants"),
                    interventions=data.get("interventions"),
                    outcomes=data.get("outcomes", []),
                    key_findings=data.get("key_findings", []),
                    limitations=data.get("limitations"),
                    country=data.get("country"),
                    setting=data.get("setting"),
                    sample_size=data.get("sample_size"),
                    detailed_outcomes=data.get("detailed_outcomes", []),
                    quantitative_results=data.get("quantitative_results"),
                    ux_strategies=data.get("ux_strategies", []),
                    adaptivity_frameworks=data.get("adaptivity_frameworks", []),
                    patient_populations=data.get("patient_populations", []),
                    accessibility_features=data.get("accessibility_features", []),
                )
            except json.JSONDecodeError:
                pass

        # Fallback: return minimal data
        return self._fallback_extract(title, abstract)

    def _fallback_extract(
        self, title: str, abstract: str, full_text: Optional[str] = None
    ) -> ExtractedData:
        """Fallback extraction using simple text parsing."""
        text = (title + " " + abstract + " " + (full_text or "")).lower()

        # Simple keyword-based extraction
        outcomes = []
        if "outcome" in text or "result" in text:
            outcomes.append("Outcomes mentioned")

        findings = []
        if "finding" in text or "conclusion" in text:
            findings.append("Findings mentioned")

        ux_strategies = []
        ux_keywords = ["user experience", "ux", "interface design", "usability"]
        for keyword in ux_keywords:
            if keyword in text:
                ux_strategies.append(keyword.title())

        return ExtractedData(
            title=title,
            authors=[],
            year=None,
            journal=None,
            doi=None,
            study_objectives=[],
            methodology=None,
            study_design=None,
            participants=None,
            interventions=None,
            outcomes=outcomes,
            key_findings=findings,
            limitations=None,
            country=None,
            setting=None,
            sample_size=None,
            detailed_outcomes=[],
            quantitative_results=None,
            ux_strategies=ux_strategies,
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        )
