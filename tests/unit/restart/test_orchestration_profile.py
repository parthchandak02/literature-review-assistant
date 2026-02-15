from src.restart.orchestration_profile import choose_orchestration_backend


def test_langgraph_selected_for_small_workload():
    decision = choose_orchestration_backend(
        estimated_runtime_hours=2,
        max_human_wait_hours=1,
        uses_cross_service_workers=False,
    )
    assert decision.backend == "langgraph"
    assert decision.should_introduce_temporal is False


def test_temporal_selected_for_long_workload():
    decision = choose_orchestration_backend(
        estimated_runtime_hours=40,
        max_human_wait_hours=2,
        uses_cross_service_workers=False,
    )
    assert decision.backend == "temporal"
    assert decision.should_introduce_temporal is True
