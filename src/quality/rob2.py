"""RoB 2 assessor for randomized studies - LLM-based with heuristic fallback."""

from __future__ import annotations

import logging
import time
from typing import Literal

from pydantic import BaseModel

from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import ExtractionRecord, RiskOfBiasJudgment, RoB2Assessment
from src.models.config import SettingsConfig

logger = logging.getLogger(__name__)

_ROB2_JUDGMENT = Literal["low", "some_concerns", "high"]


class _Rob2LLMResponse(BaseModel):
    domain_1_randomization: _ROB2_JUDGMENT = "some_concerns"
    domain_1_rationale: str = ""
    domain_2_deviations: _ROB2_JUDGMENT = "some_concerns"
    domain_2_rationale: str = ""
    domain_3_missing_data: _ROB2_JUDGMENT = "low"
    domain_3_rationale: str = ""
    domain_4_measurement: _ROB2_JUDGMENT = "some_concerns"
    domain_4_rationale: str = ""
    domain_5_selection: _ROB2_JUDGMENT = "low"
    domain_5_rationale: str = ""
    overall_judgment: _ROB2_JUDGMENT = "some_concerns"
    overall_rationale: str = ""


def _to_rob2_judgment(value: str) -> RiskOfBiasJudgment:
    mapping = {
        "low": RiskOfBiasJudgment.LOW,
        "some_concerns": RiskOfBiasJudgment.SOME_CONCERNS,
        "high": RiskOfBiasJudgment.HIGH,
    }
    return mapping.get(str(value).lower(), RiskOfBiasJudgment.SOME_CONCERNS)


def _max_judgment(values: list[RiskOfBiasJudgment]) -> RiskOfBiasJudgment:
    if RiskOfBiasJudgment.HIGH in values:
        return RiskOfBiasJudgment.HIGH
    if RiskOfBiasJudgment.SOME_CONCERNS in values:
        return RiskOfBiasJudgment.SOME_CONCERNS
    return RiskOfBiasJudgment.LOW


def _build_rob2_prompt(record: ExtractionRecord, full_text: str) -> str:
    results = record.results_summary.get("summary", "")[:2000]
    text_excerpt = full_text[:3000] if full_text.strip() else results
    return "\n".join([
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
        "Overall: any 'high' -> 'high'; any 'some_concerns' -> 'some_concerns'; else 'low'.",
        "",
        "Return ONLY valid JSON matching the schema. Provide a 1-2 sentence rationale per domain.",
    ])


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
        summary = (record.results_summary.get("summary") or "").lower()
        d1 = RiskOfBiasJudgment.LOW if "random" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d2 = RiskOfBiasJudgment.LOW if "protocol" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d3 = RiskOfBiasJudgment.HIGH if "missing data" in summary else RiskOfBiasJudgment.LOW
        d4 = RiskOfBiasJudgment.LOW if "validated" in summary else RiskOfBiasJudgment.SOME_CONCERNS
        d5 = RiskOfBiasJudgment.SOME_CONCERNS if "selective" in summary else RiskOfBiasJudgment.LOW
        overall = _max_judgment([d1, d2, d3, d4, d5])
        return RoB2Assessment(
            paper_id=record.paper_id,
            domain_1_randomization=d1,
            domain_1_rationale="Heuristic randomization signal check.",
            domain_2_deviations=d2,
            domain_2_rationale="Heuristic protocol deviation signal check.",
            domain_3_missing_data=d3,
            domain_3_rationale="Heuristic missing-data signal check.",
            domain_4_measurement=d4,
            domain_4_rationale="Heuristic measurement validity signal check.",
            domain_5_selection=d5,
            domain_5_rationale="Heuristic reporting-selection signal check.",
            overall_judgment=overall,
            overall_rationale="Overall follows RoB2 aggregation rule.",
        )

    async def assess(self, record: ExtractionRecord, full_text: str = "") -> RoB2Assessment:
        if self.llm_client is not None and self.settings is not None:
            try:
                agent = self.settings.agents.get("quality_assessment")
                model = agent.model if agent else "google-gla:gemini-2.5-pro"
                temperature = agent.temperature if agent else 0.2
                prompt = _build_rob2_prompt(record, full_text)
                schema = _Rob2LLMResponse.model_json_schema()
                t0 = time.monotonic()
                if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
                    raw, tok_in, tok_out, cw, cr = await self.llm_client.complete_with_usage(
                        prompt, model=model, temperature=temperature, json_schema=schema
                    )
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
                    await self.provider.log_cost(model, tok_in, tok_out, cost, latency_ms, phase="quality_rob2", cache_read_tokens=cr, cache_write_tokens=cw)
                else:
                    raw = await self.llm_client.complete(
                        prompt, model=model, temperature=temperature, json_schema=schema
                    )
                parsed = _Rob2LLMResponse.model_validate_json(raw)
                return RoB2Assessment(
                    paper_id=record.paper_id,
                    domain_1_randomization=_to_rob2_judgment(parsed.domain_1_randomization),
                    domain_1_rationale=parsed.domain_1_rationale or "LLM assessment.",
                    domain_2_deviations=_to_rob2_judgment(parsed.domain_2_deviations),
                    domain_2_rationale=parsed.domain_2_rationale or "LLM assessment.",
                    domain_3_missing_data=_to_rob2_judgment(parsed.domain_3_missing_data),
                    domain_3_rationale=parsed.domain_3_rationale or "LLM assessment.",
                    domain_4_measurement=_to_rob2_judgment(parsed.domain_4_measurement),
                    domain_4_rationale=parsed.domain_4_rationale or "LLM assessment.",
                    domain_5_selection=_to_rob2_judgment(parsed.domain_5_selection),
                    domain_5_rationale=parsed.domain_5_rationale or "LLM assessment.",
                    overall_judgment=_to_rob2_judgment(parsed.overall_judgment),
                    overall_rationale=parsed.overall_rationale or "LLM overall judgment.",
                )
            except Exception as exc:
                logger.warning(
                    "RoB 2 LLM assessment failed for %s (%s); using heuristic.",
                    record.paper_id[:12],
                    type(exc).__name__,
                )
        return self._heuristic(record)
