"""MMAT 2018 assessor for mixed-methods studies.

The Mixed Methods Appraisal Tool (MMAT) 2018 appraises five study types:
  1. Qualitative
  2. Randomized controlled trials (RCTs)
  3. Non-randomized quantitative (observational, quasi-experimental)
  4. Quantitative descriptive (cross-sectional, survey)
  5. Mixed methods

Each study type has 5 type-specific criteria applied after 2 screening questions.
The tool supports mixed-methods systematic reviews covering staff experience, patient
safety, and quality improvement designs.

Reference: Hong, Q.N., Faber, G. et al. (2018). The Mixed Methods Appraisal Tool
(MMAT) version 2018 for information professionals and researchers. Education for
Information, 34(4), 285-291. DOI: 10.3233/EFI-180221
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import ExtractionRecord, StudyDesign
from src.models.config import SettingsConfig

logger = logging.getLogger(__name__)

MmatStudyType = Literal[
    "qualitative",
    "rct",
    "non_randomized",
    "quantitative_descriptive",
    "mixed_methods",
]


class MmatAssessment(BaseModel):
    """MMAT 2018 appraisal result for a single study."""

    paper_id: str
    study_type: MmatStudyType

    # Screening criteria (applicable to all types)
    screening_1_clear_question: bool
    screening_2_appropriate_data: bool

    # Type-specific criteria (5 per type)
    criterion_1: bool
    criterion_2: bool
    criterion_3: bool
    criterion_4: bool
    criterion_5: bool

    overall_score: int  # count of True criteria (0-5 type-specific)
    overall_summary: str
    assessment_source: Literal["llm", "heuristic"] = "llm"


class _MmatLLMResponse(BaseModel):
    screening_1_clear_question: bool = False
    screening_2_appropriate_data: bool = False
    criterion_1: bool = False
    criterion_2: bool = False
    criterion_3: bool = False
    criterion_4: bool = False
    criterion_5: bool = False
    overall_summary: str = ""


def _infer_study_type(record: ExtractionRecord) -> MmatStudyType:
    """Map StudyDesign enum to MMAT study type."""
    design = record.study_design
    if design == StudyDesign.RCT:
        return "rct"
    if design == StudyDesign.QUALITATIVE:
        return "qualitative"
    if design == StudyDesign.MIXED_METHODS:
        return "mixed_methods"
    if design == StudyDesign.CROSS_SECTIONAL:
        return "quantitative_descriptive"
    # NON_RANDOMIZED, COHORT, CASE_CONTROL, OTHER
    return "non_randomized"


def _type_specific_criteria(study_type: MmatStudyType) -> str:
    """Return the 5 type-specific MMAT 2018 criteria for a given study type."""
    if study_type == "qualitative":
        return (
            "Criterion 1: Is the qualitative approach appropriate to answer the research question?\n"
            "Criterion 2: Are the qualitative data collection methods adequate to address the research question?\n"
            "Criterion 3: Are the findings adequately derived from the data?\n"
            "Criterion 4: Is the interpretation of results sufficiently substantiated by data?\n"
            "Criterion 5: Is there coherence between qualitative data sources, collection, analysis and interpretation?"
        )
    if study_type == "rct":
        return (
            "Criterion 1: Is randomization appropriately performed?\n"
            "Criterion 2: Are the groups comparable at baseline?\n"
            "Criterion 3: Are there complete outcome data?\n"
            "Criterion 4: Are outcome assessors blinded to the intervention provided?\n"
            "Criterion 5: Did the participants adhere to the assigned intervention?"
        )
    if study_type == "non_randomized":
        return (
            "Criterion 1: Are the participants representative of the target population?\n"
            "Criterion 2: Are measurements appropriate regarding both the outcome and intervention?\n"
            "Criterion 3: Are there complete outcome data?\n"
            "Criterion 4: Are the confounders accounted for in the design and analysis?\n"
            "Criterion 5: During the study period, is the intervention administered as intended?"
        )
    if study_type == "quantitative_descriptive":
        return (
            "Criterion 1: Is the sampling strategy relevant to address the research question?\n"
            "Criterion 2: Is the sample representative of the target population?\n"
            "Criterion 3: Are the measurements appropriate?\n"
            "Criterion 4: Is the risk of nonresponse bias low?\n"
            "Criterion 5: Is the statistical analysis appropriate to answer the research question?"
        )
    # mixed_methods
    return (
        "Criterion 1: Is there an adequate rationale for using a mixed methods design?\n"
        "Criterion 2: Are the different components of the study effectively integrated?\n"
        "Criterion 3: Are the outputs of the integration of qualitative and quantitative components "
        "adequately interpreted?\n"
        "Criterion 4: Are divergences and inconsistencies between quantitative and qualitative results "
        "adequately addressed?\n"
        "Criterion 5: Do the different components of the study adhere to the quality criteria of each "
        "tradition of the methods involved?"
    )


def _build_mmat_prompt(record: ExtractionRecord, study_type: MmatStudyType, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    text_excerpt = full_text[:3000] if full_text.strip() else results
    criteria = _type_specific_criteria(study_type)
    return "\n".join(
        [
            "You are an expert systematic review methodologist applying the MMAT 2018.",
            f"Study type: {study_type.replace('_', ' ').title()}",
            "",
            "STUDY INFORMATION:",
            f"Title: {record.paper_id}",
            f"Design: {record.study_design.value if record.study_design else 'unknown'}",
            f"Setting: {record.setting or 'not reported'}",
            f"Participants: {record.participant_count or 'not reported'}",
            f"Results: {results}",
            f"Full text excerpt: {text_excerpt}",
            "",
            "MMAT 2018 SCREENING QUESTIONS (apply to all study types):",
            "Screening Q1: Are there clear research questions?",
            "Screening Q2: Do the collected data allow to address the research questions?",
            "",
            f"TYPE-SPECIFIC CRITERIA ({study_type.replace('_', ' ').upper()}):",
            criteria,
            "",
            "Return ONLY valid JSON with this exact schema:",
            '{"screening_1_clear_question": true|false, "screening_2_appropriate_data": true|false, '
            '"criterion_1": true|false, "criterion_2": true|false, "criterion_3": true|false, '
            '"criterion_4": true|false, "criterion_5": true|false, '
            '"overall_summary": "one paragraph assessment"}',
            "Answer each criterion truthfully based on available evidence. Use false when information is absent.",
        ]
    )


def _heuristic_mmat(record: ExtractionRecord, study_type: MmatStudyType) -> MmatAssessment:
    """Conservative heuristic fallback: all criteria false except screening Q1."""
    return MmatAssessment(
        paper_id=record.paper_id,
        study_type=study_type,
        screening_1_clear_question=bool((record.results_summary.get("summary") or "").strip()),
        screening_2_appropriate_data=False,
        criterion_1=False,
        criterion_2=False,
        criterion_3=False,
        criterion_4=False,
        criterion_5=False,
        overall_score=0,
        overall_summary="MMAT heuristic fallback: LLM assessment unavailable. Manual review required.",
        assessment_source="heuristic",
    )


class MmatAssessor:
    """Apply MMAT 2018 appraisal to a study record."""

    def __init__(
        self,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        provider: object | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.settings = settings
        self.provider = provider

    async def assess(
        self,
        record: ExtractionRecord,
        full_text: str = "",
    ) -> MmatAssessment:
        """Assess a study using MMAT 2018. Falls back to heuristic on LLM failure."""
        study_type = _infer_study_type(record)
        if self.llm_client is None or self.settings is None:
            return _heuristic_mmat(record, study_type)

        agent = self.settings.agents.get("quality_assessment")
        if not agent:
            return _heuristic_mmat(record, study_type)

        model = agent.model
        temperature = agent.temperature
        prompt = _build_mmat_prompt(record, study_type, full_text)
        schema = _MmatLLMResponse.model_json_schema()

        try:
            t0 = time.monotonic()
            if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
                raw, tok_in, tok_out, cw, cr = await self.llm_client.complete_with_usage(
                    prompt, model=model, temperature=temperature, json_schema=schema
                )
                latency_ms = int((time.monotonic() - t0) * 1000)
                cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
                await self.provider.log_cost(
                    model,
                    tok_in,
                    tok_out,
                    cost,
                    latency_ms,
                    phase="quality_mmat",
                    cache_read_tokens=cr,
                    cache_write_tokens=cw,
                )
            else:
                raw = await self.llm_client.complete(prompt, model=model, temperature=temperature, json_schema=schema)
            parsed = _MmatLLMResponse.model_validate_json(raw)
            score = sum(
                [
                    parsed.criterion_1,
                    parsed.criterion_2,
                    parsed.criterion_3,
                    parsed.criterion_4,
                    parsed.criterion_5,
                ]
            )
            return MmatAssessment(
                paper_id=record.paper_id,
                study_type=study_type,
                screening_1_clear_question=parsed.screening_1_clear_question,
                screening_2_appropriate_data=parsed.screening_2_appropriate_data,
                criterion_1=parsed.criterion_1,
                criterion_2=parsed.criterion_2,
                criterion_3=parsed.criterion_3,
                criterion_4=parsed.criterion_4,
                criterion_5=parsed.criterion_5,
                overall_score=score,
                overall_summary=parsed.overall_summary or f"MMAT score: {score}/5.",
                assessment_source="llm",
            )
        except Exception as exc:
            logger.warning("MMAT LLM assessment failed for %s (%s); using heuristic.", record.paper_id, exc)
            return _heuristic_mmat(record, study_type)
