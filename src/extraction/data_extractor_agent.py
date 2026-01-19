"""
Data Extraction Agent

Extracts structured data from research papers using LLM with structured outputs.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
import logging
import time

from rich.console import Console
from rich.panel import Panel

from ..screening.base_agent import BaseScreeningAgent
from ..schemas.extraction_schemas import ExtractedDataSchema
from ..config.debug_config import DebugLevel

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ExtractedData:
    """Structured data extracted from a paper."""

    title: str
    authors: List[str]
    year: Optional[int]
    journal: Optional[str]
    doi: Optional[str]
    study_objectives: List[str]
    methodology: str
    study_design: Optional[str]
    participants: Optional[str]
    interventions: Optional[str]
    outcomes: List[str]
    key_findings: List[str]
    limitations: Optional[str]
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
                "study_objectives", "methodology", "study_design", "participants",
                "interventions", "outcomes", "key_findings", "limitations",
                "ux_strategies", "adaptivity_frameworks", "patient_populations",
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
                schema_result = ExtractedDataSchema.model_validate_json(response)
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
                logger.warning(f"Structured output failed, falling back to parsing: {e}")
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
            "ux_strategies",
            "adaptivity_frameworks",
            "patient_populations",
            "accessibility_features",
        ]

        prompt = f"""Extract structured data from the following research paper:

{text_content}

Please extract the following information and return it as a JSON object:

{chr(10).join(f"- {field}: " for field in fields_to_extract)}

For each field:
- study_objectives: List of main research objectives
- methodology: Description of research methodology
- study_design: Type of study (e.g., RCT, case study, survey)
- participants: Description of study participants
- interventions: Description of interventions or treatments
- outcomes: List of measured outcomes
- key_findings: List of key findings/results
- limitations: Study limitations
- ux_strategies: UX design strategies mentioned
- adaptivity_frameworks: Adaptive/personalization frameworks used
- patient_populations: Patient populations studied
- accessibility_features: Accessibility features mentioned

