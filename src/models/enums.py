"""Enum definitions for typed phase boundaries."""

from enum import Enum


class ReviewType(str, Enum):
    SYSTEMATIC = "systematic"
    SCOPING = "scoping"
    NARRATIVE = "narrative"


class ScreeningDecisionType(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNCERTAIN = "uncertain"


class ReviewerType(str, Enum):
    REVIEWER_A = "reviewer_a"
    REVIEWER_B = "reviewer_b"
    ADJUDICATOR = "adjudicator"
    HUMAN = "human"
    KEYWORD_FILTER = "keyword_filter"


class RiskOfBiasJudgment(str, Enum):
    LOW = "low"
    SOME_CONCERNS = "some_concerns"
    HIGH = "high"


class RobinsIJudgment(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    SERIOUS = "serious"
    CRITICAL = "critical"
    NO_INFORMATION = "no_information"


class GateStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class ExclusionReason(str, Enum):
    WRONG_POPULATION = "wrong_population"
    WRONG_INTERVENTION = "wrong_intervention"
    WRONG_COMPARATOR = "wrong_comparator"
    WRONG_OUTCOME = "wrong_outcome"
    WRONG_STUDY_DESIGN = "wrong_study_design"
    NOT_PEER_REVIEWED = "not_peer_reviewed"
    DUPLICATE = "duplicate"
    INSUFFICIENT_DATA = "insufficient_data"
    WRONG_LANGUAGE = "wrong_language"
    NO_FULL_TEXT = "no_full_text"
    KEYWORD_FILTER = "keyword_filter"  # pre-filter: zero intervention keyword matches; no LLM call made
    LOW_RELEVANCE_SCORE = "low_relevance_score"  # BM25 score below cap cutoff; no LLM call made
    PROTOCOL_ONLY = "protocol_only"  # study is a registered protocol/trial with no reported results
    OTHER = "other"


class GRADECertainty(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


class StudyDesign(str, Enum):
    RCT = "rct"
    NON_RANDOMIZED = "non_randomized"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    QUALITATIVE = "qualitative"
    MIXED_METHODS = "mixed_methods"
    CROSS_SECTIONAL = "cross_sectional"
    PROTOCOL = "protocol"  # registered trial protocol or study design paper with no results
    OTHER = "other"


class SourceCategory(str, Enum):
    DATABASE = "database"
    OTHER_SOURCE = "other_source"
