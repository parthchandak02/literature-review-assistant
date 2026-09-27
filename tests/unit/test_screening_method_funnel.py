from src.writing.context_builder import _build_screening_method_description


def test_three_stage_funnel_discloses_pre_screen_exclusions() -> None:
    text = _build_screening_method_description(
        [object()], 495, batch_screen_forwarded=60, batch_screen_excluded=0, batch_screen_threshold=0.3, cohens_kappa=0.87
    )
    assert "evaluated all 495 records and excluded 435" in text
    assert "routing 60 records" in text
    assert "on the 60 records evaluated" not in text


def test_three_stage_funnel_without_pre_screen_exclusions() -> None:
    text = _build_screening_method_description(
        [object()], 60, batch_screen_forwarded=50, batch_screen_excluded=10, batch_screen_threshold=0.3, cohens_kappa=0.8
    )
    assert "a relevance pre-screen evaluated all records, routing 60 records" in text
    assert "excluded 10 records with low relevance" in text