Return ONLY valid JSON matching this exact structure:
{{
  "title": "{title}",
  "authors": [],
  "year": null,
  "journal": null,
  "doi": null,
  "study_objectives": ["objective1", "objective2"],
  "methodology": "description",
  "study_design": "type",
  "participants": "description",
  "interventions": "description",
  "outcomes": ["outcome1", "outcome2"],
  "key_findings": ["finding1", "finding2"],
  "limitations": "description",
  "ux_strategies": ["strategy1", "strategy2"],
  "adaptivity_frameworks": ["framework1"],
  "patient_populations": ["population1"],
  "accessibility_features": ["feature1"]
}}"""
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

        model_to_use = self.llm_model
        enhanced_prompt = self._inject_topic_context(prompt)

        # Enhanced logging with Rich console
        start_time = time.time()
        if self.debug_config.show_llm_calls or self.debug_config.enabled:
            prompt_preview = (
                enhanced_prompt[:200] + "..." if len(enhanced_prompt) > 200 else enhanced_prompt
            )
            console.print(
                Panel(
                    f"[bold cyan]LLM Call (Structured Output)[/bold cyan]\n"
                    f"[yellow]Model:[/yellow] {model_to_use} ({self.llm_provider})\n"
                    f"[yellow]Agent:[/yellow] {self.role}\n"
                    f"[yellow]Temperature:[/yellow] {self.temperature}\n"
                    f"[yellow]Prompt length:[/yellow] {len(enhanced_prompt)} chars\n"
                    f"[yellow]Prompt preview:[/yellow]\n{prompt_preview}",
                    title="[bold]→ LLM Request[/bold]",
                    border_style="cyan",
                )
            )

        # Use structured output if available
        call_start_time = time.time()
        if self.llm_provider == "openai":
            # OpenAI supports JSON mode
            response = self.llm_client.chat.completions.create(
                model=model_to_use,
                messages=[{"role": "user", "content": enhanced_prompt}],
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Force JSON output
            )
            
            duration = time.time() - call_start_time
            content = response.choices[0].message.content or "{}"
            tokens = response.usage.total_tokens if hasattr(response, "usage") else None
            
            # Track cost if enabled
            if self.debug_config.show_costs and hasattr(response, "usage"):
                from ..observability.cost_tracker import get_cost_tracker
                cost_tracker = get_cost_tracker()
                cost_tracker.record_call(
                    "openai",
                    model_to_use,
                    type(
                        "Usage",
                        (),
                        {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        },
                    )(),
                    agent_name=self.role,
                )
            
            # Enhanced logging with Rich console
            if self.debug_config.show_llm_calls or self.debug_config.enabled:
                response_preview = content[:200] + "..." if len(content) > 200 else content
                token_info = f"\n[yellow]Tokens:[/yellow] {tokens}" if tokens else ""
                console.print(
                    Panel(
                        f"[bold green]LLM Response[/bold green]\n"
                        f"[yellow]Duration:[/yellow] {duration:.2f}s{token_info}\n"
                        f"[yellow]Response preview:[/yellow]\n{response_preview}",
                        title="[bold]← LLM Response[/bold]",
                        border_style="green",
                    )
                )
            
            return content
        elif self.llm_provider == "anthropic":
            # Anthropic - request JSON in prompt, parse response
            json_prompt = enhanced_prompt + "\n\nReturn your response as valid JSON only."
            response = self.llm_client.messages.create(
                model="claude-3-opus-20240229"
                if "gpt-4" in model_to_use
                else "claude-3-haiku-20240307",
                max_tokens=2000,
                temperature=self.temperature,
                messages=[{"role": "user", "content": json_prompt}],
            )
            
            duration = time.time() - call_start_time
            content = response.content[0].text if response.content else "{}"
            # Extract JSON from response if wrapped in markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            # Track cost if enabled
            if self.debug_config.show_costs and hasattr(response, "usage"):
                from ..observability.cost_tracker import get_cost_tracker
                cost_tracker = get_cost_tracker()
                cost_tracker.record_call(
                    "anthropic",
                    model_to_use,
                    type(
                        "Usage",
                        (),
                        {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                        },
                    )(),
                    agent_name=self.role,
                )
            
            # Enhanced logging with Rich console
            if self.debug_config.show_llm_calls or self.debug_config.enabled:
                response_preview = content[:200] + "..." if len(content) > 200 else content
                console.print(
                    Panel(
                        f"[bold green]LLM Response[/bold green]\n"
                        f"[yellow]Duration:[/yellow] {duration:.2f}s\n"
                        f"[yellow]Response preview:[/yellow]\n{response_preview}",
                        title="[bold]← LLM Response[/bold]",
                        border_style="green",
                    )
                )
            
            return content
        elif self.llm_provider == "gemini":
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
            # Extract JSON from response if wrapped in markdown
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            # Enhanced logging with Rich console
            if self.debug_config.show_llm_calls or self.debug_config.enabled:
                response_preview = content[:200] + "..." if len(content) > 200 else content
                console.print(
                    Panel(
                        f"[bold green]LLM Response[/bold green]\n"
                        f"[yellow]Duration:[/yellow] {duration:.2f}s\n"
                        f"[yellow]Response preview:[/yellow]\n{response_preview}",
                        title="[bold]← LLM Response[/bold]",
                        border_style="green",
                    )
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
                    methodology=data.get("methodology", ""),
                    study_design=data.get("study_design"),
                    participants=data.get("participants"),
                    interventions=data.get("interventions"),
                    outcomes=data.get("outcomes", []),
                    key_findings=data.get("key_findings", []),
                    limitations=data.get("limitations"),
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
            methodology="Not extracted",
            study_design=None,
            participants=None,
            interventions=None,
            outcomes=outcomes,
            key_findings=findings,
            limitations=None,
            ux_strategies=ux_strategies,
            adaptivity_frameworks=[],
            patient_populations=[],
            accessibility_features=[],
        )
