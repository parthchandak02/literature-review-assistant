"""Structured extraction service with LLM-based extraction and heuristic fallback."""

from __future__ import annotations

import logging
import time
from typing import List

from pydantic import BaseModel, Field

from src.db.repositories import WorkflowRepository
from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import CandidatePaper, ExtractionRecord, StudyDesign
from src.models.config import ReviewConfig, SettingsConfig

logger = logging.getLogger(__name__)


class _OutcomeItem(BaseModel):
    name: str = "primary_outcome"
    description: str = ""
    effect_size: str = ""
    se: str = ""
    n: str = ""


class _ExtractionLLMResponse(BaseModel):
    study_duration: str = ""
    setting: str = ""
    participant_count: str = ""
    participant_demographics: str = ""
    intervention_description: str = ""
    comparator_description: str = ""
    outcomes: List[_OutcomeItem] = Field(default_factory=list)
    results_summary: str = ""
    funding_source: str = ""
    conflicts_of_interest: str = ""


def _build_extraction_prompt(
    paper: CandidatePaper,
    text: str,
    review: ReviewConfig,
) -> str:
    return "\n".join([
        "You are a systematic review data extractor.",
        f"Research question: {review.research_question}",
        f"Intervention of interest: {review.pico.intervention}",
        f"Population of interest: {review.pico.population}",
        f"Outcome of interest: {review.pico.outcome}",
        "",
        f"Title: {paper.title}",
        "",
        "Text excerpt (up to 8000 chars):",
        text[:8000],
        "",
        "Extract the following from this study:",
        "- study_duration: Duration of the study or intervention (e.g. '8 weeks', '1 semester', 'unknown')",
        "- setting: Study setting (e.g. 'university classroom', 'online platform', 'hospital ward')",
        "- participant_count: Total number of participants as a string (e.g. '120', 'not reported')",
        "- participant_demographics: Brief description of participants (age, background, etc.)",
        "- intervention_description: What the intervention/treatment was in detail",
        "- comparator_description: What the control/comparison condition was (or 'no control' if absent)",
        "- outcomes: List of outcome measures. For each outcome include:",
        "    name (short identifier), description, effect_size (e.g. 'SMD=0.45', 'OR=2.1', or empty),",
        "    se (standard error as decimal string, e.g. '0.12', or empty), n (sample size string or empty)",
        "- results_summary: Plain text summary of the key findings (2-4 sentences)",
        "- funding_source: Who funded the study (or 'not reported')",
        "- conflicts_of_interest: Any declared COI (or 'none declared')",
        "",
        "Return ONLY valid JSON matching the schema.",
    ])


class ExtractionService:
    """Create typed extraction records from paper metadata/full text.

    Uses Gemini Pro LLM when available; falls back to heuristic extraction
    on API errors or when offline.
    """

    def __init__(
        self,
        repository: WorkflowRepository,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        review: ReviewConfig | None = None,
        provider: object | None = None,
    ):
        self.repository = repository
        self.llm_client = llm_client
        self.settings = settings
        self.review = review
        self.provider = provider

    @staticmethod
    def _heuristic_summary(paper: CandidatePaper, full_text: str) -> str:
        text = full_text.strip()
        if text:
            return text[:1200]
        abstract = (paper.abstract or "").strip()
        if abstract:
            return abstract[:1200]
        return "No summary available."

    @staticmethod
    def _heuristic_outcomes() -> list[dict[str, str]]:
        return [
            {
                "name": "primary_outcome",
                "description": "Learning performance or retention signal extracted from source context.",
            }
        ]

    def _heuristic_extract(
        self,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        text = full_text[:10000]
        summary = self._heuristic_summary(paper, text)
        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            study_duration="unknown",
            setting="not_reported",
            participant_count=None,
            participant_demographics=None,
            intervention_description=paper.title[:500],
            comparator_description=None,
            outcomes=self._heuristic_outcomes(),
            results_summary={
                "summary": summary,
                "source": "heuristic",
            },
            funding_source=None,
            conflicts_of_interest=None,
            source_spans={
                "full_text_excerpt": text[:500] if text.strip() else "",
                "title": paper.title[:500],
            },
        )

    async def _llm_extract(
        self,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        assert self.llm_client is not None
        assert self.review is not None
        assert self.settings is not None

        agent = self.settings.agents.get("extraction")
        model = agent.model if agent else "google-gla:gemini-2.5-pro"
        temperature = agent.temperature if agent else 0.1

        text = full_text[:10000]
        prompt = _build_extraction_prompt(paper, text, self.review)
        schema = _ExtractionLLMResponse.model_json_schema()

        t0 = time.monotonic()
        if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
            raw, tok_in, tok_out, cw, cr = await self.llm_client.complete_with_usage(
                prompt, model=model, temperature=temperature, json_schema=schema
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
            await self.provider.log_cost(model, tok_in, tok_out, cost, latency_ms, phase="extraction", cache_read_tokens=cr, cache_write_tokens=cw)
        else:
            raw = await self.llm_client.complete(
                prompt, model=model, temperature=temperature, json_schema=schema
            )
        parsed = _ExtractionLLMResponse.model_validate_json(raw)

        outcomes: list[dict[str, str]] = []
        for o in (parsed.outcomes or []):
            entry: dict[str, str] = {
                "name": o.name or "primary_outcome",
                "description": o.description or "",
            }
            if o.effect_size:
                entry["effect_size"] = o.effect_size
            if o.se:
                entry["se"] = o.se
            if o.n:
                entry["n"] = o.n
            outcomes.append(entry)
        if not outcomes:
            outcomes = self._heuristic_outcomes()

        try:
            participant_count: int | None = int(parsed.participant_count) if parsed.participant_count.strip().isdigit() else None
        except (ValueError, AttributeError):
            participant_count = None

        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            study_duration=parsed.study_duration or "unknown",
            setting=parsed.setting or "not_reported",
            participant_count=participant_count,
            participant_demographics=parsed.participant_demographics or None,
            intervention_description=parsed.intervention_description or paper.title[:500],
            comparator_description=parsed.comparator_description or None,
            outcomes=outcomes,
            results_summary={
                "summary": parsed.results_summary or self._heuristic_summary(paper, text),
                "source": "llm",
            },
            funding_source=parsed.funding_source or None,
            conflicts_of_interest=parsed.conflicts_of_interest or None,
            source_spans={
                "full_text_excerpt": text[:500] if text.strip() else "",
                "title": paper.title[:500],
            },
        )

    async def extract(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        record: ExtractionRecord
        if self.llm_client is not None and self.review is not None and self.settings is not None:
            try:
                record = await self._llm_extract(paper, study_design, full_text)
            except Exception as exc:
                logger.warning(
                    "LLM extraction failed for %s (%s); using heuristic fallback.",
                    paper.paper_id[:12],
                    type(exc).__name__,
                )
                record = self._heuristic_extract(paper, study_design, full_text)
        else:
            record = self._heuristic_extract(paper, study_design, full_text)
        await self.repository.save_extraction_record(workflow_id=workflow_id, record=record)
        return record
