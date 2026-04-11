"""Agentic study design classifier for extraction routing."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from src.db.repositories import WorkflowRepository
from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import CandidatePaper, DecisionLogEntry, ReviewConfig, StudyDesign


class StudyClassificationResult(BaseModel):
    study_design: StudyDesign
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class StudyClassificationLLMClient(Protocol):
    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return a JSON string matching StudyClassificationResult."""


class PydanticAIStudyClassificationClient:
    """Study classification client backed by PydanticAI Agent.

    Satisfies StudyClassificationLLMClient Protocol. Supports all PydanticAI
    providers -- switch the model string in settings.yaml to change provider.
    """

    async def complete_json(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> str:
        _ = agent_name
        schema = StudyClassificationResult.model_json_schema()
        client = PydanticAIClient()
        return await client.complete(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=schema,
        )

    async def complete_json_with_usage(
        self,
        prompt: str,
        *,
        agent_name: str,
        model: str,
        temperature: float,
    ) -> tuple[str, int, int, int, int]:
        """Return (json_str, input_tokens, output_tokens, cache_write, cache_read)."""
        _ = agent_name
        schema = StudyClassificationResult.model_json_schema()
        client = PydanticAIClient()
        return await client.complete_with_usage(
            prompt,
            model=model,
            temperature=temperature,
            json_schema=schema,
        )


# Backward-compatibility alias.
GeminiStudyClassificationClient = PydanticAIStudyClassificationClient


class StudyClassifier:
    """Classify study design via a Pro-tier agent with typed fallback."""

    def __init__(
        self,
        provider: LLMProvider,
        repository: WorkflowRepository,
        review: ReviewConfig,
        llm_client: StudyClassificationLLMClient | None = None,
        low_confidence_threshold: float = 0.70,
        on_llm_call: Callable[..., None] | None = None,
    ):
        self.provider = provider
        self.repository = repository
        self.review = review
        self.llm_client = llm_client or PydanticAIStudyClassificationClient()
        self.low_confidence_threshold = low_confidence_threshold
        self.on_llm_call = on_llm_call
        # Use quality_assessment profile for single Pro-tier behavior.
        self.agent_name = "quality_assessment"

    def _build_prompt(self, paper: CandidatePaper, *, abstract_only: bool = False) -> str:
        lines = [
            "Role: Study Design Classification Specialist",
            "Goal: Classify study design for downstream quality-assessment routing.",
            "Backstory: You support systematic reviews across changing domains and topics.",
            f"Topic: {self.review.expert_topic()}",
            f"Research Question: {self.review.research_question}",
            f"Domain: {self.review.domain}",
            f"Keywords: {', '.join(self.review.keywords)}",
            f"Topic anchor terms: {', '.join(self.review.domain_signal_terms(limit=12))}",
            f"Preferred terminology: {', '.join(self.review.preferred_terminology())}",
            "Domain brief:",
            *[f"  - {item}" for item in self.review.domain_brief_lines()],
            "",
            f"Paper ID: {paper.paper_id}",
            f"Title: {paper.title}",
            f"Abstract: {paper.abstract or ''}",
            "",
            "Classify the study design. Choose the most appropriate value:",
            "  rct                - Randomized controlled trial with random allocation to groups.",
            "  non_randomized     - Non-randomized CONTROLLED study with a defined intervention",
            "    AND a comparator/control group. ROBINS-I applies.",
            "    Covers any domain: clinical trials without randomization, simulation/computational",
            "    studies comparing multiple conditions with controlled variables, laboratory bench",
            "    tests with controlled parameters, A/B comparisons in software or policy, etc.",
            "    Do NOT use for single-group pre-post studies without a control arm.",
            "  quasi_experimental - Controlled study with non-equivalent groups (convenience assignment)",
            "    or interrupted time series. Has a comparator but groups are not randomly assigned.",
            "    Covers any domain: classroom vs classroom, before/after policy changes with a",
            "    control region, baseline vs modified configuration comparisons, historical controls.",
            "  cohort             - Cohort study (prospective or retrospective) following a group over time.",
            "  case_control       - Case-control study comparing cases with matched controls.",
            "  pre_post           - Single-group before/after (pre-post) study with NO control arm.",
            "    Use when: a single group or system is measured at baseline and after an intervention,",
            "    but there is no comparison group. Applies in any domain: clinical, educational,",
            "    engineering, policy, etc. Appraisable with MMAT (quantitative descriptive).",
            "  qualitative        - Qualitative study: interviews, focus groups, thematic analysis.",
            "  mixed_methods      - Mixed quantitative + qualitative methods in a single study.",
            "  cross_sectional    - Cross-sectional survey, audit, or single time-point observation.",
            "    Use when: data collected at one time point with no before/after measurement.",
            "  usability_study    - UX/acceptability evaluation only (System Usability Scale, TAM,",
            "    think-aloud, heuristic evaluation). Primary outcome is usability/acceptability.",
            "    No pre-post measurement of domain-specific outcomes.",
            "  development_study  - PURE system design, architecture, or proof-of-concept paper with",
            "    NO quantitative evaluation or empirical results whatsoever.",
            "    Use ONLY when: the paper describes a system, framework, method, or model but reports",
            "    NO performance metrics, NO simulation/experimental data, NO quantitative comparisons,",
            "    and NO measured outcomes of any kind. If the abstract mentions ANY quantitative results",
            "    -- regardless of domain -- classify as an empirical category instead.",
            "    Not appraisable with standard RoB tools.",
            "  protocol           - Registered trial protocol or study design paper (no results yet).",
            "  conference_abstract - Conference poster or abstract only (not a full peer-reviewed paper).",
            "    Use this when: the DOI contains 'conf', 'conference', 'abstract', 'supplement', 'poster',",
            "    or similar conference identifiers; or the title/abstract indicates poster/abstract only.",
            "  narrative_review   - Narrative, scoping, or umbrella review (not a primary evidence study).",
            "    Use this when: the title or abstract explicitly says 'systematic review', 'scoping review',",
            "    'narrative review', 'meta-analysis', 'review of literature', 'overview', etc.",
            "  other              - Study type genuinely not covered by any category above.",
            "",
            "DISAMBIGUATION RULE (applies to ALL domains): If the abstract mentions quantitative",
            "results, measured outcomes, performance metrics, experimental evaluation, simulation data,",
            "statistical analysis, or any kind of empirical comparison, the paper is a primary",
            "empirical study -- classify as non_randomized, quasi_experimental, pre_post, or another",
            "empirical category. Do NOT classify it as development_study. Papers that both propose",
            "a new system/method AND evaluate it quantitatively are empirical studies, not",
            "development studies. This rule applies regardless of domain (clinical, engineering,",
            "education, social science, computer science, etc.).",
        ]
        if abstract_only:
            lines.extend([
                "",
                "ABSTRACT-ONLY CLASSIFICATION: You are classifying from title and abstract ONLY",
                "(full text was not available). When uncertain between development_study and an",
                "empirical category (non_randomized, quasi_experimental, pre_post), PREFER the",
                "empirical category. Across all domains, papers routinely describe their method",
                "or system in the abstract while the full quantitative evaluation appears only",
                "in the body. Reserve development_study ONLY for papers whose abstract explicitly",
                "states that NO evaluation, testing, or results are presented.",
            ])
        lines.extend([
            "",
            "Return ONLY valid JSON matching this exact schema:",
            '{"study_design":"rct|non_randomized|quasi_experimental|cohort|case_control|pre_post|qualitative|mixed_methods|cross_sectional|usability_study|development_study|protocol|conference_abstract|narrative_review|other","confidence":0.0,"reasoning":"..."}',
        ])
        return "\n".join(lines)

    @staticmethod
    def _parse_response(raw: str) -> StudyClassificationResult | None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            return StudyClassificationResult.model_validate(payload)
        except ValidationError:
            return None

    # DOI fragments that reliably indicate a conference abstract (not a full paper).
    # Keep entries generic -- do not add society- or journal-specific prefixes here.
    _CONFERENCE_DOI_SIGNALS = (
        "-conf.",
        "conference",
        ".meeting.",
        "abstract",
        "supplement",
        "suppl.",
        "poster",
        "bmjpo-",
    )
    # Title phrases that indicate a narrative/scoping review
    _REVIEW_TITLE_SIGNALS = (
        "systematic review",
        "scoping review",
        "narrative review",
        "meta-analysis",
        "literature review",
        "umbrella review",
        "overview of",
    )

    async def classify(self, workflow_id: str, paper: CandidatePaper, *, abstract_only: bool = False) -> StudyDesign:
        # Heuristic pre-classification: DOI-based conference abstract detection
        doi_lower = (paper.doi or "").lower()
        if any(signal in doi_lower for signal in self._CONFERENCE_DOI_SIGNALS):
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="study_classification",
                    paper_id=paper.paper_id,
                    decision=StudyDesign.CONFERENCE_ABSTRACT.value,
                    rationale=(
                        f"DOI pattern '{doi_lower[:80]}' matches conference abstract signals. "
                        "Classified as conference_abstract without LLM call."
                    ),
                    actor="study_classifier_heuristic",
                    phase="phase_4_extraction_quality",
                )
            )
            return StudyDesign.CONFERENCE_ABSTRACT

        # Title-based narrative review detection
        title_lower = (paper.title or "").lower()
        if any(signal in title_lower for signal in self._REVIEW_TITLE_SIGNALS):
            await self.repository.append_decision_log(
                DecisionLogEntry(
                    decision_type="study_classification",
                    paper_id=paper.paper_id,
                    decision=StudyDesign.NARRATIVE_REVIEW.value,
                    rationale=(
                        f"Title '{paper.title[:80]}' matches narrative/scoping review signals. "
                        "Classified as narrative_review without LLM call."
                    ),
                    actor="study_classifier_heuristic",
                    phase="phase_4_extraction_quality",
                )
            )
            return StudyDesign.NARRATIVE_REVIEW

        prompt = self._build_prompt(paper, abstract_only=abstract_only)
        runtime = await self.provider.reserve_call_slot(self.agent_name)
        started = time.perf_counter()
        if hasattr(self.llm_client, "complete_json_with_usage"):
            raw, tokens_in, tokens_out, cache_write, cache_read = await self.llm_client.complete_json_with_usage(
                prompt,
                agent_name=self.agent_name,
                model=runtime.model,
                temperature=runtime.temperature,
            )
        else:
            raw = await self.llm_client.complete_json(
                prompt,
                agent_name=self.agent_name,
                model=runtime.model,
                temperature=runtime.temperature,
            )
            tokens_in = max(1, len(prompt.split()))
            tokens_out = max(1, len(raw.split()))
            cache_write = cache_read = 0
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self.provider.estimate_cost(runtime.model, tokens_in, tokens_out, cache_write, cache_read)
        parsed = self._parse_response(raw)
        await self.provider.log_cost(
            model=runtime.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=elapsed_ms,
            phase="phase_4_extraction_quality",
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        if self.on_llm_call:
            details = (
                f"{paper.paper_id[:12]} {parsed.study_design.value}" if parsed else f"{paper.paper_id[:12]} parse_error"
            )
            self.on_llm_call(
                source="study_type_detection",
                status="success",
                details=details,
                records=None,
                call_type="llm_classification",
                raw_response=raw,
                latency_ms=elapsed_ms,
                model=runtime.model,
                paper_id=paper.paper_id,
                phase="phase_4_extraction_quality",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
            )
        if parsed is None:
            final_design = StudyDesign.NON_RANDOMIZED
            rationale = "Malformed classifier output. Applied non_randomized fallback."
            confidence = 0.0
            predicted = "parse_error"
        elif parsed.confidence < self.low_confidence_threshold:
            final_design = StudyDesign.NON_RANDOMIZED
            rationale = (
                f"Low confidence ({parsed.confidence:.2f} < {self.low_confidence_threshold:.2f}). "
                "Applied non_randomized fallback."
            )
            confidence = parsed.confidence
            predicted = parsed.study_design.value
        elif (
            abstract_only
            and parsed.study_design == StudyDesign.DEVELOPMENT_STUDY
            and parsed.confidence < 0.85
        ):
            final_design = StudyDesign.NON_RANDOMIZED
            rationale = (
                f"Abstract-only classification returned development_study with "
                f"confidence={parsed.confidence:.2f} < 0.85. Upgrading to non_randomized "
                f"because abstract-only context is insufficient to confirm absence of "
                f"empirical evaluation."
            )
            confidence = parsed.confidence
            predicted = parsed.study_design.value
        else:
            final_design = parsed.study_design
            rationale = parsed.reasoning
            confidence = parsed.confidence
            predicted = parsed.study_design.value

        await self.repository.append_decision_log(
            DecisionLogEntry(
                decision_type="study_design_classification",
                paper_id=paper.paper_id,
                decision=final_design.value,
                rationale=(
                    f"predicted={predicted}; confidence={confidence:.2f}; "
                    f"threshold={self.low_confidence_threshold:.2f}; rationale={rationale}"
                ),
                actor="study_classifier_agent",
                phase="phase_4_extraction_quality",
            )
        )
        return final_design
