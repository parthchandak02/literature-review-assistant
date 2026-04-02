"""Phase-7 manuscript audit orchestration."""

from __future__ import annotations

import json
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import (
    ManuscriptAuditFinding,
    ManuscriptAuditProfileSelection,
    ManuscriptAuditResult,
    ReviewConfig,
    SettingsConfig,
)


class _ReviewerFinding(BaseModel):
    severity: Literal["major", "minor", "note"]
    category: str
    section: str | None = None
    evidence: str
    recommendation: str
    owner_module: str = "writing"
    blocking: bool = False


class _ReviewerResponse(BaseModel):
    verdict: Literal["accept", "minor_revisions", "major_revisions", "reject"]
    summary: str
    findings: list[_ReviewerFinding] = Field(default_factory=list)


def select_audit_profiles(review: ReviewConfig, settings: SettingsConfig) -> ManuscriptAuditProfileSelection:
    """Route to bounded profile set based on review metadata and settings."""
    cfg = settings.manuscript_audit
    max_profiles = max(1, int(cfg.max_profiles_per_run))
    mode = str(cfg.profile_activation or "domain_matched")

    if mode == "manual":
        selected = [str(p) for p in (cfg.required_profiles or ["general_systematic_review"])]
        selected = selected[:max_profiles]
        return ManuscriptAuditProfileSelection(
            selected_profiles=selected,  # type: ignore[arg-type]
            routing_reason="manual profile list from settings.manuscript_audit.required_profiles",
        )
    if mode == "always":
        selected = ["general_systematic_review"]
        return ManuscriptAuditProfileSelection(
            selected_profiles=selected, routing_reason="always mode uses only general profile"
        )

    selected: list[str] = ["general_systematic_review"]
    domain = (review.domain or "").lower()
    text = " ".join([review.research_question, domain, " ".join(review.keywords)]).lower()
    if any(x in text for x in ("cost", "payer", "economic", "insurance", "icer", "out-of-pocket")):
        selected.append("health_economics")
    if any(x in text for x in ("education", "student", "learning", "curriculum", "teaching")):
        selected.append("education")
    if any(x in text for x in ("implementation", "adoption", "feasibility", "barrier", "facilitator")):
        selected.append("implementation_science")
    if any(x in text for x in ("qualitative", "interview", "focus group", "thematic")):
        selected.append("qualitative_methods")
    deduped: list[str] = []
    for p in selected:
        if p not in deduped:
            deduped.append(p)
    deduped = deduped[:max_profiles]
    return ManuscriptAuditProfileSelection(
        selected_profiles=deduped,  # type: ignore[arg-type]
        routing_reason="domain_matched routing from review question/domain/keywords",
    )


def _profile_instructions(profile: str) -> str:
    if profile == "health_economics":
        return "Focus on economic framing, payer perspective, cost reporting clarity, and policy relevance."
    if profile == "education":
        return "Focus on educational outcomes, learner context, intervention fidelity, and pedagogical interpretation."
    if profile == "implementation_science":
        return "Focus on implementation barriers, facilitators, setting transferability, and execution realism."
    if profile == "qualitative_methods":
        return "Focus on qualitative rigor, sampling transparency, reflexivity, and analytic traceability."
    return "Focus on general systematic review quality, methods-to-results coherence, and manuscript clarity."


async def run_manuscript_audit(
    *,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    manuscript_text: str,
    contract_summary_json: str,
    provider: LLMProvider,
) -> tuple[ManuscriptAuditResult, list[ManuscriptAuditFinding]]:
    """Run bounded profile-based manuscript audit with explicit cost cap."""
    selection = select_audit_profiles(review, settings)
    selected = list(selection.selected_profiles)
    agent_name = "writing"
    client = PydanticAIClient(timeout_seconds=float(settings.llm.request_timeout_seconds))
    findings: list[ManuscriptAuditFinding] = []
    total_cost = 0.0
    verdict_rank = {"accept": 0, "minor_revisions": 1, "major_revisions": 2, "reject": 3}
    merged_verdict = "accept"
    summaries: list[str] = []

    for profile in selected:
        if total_cost >= float(settings.manuscript_audit.cost_cap_usd):
            break
        runtime = await provider.reserve_call_slot(agent_name)
        prompt = (
            "You are a manuscript peer reviewer.\n"
            f"Profile: {profile}\n"
            f"Instructions: {_profile_instructions(profile)}\n"
            "Return strict JSON only.\n"
            "Use these severity levels: major, minor, note.\n"
            "Set blocking=true only for critical defects that should block strict gate.\n\n"
            f"Deterministic contract summary JSON:\n{contract_summary_json}\n\n"
            "Manuscript:\n"
            f"{manuscript_text[:32000]}"
        )
        schema = _ReviewerResponse.model_json_schema()
        t0 = time.monotonic()
        raw, tok_in, tok_out, cw, cr = await client.complete_with_usage(
            prompt,
            model=runtime.model,
            temperature=runtime.temperature,
            json_schema=schema,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        cost = provider.estimate_cost_usd(runtime.model, tok_in, tok_out, cw, cr)
        total_cost += cost
        await provider.log_cost(
            runtime.model,
            tok_in,
            tok_out,
            cost,
            latency_ms,
            phase="phase_7_audit",
            workflow_id=workflow_id,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
        )
        parsed = _ReviewerResponse.model_validate_json(raw)
        if verdict_rank[parsed.verdict] > verdict_rank[merged_verdict]:
            merged_verdict = parsed.verdict
        if parsed.summary:
            summaries.append(f"{profile}: {parsed.summary}")
        for idx, f in enumerate(parsed.findings):
            findings.append(
                ManuscriptAuditFinding(
                    finding_id=f"{profile}-{idx+1}",
                    profile=profile,  # type: ignore[arg-type]
                    severity=f.severity,
                    category=f.category,
                    section=f.section,
                    evidence=f.evidence,
                    recommendation=f.recommendation,
                    owner_module=f.owner_module or "writing",
                    blocking=bool(f.blocking),
                )
            )

    major_count = len([f for f in findings if f.severity == "major"])
    minor_count = len([f for f in findings if f.severity == "minor"])
    note_count = len([f for f in findings if f.severity == "note"])
    blocking_count = len([f for f in findings if f.blocking])
    mode = str(getattr(settings.gates, "manuscript_audit_mode", "observe"))
    passed = True
    if mode == "soft":
        passed = merged_verdict != "reject"
    elif mode == "strict":
        passed = blocking_count == 0 and merged_verdict in ("accept", "minor_revisions")

    result = ManuscriptAuditResult(
        audit_run_id=f"audit-{uuid.uuid4().hex[:12]}",
        workflow_id=workflow_id,
        mode=mode,
        verdict=merged_verdict,  # type: ignore[arg-type]
        passed=passed,
        selected_profiles=selected,  # type: ignore[arg-type]
        summary=" | ".join(summaries)[:2000],
        total_findings=len(findings),
        major_count=major_count,
        minor_count=minor_count,
        note_count=note_count,
        blocking_count=blocking_count,
        total_cost_usd=round(total_cost, 6),
    )
    return result, findings


def serialize_contract_summary(summary: dict[str, object]) -> str:
    """Stable JSON serialization for prompt grounding."""
    try:
        return json.dumps(summary, ensure_ascii=True)
    except Exception:
        return "{}"

