"""Phase-7 manuscript audit orchestration."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import (
    AuditProfileName,
    ManuscriptAuditFinding,
    ManuscriptAuditProfileSelection,
    ManuscriptAuditResult,
    ReviewConfig,
    SettingsConfig,
)

logger = logging.getLogger(__name__)


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


_GENERAL_PROFILE: AuditProfileName = "general_systematic_review"
_PROFILE_ORDER: list[AuditProfileName] = [
    "general_systematic_review",
    "implementation_science",
    "qualitative_methods",
    "health_economics",
    "education",
]
_PROFILE_LABELS: dict[AuditProfileName, str] = {
    "general_systematic_review": "General evidence-synthesis review",
    "health_economics": "Health economics and policy relevance",
    "education": "Education and learner-outcome interpretation",
    "implementation_science": "Implementation and real-world adoption",
    "qualitative_methods": "Qualitative methods rigor",
}
_CORE_SECTION_PRIORITY = (
    "abstract",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "introduction",
    "limitations",
)


@dataclass(frozen=True)
class _AuditPassSpec:
    label: str
    scope_note: str
    manuscript_excerpt: str


def select_audit_profiles(review: ReviewConfig, settings: SettingsConfig) -> ManuscriptAuditProfileSelection:
    """Deterministic fallback router based on structured review metadata."""
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

    text_parts = [
        review.research_question,
        review.expert_topic(),
        review.domain,
        review.scope,
        review.pico.population,
        review.pico.intervention,
        review.pico.outcome,
        " ".join(review.keywords),
        " ".join(review.target_databases),
        " ".join(review.inclusion_criteria[:5]),
        " ".join(review.exclusion_criteria[:5]),
        " ".join(review.domain_signal_terms(limit=20)),
        " ".join(review.methodology_expectations(limit=10)),
    ]
    text = " ".join(part for part in text_parts if part).lower()
    selected: list[AuditProfileName] = [_GENERAL_PROFILE]
    if any(x in text for x in ("cost", "cost-effect", "economic", "payer", "insurance", "icer", "budget impact")):
        selected.append("health_economics")
    if any(x in text for x in ("education", "student", "learner", "curriculum", "teaching", "school")):
        selected.append("education")
    if any(x in text for x in ("implementation", "adoption", "feasibility", "barrier", "facilitator", "uptake")):
        selected.append("implementation_science")
    if any(x in text for x in ("qualitative", "interview", "focus group", "thematic", "ethnograph", "reflexiv")):
        selected.append("qualitative_methods")
    deduped = _normalize_selected_profiles(selected, max_profiles=max_profiles)
    return ManuscriptAuditProfileSelection(
        selected_profiles=deduped,
        routing_reason=(
            "deterministic fallback routing from structured review metadata, PICO, "
            "domain brief, and methodology expectations"
        ),
    )


def _audit_domain_brief(review: ReviewConfig) -> str:
    lines = review.domain_brief_lines()
    if not lines:
        return ""
    return "Domain brief:\n" + "\n".join(f"- {item}" for item in lines)


def _profile_instructions(profile: str) -> str:
    if profile == "health_economics":
        return "Focus on economic framing, payer perspective, cost reporting clarity, and policy relevance."
    if profile == "education":
        return "Focus on educational outcomes, learner context, intervention fidelity, and pedagogical interpretation."
    if profile == "implementation_science":
        return "Focus on implementation barriers, facilitators, setting transferability, and execution realism."
    if profile == "qualitative_methods":
        return "Focus on qualitative rigor, sampling transparency, reflexivity, and analytic traceability."
    return (
        "Focus on evidence-synthesis quality, reporting transparency, methods-to-results coherence, "
        "and claim calibration."
    )


def _normalize_selected_profiles(
    profiles: list[str | AuditProfileName],
    *,
    max_profiles: int,
) -> list[AuditProfileName]:
    allowed = set(_PROFILE_ORDER)
    deduped: list[AuditProfileName] = []
    if _GENERAL_PROFILE not in profiles:
        profiles = [_GENERAL_PROFILE, *profiles]
    for raw in profiles:
        profile = str(raw or "").strip()
        if not profile or profile not in allowed:
            continue
        typed_profile = profile  # type: ignore[assignment]
        if typed_profile not in deduped:
            deduped.append(typed_profile)
    if not deduped:
        deduped = [_GENERAL_PROFILE]
    return deduped[: max(1, max_profiles)]


def _profile_catalog_text() -> str:
    return "\n".join(f"- {name}: {_PROFILE_LABELS[name]}; {_profile_instructions(name)}" for name in _PROFILE_ORDER)


def _markdown_sections(manuscript_text: str) -> list[tuple[str, str]]:
    lines = manuscript_text.splitlines()
    heading_rows: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("## "):
            continue
        heading = stripped[3:].strip()
        if heading:
            heading_rows.append((idx, heading))
    if not heading_rows:
        return [("full_manuscript", manuscript_text)]
    sections: list[tuple[str, str]] = []
    if heading_rows[0][0] > 0:
        front_matter = "\n".join(lines[: heading_rows[0][0]]).strip()
        if front_matter:
            sections.append(("front_matter", front_matter))
    for idx, (start_row, heading) in enumerate(heading_rows):
        end_row = heading_rows[idx + 1][0] if idx + 1 < len(heading_rows) else len(lines)
        body = "\n".join(lines[start_row:end_row]).strip()
        sections.append((heading, body))
    return sections


def _collapse_non_alnum(value: str, *, separator: str) -> str:
    out_chars: list[str] = []
    prev_sep = False
    for ch in value.lower():
        is_alnum = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if is_alnum:
            out_chars.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out_chars.append(separator)
            prev_sep = True
    return "".join(out_chars).strip(separator)


def _heading_key(heading: str) -> str:
    return _collapse_non_alnum(str(heading or ""), separator=" ")


def _build_manuscript_excerpt(manuscript_text: str, *, char_budget: int = 32000) -> str:
    if len(manuscript_text) <= char_budget:
        return manuscript_text
    sections = _markdown_sections(manuscript_text)
    if not sections:
        return manuscript_text[:char_budget]
    section_map = {heading: body for heading, body in sections}
    ordered_headings: list[str] = []
    for target in _CORE_SECTION_PRIORITY:
        for heading, _body in sections:
            if heading in ordered_headings:
                continue
            if target in _heading_key(heading):
                ordered_headings.append(heading)
    for heading, _body in sections:
        if heading not in ordered_headings:
            ordered_headings.append(heading)

    parts: list[str] = []
    remaining = char_budget
    for idx, heading in enumerate(ordered_headings):
        body = section_map.get(heading, "").strip()
        if not body or remaining <= 200:
            continue
        remaining_sections = max(1, len(ordered_headings) - idx)
        section_budget = min(4500, max(300, remaining // remaining_sections))
        piece = body[: min(section_budget, remaining)]
        if len(piece) < len(body):
            piece = piece.rstrip() + "\n[section truncated]"
        if len(piece) > remaining:
            piece = piece[:remaining]
        parts.append(piece)
        remaining -= len(piece) + 2
    excerpt = "\n\n".join(parts).strip()
    if not excerpt:
        return manuscript_text[:char_budget]
    return excerpt[:char_budget]


def _build_section_focus_excerpt(
    manuscript_text: str,
    *,
    section_targets: tuple[str, ...],
    char_budget: int,
) -> str:
    sections = _markdown_sections(manuscript_text)
    if not sections:
        return manuscript_text[:char_budget]
    ordered_bodies: list[str] = []
    used: set[str] = set()
    for target in section_targets:
        for heading, body in sections:
            normalized = _heading_key(heading)
            if target not in normalized or heading in used or not body.strip():
                continue
            ordered_bodies.append(body.strip())
            used.add(heading)
            break
    if not ordered_bodies:
        return ""
    remaining = char_budget
    parts: list[str] = []
    for idx, body in enumerate(ordered_bodies):
        remaining_sections = max(1, len(ordered_bodies) - idx)
        section_budget = min(6000, max(800, remaining // remaining_sections))
        piece = body[: min(section_budget, remaining)]
        if len(piece) < len(body):
            piece = piece.rstrip() + "\n[section truncated]"
        if len(piece) > remaining:
            piece = piece[:remaining]
        parts.append(piece)
        remaining -= len(piece) + 2
        if remaining <= 200:
            break
    return "\n\n".join(parts).strip()[:char_budget]


def _build_audit_pass_plan(manuscript_text: str, *, char_budget: int = 32000) -> list[_AuditPassSpec]:
    overview_excerpt = _build_manuscript_excerpt(manuscript_text, char_budget=char_budget)
    plan = [
        _AuditPassSpec(
            label="balanced_overview",
            scope_note="Review the manuscript globally across all available sections before making a verdict.",
            manuscript_excerpt=overview_excerpt,
        )
    ]
    sections = _markdown_sections(manuscript_text)
    needs_escalation = len(manuscript_text) > char_budget or len(sections) > 8
    if needs_escalation:
        critical_excerpt = _build_section_focus_excerpt(
            manuscript_text,
            section_targets=("methods", "results", "discussion", "conclusion"),
            char_budget=min(char_budget, 22000),
        )
        if critical_excerpt and critical_excerpt != overview_excerpt:
            plan.append(
                _AuditPassSpec(
                    label="critical_sections",
                    scope_note=(
                        "Focus especially on Methods, Results, Discussion, and Conclusion. "
                        "Look for cross-section contradictions, unsupported certainty claims, "
                        "and omissions that can be hidden in long manuscripts."
                    ),
                    manuscript_excerpt=critical_excerpt,
                )
            )
    return plan


def _finding_scope_token(scope: str) -> str:
    return _collapse_non_alnum(scope, separator="_") or "scope"


def _dedupe_findings(findings: list[ManuscriptAuditFinding]) -> list[ManuscriptAuditFinding]:
    deduped: list[ManuscriptAuditFinding] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for finding in findings:
        key = (
            str(finding.profile).lower(),
            str(finding.category).strip().lower(),
            str(finding.section or "").strip().lower(),
            str(finding.recommendation).strip().lower(),
            str(finding.evidence).strip().lower()[:180],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _routing_prompt(
    review: ReviewConfig,
    fallback: ManuscriptAuditProfileSelection,
    *,
    max_profiles: int,
) -> str:
    return (
        "You are routing a manuscript audit to the most relevant bounded profile set.\n"
        "Return strict JSON only.\n"
        f"Maximum profiles allowed: {max_profiles}.\n"
        "Always include general_systematic_review.\n"
        "Select domain-specific profiles only when the structured review metadata clearly supports them.\n"
        "Prefer under-selection to over-selection.\n\n"
        "Available profiles:\n"
        f"{_profile_catalog_text()}\n\n"
        f"Review type: {review.review_type.value}\n"
        f"Research question: {review.research_question}\n"
        f"Topic focus: {review.expert_topic()}\n"
        f"Domain: {review.domain}\n"
        f"Scope: {review.scope}\n"
        f"PICO population: {review.pico.population}\n"
        f"PICO intervention: {review.pico.intervention}\n"
        f"PICO outcome: {review.pico.outcome}\n"
        f"Target databases: {', '.join(review.target_databases)}\n"
        f"Methodology expectations: {'; '.join(review.methodology_expectations(limit=10)) or 'not specified'}\n"
        f"Preferred terminology: {', '.join(review.preferred_terminology(limit=12)) or 'not specified'}\n"
        f"Deterministic fallback suggestion: {', '.join(fallback.selected_profiles)}\n"
        "Return a short routing_reason grounded in the structured review metadata, not vague domain wording."
    )


async def _route_audit_profiles_with_llm(
    *,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    provider: LLMProvider,
    client: PydanticAIClient,
) -> tuple[ManuscriptAuditProfileSelection, float]:
    fallback = select_audit_profiles(review, settings)
    cfg = settings.manuscript_audit
    max_profiles = max(1, int(cfg.max_profiles_per_run))
    if str(cfg.profile_activation or "domain_matched") != "domain_matched":
        return fallback, 0.0
    runtime = await provider.reserve_call_slot("writing")
    prompt = _routing_prompt(review, fallback, max_profiles=max_profiles)
    t0 = time.monotonic()
    try:
        parsed, tok_in, tok_out, cw, cr, _retries = await client.complete_validated(
            prompt,
            model=runtime.model,
            temperature=0.0,
            response_model=ManuscriptAuditProfileSelection,
        )
    except Exception as exc:
        logger.warning("Manuscript audit profile routing degraded to fallback: %s", exc)
        return fallback, 0.0
    cost = provider.estimate_cost_usd(runtime.model, tok_in, tok_out, cw, cr)
    await provider.log_cost(
        runtime.model,
        tok_in,
        tok_out,
        cost,
        latency_ms=int((time.monotonic() - t0) * 1000),
        phase="phase_7_audit",
        workflow_id=workflow_id,
        cache_read_tokens=cr,
        cache_write_tokens=cw,
    )
    selected = _normalize_selected_profiles(parsed.selected_profiles, max_profiles=max_profiles)
    return (
        ManuscriptAuditProfileSelection(
            selected_profiles=selected,
            routing_reason=parsed.routing_reason or fallback.routing_reason,
        ),
        cost,
    )


async def run_manuscript_audit(
    *,
    workflow_id: str,
    review: ReviewConfig,
    settings: SettingsConfig,
    manuscript_text: str,
    contract_summary_json: str,
    audit_context_json: str,
    provider: LLMProvider,
) -> tuple[ManuscriptAuditResult, list[ManuscriptAuditFinding]]:
    """Run bounded profile-based manuscript audit with explicit cost cap."""
    client = PydanticAIClient(timeout_seconds=float(settings.llm.request_timeout_seconds))
    selection, routing_cost = await _route_audit_profiles_with_llm(
        workflow_id=workflow_id,
        review=review,
        settings=settings,
        provider=provider,
        client=client,
    )
    selected = list(selection.selected_profiles)
    agent_name = "writing"
    findings: list[ManuscriptAuditFinding] = []
    total_cost = routing_cost
    verdict_rank = {"accept": 0, "minor_revisions": 1, "major_revisions": 2, "reject": 3}
    merged_verdict = "accept"
    summaries: list[str] = []
    successful_profiles = 0
    audit_passes = _build_audit_pass_plan(manuscript_text)

    for profile in selected:
        for pass_idx, audit_pass in enumerate(audit_passes, start=1):
            if total_cost >= float(settings.manuscript_audit.cost_cap_usd):
                break
            runtime = await provider.reserve_call_slot(agent_name)
            domain_brief = _audit_domain_brief(review)
            audit_date = date.today().isoformat()
            prompt = (
                "You are a manuscript peer reviewer.\n"
                f"Profile: {profile}\n"
                f"Instructions: {_profile_instructions(profile)}\n"
                f"Topic focus: {review.expert_topic()}\n"
                f"Domain: {review.domain}\n"
                f"Preferred terminology: {', '.join(review.preferred_terminology())}\n"
                + (domain_brief + "\n" if domain_brief else "")
                + "Return strict JSON only.\n"
                + "Use these severity levels: major, minor, note.\n"
                + "Set blocking=true only for critical defects that should block strict gate.\n\n"
                + f"Audit context date: {audit_date}.\n"
                + f"Audit pass label: {audit_pass.label}.\n"
                + f"Audit pass guidance: {audit_pass.scope_note}\n"
                + "Treat searches run on or before the audit context date as current, not future-dated. "
                + "Treat publication years less than or equal to the audit context year as allowable unless the manuscript "
                + "explicitly claims those studies were unavailable at the time of search.\n"
                + "Use the structured audit context JSON as authoritative for review metadata, source coverage, and DB-backed "
                + "counts. Use the deterministic contract summary JSON as authoritative for already-detected structural defects. "
                + "Do not contradict those inputs.\n"
                + "Do not repeat contract violations as fresh findings unless they create a broader methodological or interpretive "
                + "risk that is not already captured by the deterministic code.\n"
                + "A transparently disclosed failed or unavailable database is a search limitation, not an automatic "
                + "blocking defect, when multiple major databases were searched and the limitation is described clearly.\n"
                + "Single-reviewer data collection is a methodological limitation that should be reported accurately, but it "
                + "is not automatically blocking unless the manuscript misstates the process or the review claims duplicate "
                + "independent extraction that did not occur.\n\n"
                + "Absence of a formal inter-rater reliability statistic (for example, Cohen's kappa) is a reporting "
                + "limitation, not an automatic blocking defect, when the manuscript already discloses dual screening with "
                + "adjudication and does not falsely claim a computed reliability estimate.\n\n"
                + "Only set blocking=true for materially misleading or non-verifiable problems, such as contradictory core "
                + "methods/results statements, unsupported certainty or safety claims, or major omissions that would leave "
                + "the review uninterpretable to a critical peer reviewer.\n\n"
                + "Evaluate these dimensions: reporting completeness, methods-to-results coherence, evidence-quality "
                + "interpretation, risk-of-bias and certainty alignment, search and selection transparency, citation support, "
                + "and overclaiming.\n\n"
                + f"Structured audit context JSON:\n{audit_context_json}\n\n"
                f"Deterministic contract summary JSON:\n{contract_summary_json}\n\n"
                "Manuscript excerpt for this audit pass:\n"
                f"{audit_pass.manuscript_excerpt}"
            )
            t0 = time.monotonic()
            try:
                parsed, tok_in, tok_out, cw, cr, _retries = await client.complete_validated(
                    prompt,
                    model=runtime.model,
                    temperature=runtime.temperature,
                    response_model=_ReviewerResponse,
                )
            except Exception as exc:
                logger.warning("Manuscript audit profile %s degraded on %s: %s", profile, audit_pass.label, exc)
                summaries.append(f"{profile}/{audit_pass.label}: audit unavailable")
                findings.append(
                    ManuscriptAuditFinding(
                        finding_id=f"{profile}-{_finding_scope_token(audit_pass.label)}-degraded",
                        profile=profile,  # type: ignore[arg-type]
                        severity="note",
                        category="audit_unavailable",
                        section=None,
                        evidence=str(exc)[:500],
                        recommendation="Re-run manuscript audit once model credentials are configured.",
                        owner_module="manuscript_audit",
                        blocking=False,
                    )
                )
                continue
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
            successful_profiles += 1
            if verdict_rank[parsed.verdict] > verdict_rank[merged_verdict]:
                merged_verdict = parsed.verdict
            if parsed.summary:
                summaries.append(f"{profile}/{audit_pass.label}: {parsed.summary}")
            for idx, f in enumerate(parsed.findings):
                findings.append(
                    ManuscriptAuditFinding(
                        finding_id=f"{profile}-{_finding_scope_token(audit_pass.label)}-{pass_idx}-{idx + 1}",
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

    findings = _dedupe_findings(findings)

    major_count = len([f for f in findings if f.severity == "major"])
    minor_count = len([f for f in findings if f.severity == "minor"])
    note_count = len([f for f in findings if f.severity == "note"])
    blocking_count = len([f for f in findings if f.blocking])
    mode = str(getattr(settings.gates, "manuscript_audit_mode", "strict"))
    if successful_profiles == 0:
        merged_verdict = "reject"
        blocking_count = max(blocking_count, 1)
    passed = True
    if mode == "soft":
        passed = blocking_count == 0 and merged_verdict != "reject"
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


def serialize_audit_context(summary: dict[str, object]) -> str:
    """Stable JSON serialization for audit-context grounding."""
    return serialize_contract_summary(summary)
