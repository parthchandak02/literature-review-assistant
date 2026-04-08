"""ROBINS-I assessor for non-randomized studies - LLM-based with heuristic fallback."""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import ExtractionRecord, RobinsIAssessment, RobinsIJudgment
from src.models.config import SettingsConfig

logger = logging.getLogger(__name__)

_ROBINS_JUDGMENT = Literal["low", "moderate", "serious", "critical", "no_information"]


class _RobinsILLMResponse(BaseModel):
    # Defaults are no_information, not moderate. If the LLM cannot assess a domain
    # from the available text, it should say so explicitly rather than silently
    # defaulting to moderate. Uniform moderate across all 7 domains is the classic
    # signal of insufficient data -- making no_information the default surfaces that
    # honestly in the traffic-light figure and GRADE assessment.
    domain_1_confounding: _ROBINS_JUDGMENT = "no_information"
    domain_1_rationale: str = "Insufficient information available from abstract alone."
    domain_2_selection: _ROBINS_JUDGMENT = "no_information"
    domain_2_rationale: str = "Insufficient information available from abstract alone."
    domain_3_classification: _ROBINS_JUDGMENT = "no_information"
    domain_3_rationale: str = "Insufficient information available from abstract alone."
    domain_4_deviations: _ROBINS_JUDGMENT = "no_information"
    domain_4_rationale: str = "Insufficient information available from abstract alone."
    domain_5_missing_data: _ROBINS_JUDGMENT = "no_information"
    domain_5_rationale: str = "Insufficient information available from abstract alone."
    domain_6_measurement: _ROBINS_JUDGMENT = "no_information"
    domain_6_rationale: str = "Insufficient information available from abstract alone."
    domain_7_reported_result: _ROBINS_JUDGMENT = "no_information"
    domain_7_rationale: str = "Insufficient information available from abstract alone."
    overall_judgment: _ROBINS_JUDGMENT = "no_information"
    overall_rationale: str = "Insufficient information to assess overall risk of bias."


def _to_robins_judgment(value: str) -> RobinsIJudgment:
    mapping = {
        "low": RobinsIJudgment.LOW,
        "moderate": RobinsIJudgment.MODERATE,
        "serious": RobinsIJudgment.SERIOUS,
        "critical": RobinsIJudgment.CRITICAL,
        "no_information": RobinsIJudgment.NO_INFORMATION,
    }
    return mapping.get(str(value).lower(), RobinsIJudgment.MODERATE)


def _worst(values: list[RobinsIJudgment]) -> RobinsIJudgment:
    ranking = {
        RobinsIJudgment.LOW: 0,
        RobinsIJudgment.MODERATE: 1,
        RobinsIJudgment.SERIOUS: 2,
        RobinsIJudgment.CRITICAL: 3,
        RobinsIJudgment.NO_INFORMATION: 4,
    }
    return max(values, key=lambda item: ranking[item])


