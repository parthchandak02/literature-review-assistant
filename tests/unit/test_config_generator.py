from pathlib import Path

import pytest

from src.web.config_generator import (
    _AMBIGUOUS_DEFAULT_DATABASES,
    _GeneratedConfig,
    _NON_BIOMED_DEFAULT_DATABASES,
    _Pico,
    _STRUCTURE_PROMPT,
    _build_yaml,
    _resolve_target_databases,
    _sanitize_keywords,
    evaluate_config_quality_dict,
    evaluate_config_quality_yaml,
)


def _make_config(
    research_question: str,
    population: str,
    intervention: str,
    outcome: str,
    domain: str,
    scope: str,
) -> _GeneratedConfig:
    return _GeneratedConfig(
        research_question=research_question,
        review_type="systematic",
        pico=_Pico(
            population=population,
            intervention=intervention,
            comparison="baseline or alternative",
            outcome=outcome,
        ),
        keywords=[
            "ai coding assistant",
            "developer productivity",
            "code quality",
            "review latency",
            "pull request turnaround",
            "defect density",
            "pair programming",
            "software engineering",
            "developer workflow",
            "human ai collaboration",
            "code review",
            "program comprehension",
            "task completion time",
            "engineering teams",
            "tool adoption",
        ],
        domain=domain,
        scope=scope,
        inclusion_criteria=[
            "Empirical studies with measurable outcomes.",
            "Studies with defined intervention and comparator.",
            "Peer reviewed studies in English.",
            "Studies that report quantitative outcome metrics.",
        ],
        exclusion_criteria=[
            "Opinion articles and editorials.",
            "Studies with no intervention description.",
            "Studies that do not report outcomes.",
        ],
        search_overrides=None,
    )


