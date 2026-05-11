"""Quality assessment models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.models.enums import GRADECertainty, RiskOfBiasJudgment, RobinsIJudgment


class RoB2Assessment(BaseModel):
    paper_id: str
    domain_1_randomization: RiskOfBiasJudgment
    domain_1_rationale: str
    domain_2_deviations: RiskOfBiasJudgment
    domain_2_rationale: str
    domain_3_missing_data: RiskOfBiasJudgment
    domain_3_rationale: str
    domain_4_measurement: RiskOfBiasJudgment
    domain_4_rationale: str
    domain_5_selection: RiskOfBiasJudgment
    domain_5_rationale: str
    overall_judgment: RiskOfBiasJudgment
    overall_rationale: str
    assessment_source: Literal["llm", "heuristic"] = "llm"
    fallback_used: bool = False


class RobinsIAssessment(BaseModel):
    paper_id: str
    domain_1_confounding: RobinsIJudgment
    domain_1_rationale: str
    domain_2_selection: RobinsIJudgment
    domain_2_rationale: str
    domain_3_classification: RobinsIJudgment
    domain_3_rationale: str
    domain_4_deviations: RobinsIJudgment
    domain_4_rationale: str
    domain_5_missing_data: RobinsIJudgment
    domain_5_rationale: str
    domain_6_measurement: RobinsIJudgment
    domain_6_rationale: str
    domain_7_reported_result: RobinsIJudgment
    domain_7_rationale: str
    overall_judgment: RobinsIJudgment
    overall_rationale: str
    assessment_source: Literal["llm", "heuristic"] = "llm"
    fallback_used: bool = False


class GRADEOutcomeAssessment(BaseModel):
    outcome_name: str
    number_of_studies: int
    study_designs: str
    starting_certainty: GRADECertainty
    risk_of_bias_downgrade: int = Field(ge=0, le=2)
    inconsistency_downgrade: int = Field(ge=0, le=2)
    indirectness_downgrade: int = Field(ge=0, le=2)
    imprecision_downgrade: int = Field(ge=0, le=2)
    publication_bias_downgrade: int = Field(ge=0, le=2)
    large_effect_upgrade: int = Field(ge=0, le=2)
    dose_response_upgrade: int = Field(ge=0, le=1)
    residual_confounding_upgrade: int = Field(ge=0, le=1)
    final_certainty: GRADECertainty
    justification: str
    # When False, inconsistency/indirectness were not computed from pipeline
    # data and default to 0; the SoF table will flag them as "not assessed".
    inconsistency_assessed: bool = True
    indirectness_assessed: bool = True


class GradeSoFRow(BaseModel):
    """One row in the GRADE Summary of Findings table (one outcome)."""

    outcome_name: str
    n_studies: int
    study_design: str
    risk_of_bias: str
    inconsistency: str
    indirectness: str
    imprecision: str
    other_considerations: str
    certainty: GRADECertainty
    effect_summary: str


class GradeSoFTable(BaseModel):
    """GRADE Summary of Findings table for the full review."""

    topic: str
    rows: list[GradeSoFRow] = Field(default_factory=list)


class CaspAssessment(BaseModel):
    """CASP appraisal result for qualitative studies."""

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
    assessment_source: Literal["llm", "heuristic"] = "llm"
    fallback_used: bool = False


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
    screening_1_clear_question: bool
    screening_2_appropriate_data: bool
    criterion_1: bool
    criterion_2: bool
    criterion_3: bool
    criterion_4: bool
    criterion_5: bool
    overall_score: int
    overall_summary: str
    assessment_source: Literal["llm", "heuristic"] = "llm"
    fallback_used: bool = False
