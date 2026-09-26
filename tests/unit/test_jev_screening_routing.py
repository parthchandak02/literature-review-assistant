from src.models import ScreeningDecisionType
from src.models.config import JevConfig
from src.screening.jev_screening import _confidence_threshold_for, _map_choice


def test_map_choice_screening_labels() -> None:
    assert _map_choice("INCLUDE") == ScreeningDecisionType.INCLUDE
    assert _map_choice("exclude") == ScreeningDecisionType.EXCLUDE
    assert _map_choice("uncertain") == ScreeningDecisionType.UNCERTAIN


def test_exclude_requires_higher_confidence_threshold() -> None:
    cfg = JevConfig()
    assert _confidence_threshold_for(ScreeningDecisionType.EXCLUDE, cfg) == cfg.exclude_confidence
    assert _confidence_threshold_for(ScreeningDecisionType.INCLUDE, cfg) == cfg.route_confidence
