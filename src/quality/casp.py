"""CASP assessor for qualitative studies - LLM-based with heuristic fallback."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from src.llm.gemini_client import GeminiClient
from src.models import ExtractionRecord
from src.models.config import SettingsConfig

logger = logging.getLogger(__name__)


class CaspAssessment(BaseModel):
    paper_id: str
    design_appropriate: bool
    recruitment_strategy: bool
    data_collection_rigorous: bool
    reflexivity_considered: bool
    ethics_considered: bool
    analysis_rigorous: bool
    findings_clear: bool
    value_of_research: bool
    overall_summary: str


class _CaspLLMResponse(BaseModel):
    design_appropriate: bool = False
    recruitment_strategy: bool = True
    data_collection_rigorous: bool = False
    reflexivity_considered: bool = False
    ethics_considered: bool = True
    analysis_rigorous: bool = False
    findings_clear: bool = True
    value_of_research: bool = True
    overall_summary: str = ""


def _build_casp_prompt(record: ExtractionRecord, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    text_excerpt = full_text[:3000] if full_text.strip() else results
    return "\n".join([
        "You are an expert systematic review methodologist.",
        "Assess this qualitative study using the CASP (Critical Appraisal Skills Programme) checklist.",
        "",
        f"Intervention / topic: {record.intervention_description[:400]}",
        f"Results summary: {results}",
        "",
        "Text excerpt:",
        text_excerpt,
        "",
        "Answer each CASP question as true or false:",
        "1. design_appropriate: Was a qualitative methodology appropriate for this research question?",
        "2. recruitment_strategy: Was the recruitment strategy appropriate to the aims of the research?",
        "3. data_collection_rigorous: Was the data collection sufficiently rigorous?",
        "4. reflexivity_considered: Was the relationship between researcher and participants considered?",
        "5. ethics_considered: Have ethical issues been taken into consideration?",
        "6. analysis_rigorous: Was the data analysis sufficiently rigorous?",
        "7. findings_clear: Is there a clear statement of findings?",
        "8. value_of_research: How valuable is the research?",
        "Also provide a brief overall_summary (1-2 sentences).",
        "",
        "Return ONLY valid JSON matching the schema.",
    ])


class CaspAssessor:
    """Produce typed CASP-style outputs. Uses Gemini Pro when available; heuristic fallback otherwise."""

    def __init__(
        self,
        llm_client: GeminiClient | None = None,
        settings: SettingsConfig | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings

    def _heuristic(self, record: ExtractionRecord) -> CaspAssessment:
        summary = (record.results_summary.get("summary") or "").lower()
        has_methods = any(token in summary for token in ["interview", "focus group", "thematic"])
        return CaspAssessment(
            paper_id=record.paper_id,
            design_appropriate=has_methods,
            recruitment_strategy=True,
            data_collection_rigorous=has_methods,
            reflexivity_considered=False,
            ethics_considered=True,
            analysis_rigorous=has_methods,
            findings_clear=True,
            value_of_research=True,
            overall_summary="CASP heuristic pass with conservative defaults.",
        )

    async def assess(self, record: ExtractionRecord, full_text: str = "") -> CaspAssessment:
        if self.llm_client is not None and self.settings is not None:
            try:
                agent = self.settings.agents.get("quality_assessment")
                model = agent.model if agent else "google-gla:gemini-2.5-pro"
                temperature = agent.temperature if agent else 0.2
                prompt = _build_casp_prompt(record, full_text)
                schema = _CaspLLMResponse.model_json_schema()
                raw = await self.llm_client.complete(
                    prompt, model=model, temperature=temperature, json_schema=schema
                )
                parsed = _CaspLLMResponse.model_validate_json(raw)
                summary = parsed.overall_summary or "LLM-based CASP assessment."
                return CaspAssessment(
                    paper_id=record.paper_id,
                    design_appropriate=parsed.design_appropriate,
                    recruitment_strategy=parsed.recruitment_strategy,
                    data_collection_rigorous=parsed.data_collection_rigorous,
                    reflexivity_considered=parsed.reflexivity_considered,
                    ethics_considered=parsed.ethics_considered,
                    analysis_rigorous=parsed.analysis_rigorous,
                    findings_clear=parsed.findings_clear,
                    value_of_research=parsed.value_of_research,
                    overall_summary=summary,
                )
            except Exception as exc:
                logger.warning(
                    "CASP LLM assessment failed for %s (%s); using heuristic.",
                    record.paper_id[:12],
                    type(exc).__name__,
                )
        return self._heuristic(record)
