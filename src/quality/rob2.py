"""RoB 2 assessor for randomized studies - LLM-based with heuristic fallback."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.models import ExtractionRecord, RiskOfBiasJudgment, RoB2Assessment
from src.models.config import SettingsConfig
from src.quality.runner import QualityLLMRunner

logger = logging.getLogger(__name__)

_ROB2_JUDGMENT = Literal["low", "some_concerns", "high"]


class _Rob2LLMResponse(BaseModel):
    # Domains default to None (missing), never to a judgment: a domain the
    # model omitted must surface as not_assessed, not as a risk level.
    domain_1_randomization: _ROB2_JUDGMENT | None = None
    domain_1_rationale: str = ""
    domain_2_deviations: _ROB2_JUDGMENT | None = None
    domain_2_rationale: str = ""
    domain_3_missing_data: _ROB2_JUDGMENT | None = None
    domain_3_rationale: str = ""
    domain_4_measurement: _ROB2_JUDGMENT | None = None
    domain_4_rationale: str = ""
    domain_5_selection: _ROB2_JUDGMENT | None = None
    domain_5_rationale: str = ""
    overall_rationale: str = ""


_MISSING_DOMAIN_RATIONALE = "Not assessed: domain judgment missing or unparseable in assessor output."


def _to_rob2_judgment(value: str | None) -> RiskOfBiasJudgment:
    mapping = {
        "low": RiskOfBiasJudgment.LOW,
        "some_concerns": RiskOfBiasJudgment.SOME_CONCERNS,
        "high": RiskOfBiasJudgment.HIGH,
    }
    if value is None:
        return RiskOfBiasJudgment.NOT_ASSESSED
    return mapping.get(str(value).strip().lower(), RiskOfBiasJudgment.NOT_ASSESSED)


def compute_rob2_overall(domains: list[RiskOfBiasJudgment]) -> RiskOfBiasJudgment:
    """Deterministic RoB 2 overall judgment.

    Any high -> high; otherwise any missing domain -> not_assessed (an
    incomplete assessment can never be low); any some concerns -> some
    concerns; all five low -> low.
    """
    if RiskOfBiasJudgment.HIGH in domains:
        return RiskOfBiasJudgment.HIGH
    if not domains or RiskOfBiasJudgment.NOT_ASSESSED in domains:
        return RiskOfBiasJudgment.NOT_ASSESSED
    if RiskOfBiasJudgment.SOME_CONCERNS in domains:
        return RiskOfBiasJudgment.SOME_CONCERNS
    return RiskOfBiasJudgment.LOW


def _domain_rationale(judgment: RiskOfBiasJudgment, rationale: str) -> str:
    if judgment == RiskOfBiasJudgment.NOT_ASSESSED:
        return _MISSING_DOMAIN_RATIONALE
    return rationale or "LLM assessment."


def _build_rob2_prompt(record: ExtractionRecord, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    text_excerpt = full_text[:3000] if full_text.strip() else results
    return "\n".join(
        [
            "You are an expert systematic review methodologist.",
            "Assess Risk of Bias using the RoB 2 tool for the following randomized controlled trial.",
            "",
            f"Intervention: {record.intervention_description[:400]}",
            f"Comparator: {record.comparator_description or 'not reported'}",
            f"Setting: {record.setting or 'not reported'}",
            f"Participants: {record.participant_count or 'not reported'}",
            f"Results summary: {results}",
            "",
            "Text excerpt:",
            text_excerpt,
            "",
            "RoB 2 Domains - assign 'low', 'some_concerns', or 'high' for each:",
            "D1 - Randomization process: Was allocation sequence truly random? Was it concealed?",
            "D2 - Deviations from intended interventions: Were there deviations? Were participants aware?",
            "D3 - Missing outcome data: Were outcome data available for all (or nearly all) participants?",
            "D4 - Measurement of the outcome: Was the outcome measured appropriately and consistently?",
            "D5 - Selection of the reported result: Was the result selected from multiple analyses?",
            "Every domain D1-D5 is required. The overall judgment is computed from the domains in code.",
            "",
            "Return ONLY valid JSON matching the schema. Provide a 1-2 sentence rationale per domain",
            "and a 1-2 sentence overall_rationale.",
        ]
    )


class Rob2Assessor:
    """Assess five RoB 2 domains. Uses Gemini Pro when available; heuristic fallback otherwise."""

    def __init__(
        self,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        provider: object | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings
        self.provider = provider

    def _heuristic(self, record: ExtractionRecord) -> RoB2Assessment:
        """Fallback when the LLM call fails: every domain is not_assessed.

        No domain receives a risk level without evidence, and the overall is
        not_assessed so GRADE and exports treat the study as unappraised.
        """
        na = RiskOfBiasJudgment.NOT_ASSESSED
        rationale = "Not assessed: LLM assessment unavailable (heuristic fallback)."
        return RoB2Assessment(
            paper_id=record.paper_id,
            domain_1_randomization=na,
            domain_1_rationale=rationale,
            domain_2_deviations=na,
            domain_2_rationale=rationale,
            domain_3_missing_data=na,
            domain_3_rationale=rationale,
            domain_4_measurement=na,
            domain_4_rationale=rationale,
            domain_5_selection=na,
            domain_5_rationale=rationale,
            overall_judgment=na,
            overall_rationale=rationale,
            assessment_source="heuristic",
            fallback_used=True,
        )

    @staticmethod
    def _from_llm(paper_id: str, parsed: _Rob2LLMResponse) -> RoB2Assessment:
        d1 = _to_rob2_judgment(parsed.domain_1_randomization)
        d2 = _to_rob2_judgment(parsed.domain_2_deviations)
        d3 = _to_rob2_judgment(parsed.domain_3_missing_data)
        d4 = _to_rob2_judgment(parsed.domain_4_measurement)
        d5 = _to_rob2_judgment(parsed.domain_5_selection)
        overall = compute_rob2_overall([d1, d2, d3, d4, d5])
        if overall == RiskOfBiasJudgment.NOT_ASSESSED:
            overall_rationale = "Incomplete assessment: one or more RoB 2 domains were not assessed."
        else:
            overall_rationale = parsed.overall_rationale or "Overall judgment derived from domain judgments."
        return RoB2Assessment(
            paper_id=paper_id,
            domain_1_randomization=d1,
            domain_1_rationale=_domain_rationale(d1, parsed.domain_1_rationale),
            domain_2_deviations=d2,
            domain_2_rationale=_domain_rationale(d2, parsed.domain_2_rationale),
            domain_3_missing_data=d3,
            domain_3_rationale=_domain_rationale(d3, parsed.domain_3_rationale),
            domain_4_measurement=d4,
            domain_4_rationale=_domain_rationale(d4, parsed.domain_4_rationale),
            domain_5_selection=d5,
            domain_5_rationale=_domain_rationale(d5, parsed.domain_5_rationale),
            overall_judgment=overall,
            overall_rationale=overall_rationale,
            assessment_source="llm",
            fallback_used=False,
        )

    async def assess(self, record: ExtractionRecord, full_text: str = "") -> RoB2Assessment:
        if self.llm_client is not None and self.settings is not None:
            try:
                prompt = _build_rob2_prompt(record, full_text)
                runner = QualityLLMRunner(self.llm_client, self.settings, self.provider)
                parsed, _metrics = await runner.run_validated(
                    agent_key="quality_assessment",
                    phase_name="quality_rob2",
                    prompt=prompt,
                    response_model=_Rob2LLMResponse,
                )
                return self._from_llm(record.paper_id, parsed)
            except Exception as exc:
                logger.warning(
                    "RoB 2 LLM assessment failed for %s (%s); using heuristic.",
                    record.paper_id[:12],
                    type(exc).__name__,
                )
        return self._heuristic(record)
