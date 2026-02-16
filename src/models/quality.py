"""Quality assessment models."""

from __future__ import annotations

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