def test_non_biomedical_topic_excludes_biomedical_connectors() -> None:
    cfg = _make_config(
        research_question="What is the impact of AI pair-programming tools on software developer productivity?",
        population="Professional software developers",
        intervention="AI code assistants",
        outcome="Task completion time and defect rate",
        domain="Software engineering productivity",
        scope="Focuses on engineering workflows and code quality outcomes.",
    )
    defaults = {
        "target_databases": [
            "openalex",
            "pubmed",
            "semantic_scholar",
            "scopus",
            "ieee_xplore",
            "clinicaltrials_gov",
        ],
        "target_sections": ["abstract", "methods"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "living_review": False,
        "last_search_date": None,
        "protocol": {"registered": False, "registry": "PROSPERO", "registration_number": "", "url": ""},
        "funding": {"source": "No funding received", "grant_number": "", "funder": ""},
        "conflicts_of_interest": "None",
        "search_overrides": {
            "openalex": "ai coding productivity software engineering",
            "pubmed": "ai[Title/Abstract] AND coding[Title/Abstract]",
            "clinicaltrials_gov": '"ai coding" OR "developer tools"',
        },
    }

    out = _build_yaml(cfg, defaults)
    assert "  - pubmed" not in out
    assert "  - clinicaltrials_gov" not in out
    assert "\n  pubmed:" not in out
    assert "\n  clinicaltrials_gov:" not in out


def test_biomedical_topic_keeps_biomedical_connectors() -> None:
    cfg = _make_config(
        research_question="How effective are voice-first medication reminder systems for elderly adults?",
        population="Older adults with chronic medication needs",
        intervention="Voice-first medication reminder systems",
        outcome="Medication adherence and missed dose rates",
        domain="Geriatric medication management",
        scope="Evaluates adherence outcomes for older adults in home and care settings.",
    )
    defaults = {
        "target_databases": [
            "openalex",
            "pubmed",
            "semantic_scholar",
            "scopus",
            "ieee_xplore",
            "clinicaltrials_gov",
        ],
        "target_sections": ["abstract", "methods"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "living_review": False,
        "last_search_date": None,
        "protocol": {"registered": False, "registry": "PROSPERO", "registration_number": "", "url": ""},
        "funding": {"source": "No funding received", "grant_number": "", "funder": ""},
        "conflicts_of_interest": "None",
    }

    out = _build_yaml(cfg, defaults)
    assert "  - pubmed" in out
    assert "  - clinicaltrials_gov" in out


def test_structure_prompt_contains_neutral_style_guardrail() -> None:
    lowered = _STRUCTURE_PROMPT.lower()
    assert "plain, neutral wording" in lowered
    assert "publication-quality" not in lowered
    assert "pathogen" not in lowered
    assert "few-shot style example (generic)" in lowered
    assert "few-shot style example (biomedical)" in lowered


def test_ambiguous_topic_uses_low_confidence_fallback_policy() -> None:
    cfg = _make_config(
        research_question="How do automation tools affect care coordination and operations?",
        population="Clinical and administrative teams",
        intervention="automation tools",
        outcome="productivity and documentation quality",
        domain="Healthcare operations and software workflows",
        scope="Mixed setting with technical and clinical language.",
    )
    defaults = {
        "target_databases": [
            "openalex",
            "pubmed",
            "semantic_scholar",
            "scopus",
            "ieee_xplore",
            "clinicaltrials_gov",
        ],
        "target_sections": ["abstract", "methods"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "living_review": False,
        "last_search_date": None,
        "protocol": {"registered": False, "registry": "PROSPERO", "registration_number": "", "url": ""},
        "funding": {"source": "No funding received", "grant_number": "", "funder": ""},
        "conflicts_of_interest": "None",
    }

    out = _build_yaml(cfg, defaults)
    assert "  - clinicaltrials_gov" not in out
    assert "  - pubmed" in out


def test_quality_evaluator_returns_expected_structure() -> None:
    yaml_text = """
research_question: "How does AI support code review in software teams?"
review_type: "systematic"
pico:
  population: "Software developers"
  intervention: "AI code assistants"
  comparison: "Traditional code review"
  outcome: "Review latency and defect density"
keywords:
  - "software engineering"
  - "code review"
  - "developer productivity"
  - "ai assistant"
  - "defect density"
  - "review latency"
  - "workflow"
  - "automation"
  - "version control"
  - "pull requests"
  - "engineering teams"
  - "pair programming"
  - "quality gates"
  - "repository"
  - "merge conflicts"
domain: "Software engineering"
scope: "Engineering workflow outcomes in software teams."
inclusion_criteria:
  - "Empirical studies."
  - "Quantitative outcomes."
  - "Peer reviewed sources."
  - "English language."
exclusion_criteria:
  - "Opinion pieces."
  - "No measurable outcomes."
  - "No intervention detail."
target_databases:
  - scopus
  - openalex
search_overrides:
  scopus: "TITLE-ABS-KEY(\\"ai assistant\\" OR \\"code review\\") AND TITLE-ABS-KEY(\\"latency\\" OR \\"defect\\")"
"""
    score = evaluate_config_quality_yaml(yaml_text)
    assert set(score.keys()) == {
        "total",
        "syntax_sanity",
        "keyword_quality",
        "database_relevance",
        "override_complexity",
        "route_domain",
        "route_confidence",
        "route_policy",
    }
    assert 0.0 <= score["total"] <= 100.0


def test_historical_snapshot_scores_wf0011_vs_wf0012_when_available() -> None:
    root = Path("/Users/parthchandak/projects/literature-review-assistant")
    wf0011 = root / "runs/2026-03-10/wf-0011-what-are-the-clinical-operational-and-financial-impacts-of-trans/run_10-41-24AM/config_snapshot.yaml"
    wf0012 = root / "runs/2026-03-10/wf-0012-what-is-the-effectiveness-of-voice-first-medication-reminder-rob/run_12-17-44PM/config_snapshot.yaml"

    if not wf0011.exists() or not wf0012.exists():
        pytest.skip("Historical run snapshots not present in this environment.")

    score_11 = evaluate_config_quality_yaml(wf0011.read_text(encoding="utf-8"))
    score_12 = evaluate_config_quality_yaml(wf0012.read_text(encoding="utf-8"))

    assert 0.0 <= score_11["total"] <= 100.0
    assert 0.0 <= score_12["total"] <= 100.0
    # wf-0012 is known to be broader/noisier than wf-0011 in keyword usage.
    assert score_11["keyword_quality"] >= score_12["keyword_quality"]


def test_keyword_sanitizer_removes_generic_noise_terms() -> None:
    raw = [
        "Automation",
        "workflow",
        "robotic medication dispensing systems",
        "Omnicell",
        "efficiency",
        "dispensing accuracy",
        "operational costs",
        "Automated Dispensing Cabinets",
        "university health centers",
        "scriptpro",
        "drug dispensing errors",
        "pharmacy robots",
        "staff workload",
        "prescription turnaround time",
        "manual dispensing",
        "medication dispensing technology",
    ]
    cleaned = _sanitize_keywords(raw)
    lowered = {k.lower() for k in cleaned}
    assert "automation" not in lowered
    assert "workflow" not in lowered
    assert "efficiency" not in lowered
    assert "robotic medication dispensing systems" in lowered
    assert len(cleaned) >= 12


def test_resolve_target_databases_biomedical_adds_pubmed_even_if_missing_in_defaults() -> None:
    cfg = _make_config(
        research_question="What is the effect of robotic medication dispensing on medication error rates in hospitals?",
        population="Hospital pharmacy patients",
        intervention="Robotic medication dispensing systems",
        outcome="Medication errors and adverse drug events",
        domain="Medication safety and clinical operations",
        scope="Clinical outcomes and safety effects in healthcare settings.",
    )
    defaults = {
        "target_databases": ["openalex", "semantic_scholar"],
        "target_sections": ["abstract", "methods"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "living_review": False,
        "last_search_date": None,
        "protocol": {"registered": False, "registry": "PROSPERO", "registration_number": "", "url": ""},
        "funding": {"source": "No funding received", "grant_number": "", "funder": ""},
        "conflicts_of_interest": "None",
    }
    selected, route = _resolve_target_databases(cfg, defaults)
    assert route.policy == "high_confidence_biomedical"
    assert "pubmed" in selected


def test_resolve_target_databases_generic_excludes_biomedical_connectors() -> None:
    cfg = _make_config(
        research_question="How do AI coding assistants impact software engineering team productivity?",
        population="Software engineers",
        intervention="AI code assistants",
        outcome="Cycle time and defect density",
        domain="Software engineering workflows",
        scope="Technical workflows and developer outcomes.",
    )
    selected, route = _resolve_target_databases(cfg, {"target_databases": ["openalex"]})
    assert route.policy == "high_confidence_generic"
    assert "pubmed" not in selected
    assert "clinicaltrials_gov" not in selected
    assert set(_NON_BIOMED_DEFAULT_DATABASES).issubset(set(selected))


def test_resolve_target_databases_ambiguous_removes_clinical_trials() -> None:
    cfg = _make_config(
        research_question="How does workflow automation affect service coordination and operational efficiency?",
        population="Administrative and engineering staff",
        intervention="Workflow automation tools",
        outcome="Operational efficiency and quality outcomes",
        domain="Operations and software workflows",
        scope="Mixed operational and technical context.",
    )
    selected, route = _resolve_target_databases(cfg, {"target_databases": ["clinicaltrials_gov", "pubmed", "openalex"]})
    assert route.policy == "low_confidence_fallback"
    assert "clinicaltrials_gov" not in selected
    assert "pubmed" in selected
    assert set(_AMBIGUOUS_DEFAULT_DATABASES).intersection(set(selected))


def test_quality_evaluator_penalizes_generic_search_overrides() -> None:
    topic_cfg = {
        "research_question": "What is the impact of robotic medication dispensing systems on dispensing accuracy and operational costs?",
        "pico": {
            "population": "University health centers",
            "intervention": "Robotic medication dispensing systems",
            "comparison": "Manual dispensing",
            "outcome": "Accuracy, speed, and costs",
        },
        "keywords": [
            "robotic medication dispensing",
            "automated dispensing cabinets",
            "omnicell",
            "scriptpro",
            "dispensing accuracy",
            "operational costs",
            "pharmacy automation",
            "university health centers",
            "prescription turnaround",
            "medication errors",
            "staff workload",
            "manual dispensing",
            "automated pharmacy",
            "robotic pharmacy",
            "dispensing efficiency",
        ],
        "domain": "Pharmacy automation in healthcare settings",
        "scope": "Review of robotic dispensing impact on operations and safety outcomes.",
        "target_databases": ["openalex", "scopus", "semantic_scholar", "pubmed"],
    }

    weak = dict(topic_cfg)
    weak["search_overrides"] = {
        "openalex": "outcomes effectiveness quality analysis evaluation",
        "scopus": "TITLE-ABS-KEY(\"outcomes\" OR \"quality\") AND TITLE-ABS-KEY(\"implementation\")",
    }
    strong = dict(topic_cfg)
    strong["search_overrides"] = {
        "openalex": "robotic medication dispensing university health center dispensing accuracy operational costs",
        "scopus": (
            "TITLE-ABS-KEY(\"robotic medication dispensing\" OR \"automated dispensing cabinets\" OR \"omnicell\") "
            "AND TITLE-ABS-KEY(\"university health center\" OR \"dispensing accuracy\" OR \"operational cost\")"
        ),
    }

    weak_score = evaluate_config_quality_dict(weak)
    strong_score = evaluate_config_quality_dict(strong)
    assert strong_score["override_complexity"] > weak_score["override_complexity"]


def test_historical_snapshot_scores_wf0013_against_wf0011_wf0012_when_available() -> None:
    root = Path("/Users/parthchandak/projects/literature-review-assistant")
    wf0011 = root / "runs/2026-03-10/wf-0011-what-are-the-clinical-operational-and-financial-impacts-of-trans/run_10-41-24AM/config_snapshot.yaml"
    wf0012 = root / "runs/2026-03-10/wf-0012-what-is-the-effectiveness-of-voice-first-medication-reminder-rob/run_12-17-44PM/config_snapshot.yaml"
    wf0013 = root / "runs/2026-03-10/wf-0013-what-is-the-impact-of-robotic-medication-dispensing-systems-on-dispe/run_12-57-40PM/config_snapshot.yaml"

    if not wf0011.exists() or not wf0012.exists() or not wf0013.exists():
        pytest.skip("One or more historical run snapshots are not present in this environment.")

    score_11 = evaluate_config_quality_yaml(wf0011.read_text(encoding="utf-8"))
    score_12 = evaluate_config_quality_yaml(wf0012.read_text(encoding="utf-8"))
    score_13 = evaluate_config_quality_yaml(wf0013.read_text(encoding="utf-8"))

    assert 0.0 <= score_11["total"] <= 100.0
    assert 0.0 <= score_12["total"] <= 100.0
    assert 0.0 <= score_13["total"] <= 100.0
    assert score_13["database_relevance"] >= score_12["database_relevance"]