def _build_robins_prompt(record: ExtractionRecord, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    has_full_text = bool(full_text.strip()) and len(full_text.strip()) > 200
    text_excerpt = full_text[:3000] if has_full_text else results
    text_source = "full text excerpt" if has_full_text else "abstract/results summary (full text unavailable)"
    return "\n".join(
        [
            "You are an expert systematic review methodologist conducting a ROBINS-I risk-of-bias assessment.",
            "Assess the seven ROBINS-I domains for the following non-randomized study.",
            "",
            f"Intervention: {record.intervention_description[:400]}",
            f"Comparator: {record.comparator_description or 'not reported'}",
            f"Setting: {record.setting or 'not reported'}",
            f"Participants: {record.participant_count or 'not reported'}",
            f"Results summary: {results}",
            "",
            f"Available text ({text_source}):",
            text_excerpt,
            "",
            "ROBINS-I Domain Assessment Rules:",
            "- Use 'low', 'moderate', 'serious', 'critical', or 'no_information' for each domain.",
            "- CRITICAL: use 'no_information' when you cannot assess a domain from the available text.",
            "  Do NOT guess 'moderate' just because you have no information -- 'no_information' is the",
            "  correct response when evidence is insufficient. Uniform 'moderate' across all domains",
            "  is scientifically invalid and will be flagged as a pipeline error.",
            "- Domains that CAN often be assessed from abstract text alone: D2, D6, D7.",
            "- Domains that USUALLY require full text to assess meaningfully: D1, D3, D4.",
            "  Use 'no_information' for these when only abstract is available.",
            "",
            "D1 - Bias due to Confounding: Were important confounders identified and controlled for?",
            "  (Requires information about study design, adjustment variables -- often absent in abstracts.)",
            "D2 - Bias in Selection of Participants: Is the participant selection method described?",
            "  Were eligible participants excluded in ways that could bias results?",
            "D3 - Bias in Classification of Interventions: Were intervention vs control groups classified",
            "  consistently using reliable, pre-specified criteria?",
            "D4 - Bias due to Deviations from Intended Interventions: Did participants receive the",
            "  intended intervention? Were there protocol deviations or contamination?",
            "D5 - Bias due to Missing Data: Are there missing outcome data, dropouts, or loss to follow-up?",
            "  If sample sizes differ between enrollment and analysis, flag this.",
            "D6 - Bias in Measurement of Outcomes: Were outcomes measured objectively and consistently?",
            "  Was the assessor blinded to intervention status?",
            "D7 - Bias in Selection of the Reported Result: Does the abstract/paper report all outcomes",
            "  that were measured, or is there evidence of selective reporting or outcome switching?",
            "Overall: apply worst-domain logic using only domains with actual information (not no_information).",
            "  If no domain can be assessed, overall should also be 'no_information'.",
            "",
            "Return ONLY valid JSON matching the schema. Provide a specific 1-2 sentence rationale",
            "for each domain explaining what evidence (or lack thereof) drove your rating.",
        ]
    )


class RobinsIAssessor:
    """Assess seven ROBINS-I domains. Uses Gemini Pro when available; heuristic fallback otherwise."""

    def __init__(
        self,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        provider: object | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings
        self.provider = provider

    _CONFOUNDING_SERIOUS_SIGNALS = ("confounding present", "unmeasured confound", "major confound")
    _MISSING_DATA_SERIOUS_SIGNALS = ("missing data", "missing outcome", "loss to follow-up", "high attrition")
    _REPORTING_SERIOUS_SIGNALS = ("selective reporting", "selective outcome", "outcome switching", "reporting bias")

    def _heuristic(self, record: ExtractionRecord) -> RobinsIAssessment:
        """Conservative heuristic fallback when LLM call fails.

        Defaults to MODERATE but escalates individual domains to SERIOUS when
        the results summary contains well-known risk-of-bias signal phrases.
        """
        corpus = " ".join(
            [
                record.results_summary.get("summary", ""),
                record.intervention_description or "",
                record.setting or "",
            ]
        ).lower()

        def _judge(signals: tuple) -> RobinsIJudgment:
            return RobinsIJudgment.SERIOUS if any(s in corpus for s in signals) else RobinsIJudgment.MODERATE

        d1 = _judge(self._CONFOUNDING_SERIOUS_SIGNALS)
        d5 = _judge(self._MISSING_DATA_SERIOUS_SIGNALS)
        d7 = _judge(self._REPORTING_SERIOUS_SIGNALS)
        mod = RobinsIJudgment.MODERATE
        overall = _worst([d1, d5, d7, mod])

        return RobinsIAssessment(
            paper_id=record.paper_id,
            domain_1_confounding=d1,
            domain_1_rationale="Heuristic fallback: LLM unavailable; signal-based estimate applied.",
            domain_2_selection=mod,
            domain_2_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_3_classification=mod,
            domain_3_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_4_deviations=mod,
            domain_4_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_5_missing_data=d5,
            domain_5_rationale="Heuristic fallback: LLM unavailable; signal-based estimate applied.",
            domain_6_measurement=mod,
            domain_6_rationale="Heuristic fallback: LLM unavailable; conservative default applied.",
            domain_7_reported_result=d7,
            domain_7_rationale="Heuristic fallback: LLM unavailable; signal-based estimate applied.",
            overall_judgment=overall,
            overall_rationale="Heuristic fallback: worst-domain logic applied to signal-based estimates.",
            assessment_source="heuristic",
            fallback_used=True,
        )

    async def assess(self, record: ExtractionRecord, full_text: str = "") -> RobinsIAssessment:
        if self.llm_client is not None and self.settings is not None:
            try:
                agent = self.settings.agents.get("quality_assessment")
                if agent is None:
                    raise ValueError("quality_assessment agent not configured in settings.yaml")
                model = agent.model
                temperature = agent.temperature
                prompt = _build_robins_prompt(record, full_text)
                if self.provider is not None:
                    await self.provider.reserve_call_slot("quality_assessment")
                t0 = time.monotonic()
                if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
                    parsed, tok_in, tok_out, cw, cr, _retries = await self.llm_client.complete_validated(
                        prompt,
                        model=model,
                        temperature=temperature,
                        response_model=_RobinsILLMResponse,
                    )
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
                    await self.provider.log_cost(
                        model,
                        tok_in,
                        tok_out,
                        cost,
                        latency_ms,
                        phase="quality_robins_i",
                        cache_read_tokens=cr,
                        cache_write_tokens=cw,
                    )
                else:
                    schema = _RobinsILLMResponse.model_json_schema()
                    raw = await self.llm_client.complete(
                        prompt, model=model, temperature=temperature, json_schema=schema
                    )
                    parsed = _RobinsILLMResponse.model_validate_json(raw)
                d1 = _to_robins_judgment(parsed.domain_1_confounding)
                d2 = _to_robins_judgment(parsed.domain_2_selection)
                d3 = _to_robins_judgment(parsed.domain_3_classification)
                d4 = _to_robins_judgment(parsed.domain_4_deviations)
                d5 = _to_robins_judgment(parsed.domain_5_missing_data)
                d6 = _to_robins_judgment(parsed.domain_6_measurement)
                d7 = _to_robins_judgment(parsed.domain_7_reported_result)
                overall = _to_robins_judgment(parsed.overall_judgment)
                # Uniformity check: all 7 domains identical and moderate signals LLM defaulted
                # rather than actually assessing. Log a warning so the audit trail captures this.
                all_domain_values = {d1, d2, d3, d4, d5, d6, d7}
                if len(all_domain_values) == 1 and d1 == RobinsIJudgment.MODERATE:
                    logger.warning(
                        "ROBINS-I uniformity detected for %s: all 7 domains rated MODERATE. "
                        "This likely means the LLM lacked sufficient text to discriminate domains. "
                        "Consider full-text retrieval to improve domain-level assessment.",
                        record.paper_id[:12],
                    )
                return RobinsIAssessment(
                    paper_id=record.paper_id,
                    domain_1_confounding=d1,
                    domain_1_rationale=parsed.domain_1_rationale or "LLM assessment.",
                    domain_2_selection=d2,
                    domain_2_rationale=parsed.domain_2_rationale or "LLM assessment.",
                    domain_3_classification=d3,
                    domain_3_rationale=parsed.domain_3_rationale or "LLM assessment.",
                    domain_4_deviations=d4,
                    domain_4_rationale=parsed.domain_4_rationale or "LLM assessment.",
                    domain_5_missing_data=d5,
                    domain_5_rationale=parsed.domain_5_rationale or "LLM assessment.",
                    domain_6_measurement=d6,
                    domain_6_rationale=parsed.domain_6_rationale or "LLM assessment.",
                    domain_7_reported_result=d7,
                    domain_7_rationale=parsed.domain_7_rationale or "LLM assessment.",
                    overall_judgment=overall,
                    overall_rationale=parsed.overall_rationale or "LLM overall judgment.",
                    assessment_source="llm",
                    fallback_used=False,
                )
            except Exception as exc:
                # Log full error message so quota/auth errors are diagnosable.
                logger.warning(
                    "ROBINS-I LLM assessment failed for %s (%s: %s); using heuristic. "
                    "If all papers fail, check API quota for quality_assessment model.",
                    record.paper_id[:12],
                    type(exc).__name__,
                    str(exc)[:200],
                )
        return self._heuristic(record)
